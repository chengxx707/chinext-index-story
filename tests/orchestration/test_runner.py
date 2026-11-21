"""Drive the runner with real, short commands that only write text artifacts."""

from hashlib import sha256
import sys

import pytest

from orchestration.adapters import Adapter
from orchestration.engine import Runner
from orchestration.registry import Registry, Task
from orchestration.reports import build_report
from orchestration.state import Store


WRITE_RESULT = (
    "from pathlib import Path; import sys; "
    "Path(sys.argv[1]).write_text('checked', encoding='utf-8'); print('check ran')"
)


def command(code, *args):
    return (sys.executable, "-c", code, *map(str, args))


def text_adapter(calls, *, render=False):
    def build(root, attempt_dir):
        calls.append(attempt_dir)
        return command(WRITE_RESULT, attempt_dir / "result.txt")

    return Adapter(build, lambda _: ("result.txt",), render=render)


def workflow(root, tasks, adapters):
    store = Store(root / "state")
    return Runner(root, Registry(tasks), store, adapters), store


def by_task(rows):
    return {row["task_id"]: row for row in rows}


def test_failed_prerequisite_blocks_downstream_without_stopping_other_lane(tmp_path):
    calls = []
    tasks = [
        Task("A.timeline", "A", "Timeline", adapter="broken"),
        Task("A.preview", "A", "Preview", dependencies=("A.timeline",), adapter="check"),
        Task("B.layout", "B", "Layout", adapter="check"),
    ]
    broken = Adapter(lambda *_: command("raise SystemExit(2)"), lambda _: ())
    runner, _ = workflow(tmp_path, tasks, {"broken": broken, "check": text_adapter(calls)})
    records = by_task(runner.run())
    assert records["A.timeline"]["status"] == "FAILED"
    assert records["A.preview"]["status"] == "BLOCKED"
    assert records["A.preview"]["attempts"] == []
    assert records["B.layout"]["status"] == "PASSED"
    assert len(calls) == 1


def test_ready_tasks_in_both_lanes_can_run_concurrently(tmp_path):
    mark_and_wait = """
from pathlib import Path
import sys
import time

marker, peer = map(Path, sys.argv[1:])
marker.touch()
deadline = time.monotonic() + 5
while not peer.exists():
    if time.monotonic() >= deadline:
        raise RuntimeError('The other lane did not start')
    time.sleep(.01)
"""

    def marks(marker, peer):
        return Adapter(lambda root, _: command(mark_and_wait, root / marker, root / peer), lambda _: ())

    tasks = [Task("A.timeline", "A", "Timeline", adapter="timeline"),
             Task("B.layout", "B", "Layout", adapter="layout")]
    runner, _ = workflow(tmp_path, tasks, {"timeline": marks("a", "b"), "layout": marks("b", "a")})
    assert [row["status"] for row in runner.run(jobs=2)] == ["PASSED", "PASSED"]


def test_manual_review_blocks_dependent_work_until_approved(tmp_path):
    calls = []
    tasks = [
        Task("B.review", "B", "Representative review", approval=True),
        Task("A.preview", "A", "Preview", dependencies=("B.review",), adapter="check"),
    ]
    runner, _ = workflow(tmp_path, tasks, {"check": text_adapter(calls)})
    records = by_task(runner.run())
    assert records["B.review"]["status"] == "BLOCKED"
    assert records["A.preview"]["status"] == "BLOCKED"
    assert calls == []

    runner.approve("B.review", "Director", "Representative accepted")
    records = by_task(runner.run())
    assert records["B.review"]["status"] == "PASSED"
    assert records["A.preview"]["status"] == "PASSED"
    assert len(calls) == 1


def test_review_cannot_be_approved_before_its_prerequisites_pass(tmp_path):
    calls = []
    tasks = [
        Task("B.layout", "B", "Layout", adapter="check"),
        Task("B.review", "B", "Review", dependencies=("B.layout",), approval=True),
    ]
    runner, _ = workflow(tmp_path, tasks, {"check": text_adapter(calls)})
    with pytest.raises(ValueError, match="Prerequisites"):
        runner.approve("B.review", "Director", "No artifacts to inspect yet")
    assert calls == []


def test_protected_adapter_requires_new_approval_when_input_changes(tmp_path):
    source = tmp_path / "input.txt"
    source.write_text("first", encoding="utf-8")
    calls = []
    task = Task("A.protected", "A", "Protected check", inputs=("input.txt",),
                adapter="check", approval=True)
    runner, store = workflow(tmp_path, [task], {"check": text_adapter(calls)})
    blocked, = runner.run()
    assert blocked["status"] == "BLOCKED"
    assert calls == []

    runner.approve(task.task_id, "Director", "Approved first input")
    approved, = runner.run()
    assert approved["status"] == "PASSED"
    assert approved["input_hash"] == blocked["input_hash"]

    source.write_text("second", encoding="utf-8")
    new, = runner.run()
    assert new["status"] == "BLOCKED"
    assert new["input_hash"] != approved["input_hash"]
    with pytest.raises(ValueError, match="stale"):
        runner.approve(task.task_id, "Director", "Approved first input", input_hash=blocked["input_hash"])
    assert runner.plan()[0]["status"] == "BLOCKED"
    assert len(calls) == 1
    assert len(store.records()) == 2


def test_explicit_render_permission_is_required_even_after_approval(tmp_path):
    calls = []
    task = Task("A.render", "A", "Render", adapter="render", approval=True)
    runner, _ = workflow(tmp_path, [task], {"render": text_adapter(calls, render=True)})
    runner.approve(task.task_id, "Director", "Review complete")
    assert runner.run()[0]["status"] == "BLOCKED"
    assert calls == []


def test_same_content_is_idempotent_across_runner_instances(tmp_path):
    source = tmp_path / "input.txt"
    source.write_text("first", encoding="utf-8")
    calls = []
    task = Task("B.check", "B", "Check", adapter="check", inputs=("input.txt",))
    adapters = {"check": text_adapter(calls)}
    runner, store = workflow(tmp_path, [task], adapters)
    first, = runner.run()
    assert first["status"] == "PASSED"
    assert first["manifest"]["artifacts"]

    reopened, _ = workflow(tmp_path, [task], adapters)
    assert reopened.run() == [first]
    assert len(calls) == 1
    assert len(store.records()) == 1

    source.write_text("changed", encoding="utf-8")
    changed, = reopened.run()
    assert changed["input_hash"] != first["input_hash"]
    assert changed["status"] == "PASSED"
    assert len(calls) == len(store.records()) == 2


def test_corrupt_artifact_is_recreated_before_cached_pass_is_reused(tmp_path):
    calls = []
    task = Task("B.check", "B", "Check", adapter="check")
    runner, store = workflow(tmp_path, [task], {"check": text_adapter(calls)})
    first, = runner.run()
    artifact = next(item for item in first["manifest"]["artifacts"] if item["path"].endswith("/result.txt"))
    assert artifact["sha256"] == sha256(b"checked").hexdigest()
    (store.path / artifact["path"]).write_text("tampered", encoding="utf-8")

    assert runner.plan()[0]["status"] != "PASSED"
    repaired, = runner.run()
    assert repaired["status"] == "PASSED"
    assert repaired["input_hash"] == first["input_hash"]
    assert len(repaired["attempts"]) == len(calls) == 2
    assert len(store.records()) == 1
    assert (calls[-1] / "result.txt").read_bytes() == b"checked"


def test_dependent_approval_expires_when_upstream_artifact_digest_changes(tmp_path):
    source_calls = []

    def build(root, attempt_dir):
        source_calls.append(attempt_dir)
        return command(
            "from pathlib import Path; import sys; Path(sys.argv[1]).write_text(sys.argv[2])",
            attempt_dir / "result.txt", len(source_calls),
        )

    tasks = [
        Task("B.layout", "B", "Layout", adapter="layout"),
        Task("B.review", "B", "Review", dependencies=("B.layout",), approval=True),
    ]
    runner, store = workflow(tmp_path, tasks, {"layout": Adapter(build, lambda _: ("result.txt",))})
    layout, _ = runner.run()
    runner.approve("B.review", "Director", "Approved initial layout")
    _, reviewed = runner.run()
    assert reviewed["status"] == "PASSED"
    (source_calls[0] / "result.txt").unlink()

    recreated, pending_review = runner.run()
    assert recreated["status"] == "PASSED"
    assert recreated["input_hash"] == layout["input_hash"]
    assert pending_review["status"] == "BLOCKED"
    assert pending_review["attempts"] == []
    assert pending_review["input_hash"] != reviewed["input_hash"]
    with pytest.raises(ValueError, match="stale"):
        runner.approve("B.review", "Director", "Old layout", input_hash=reviewed["input_hash"])
    assert store.get("B.review", reviewed["input_hash"])["status"] == "PASSED"


def test_log_records_failure_and_safe_retry_finishes_validation(tmp_path):
    calls = []

    def build(root, attempt_dir):
        calls.append(attempt_dir)
        if len(calls) == 1:
            return command("import sys; print('temporary error', file=sys.stderr); sys.exit(7)")
        return command(WRITE_RESULT, attempt_dir / "result.txt")

    task = Task("A.check", "A", "Check", adapter="check", max_attempts=2)
    adapter = Adapter(build, lambda _: ("result.txt",), retry_safe=True)
    runner, store = workflow(tmp_path, [task], {"check": adapter})
    record, = runner.run()
    assert record["status"] == "PASSED"
    failed, passed = record["attempts"]
    assert failed["exit_code"] == 7
    assert failed["error"]
    assert "temporary error" in (store.path / failed["log"]).read_text(encoding="utf-8")
    assert passed["exit_code"] == 0
    assert "check ran" in (store.path / passed["log"]).read_text(encoding="utf-8")
    assert [event["status"] for event in record["history"] if event["status"] != "PENDING"] == [
        "READY", "RUNNING", "FAILED", "READY", "RUNNING", "VALIDATING", "PASSED",
    ]


def test_safe_retry_budget_is_not_reset_by_another_run(tmp_path):
    calls = []

    def build(root, attempt_dir):
        calls.append(attempt_dir)
        return command("raise SystemExit(9)")

    task = Task("B.check", "B", "Check", adapter="check", max_attempts=2)
    adapter = Adapter(build, lambda _: (), retry_safe=True)
    runner, store = workflow(tmp_path, [task], {"check": adapter})
    first, = runner.run()
    assert first["status"] == "FAILED"
    assert len(first["attempts"]) == 2
    runner.run()
    assert len(calls) == 2
    assert len(store.records()) == 1


def test_runner_rejects_retry_for_adapter_without_retry_permission(tmp_path):
    task = Task("A.check", "A", "Check", adapter="check", max_attempts=2)
    with pytest.raises(ValueError, match="retry-safe"):
        workflow(tmp_path, [task], {"check": text_adapter([])})


def test_input_change_during_execution_fails_without_retrying_new_identity(tmp_path):
    source = tmp_path / "input.txt"
    source.write_text("first", encoding="utf-8")
    task = Task("A.check", "A", "Check", adapter="check", inputs=("input.txt",), max_attempts=3)
    change_input_once = (
        "from pathlib import Path; import sys\n"
        "path = Path(sys.argv[1])\n"
        "if path.read_text() == 'first':\n"
        "    path.write_text('first!')\n"
    )
    adapter = Adapter(lambda *_: command(change_input_once, source), lambda _: (), retry_safe=True)
    runner, store = workflow(tmp_path, [task], {"check": adapter})
    expected_hash = runner.plan()[0]["input_hash"]

    record, = runner.run()
    assert record["input_hash"] == expected_hash
    assert record["status"] == "FAILED"
    assert record["code"] == "input_changed"
    assert len(record["attempts"]) == 1
    assert source.read_text(encoding="utf-8") == "first!"
    assert store.records() == [record]


def test_missing_artifact_fails_validation_even_if_command_exits_zero(tmp_path):
    task = Task("A.check", "A", "Check", adapter="check")
    adapter = Adapter(lambda *_: command("pass"), lambda _: ("result.txt",))
    runner, _ = workflow(tmp_path, [task], {"check": adapter})
    record, = runner.run()
    assert record["status"] == "FAILED"
    assert record["attempts"][0]["exit_code"] == 0
    assert record["attempts"][0]["error"]
    assert record["manifest"] is None


def test_report_uses_recorded_results_without_counting_dry_run_or_approval(tmp_path):
    calls = []
    task = Task("A.check", "A", "Check", adapter="check", approval=True)
    runner, store = workflow(tmp_path, [task], {"check": text_adapter(calls)})
    assert runner.plan()[0]["status"] == "BLOCKED"
    assert not store.path.exists()
    runner.approve(task.task_id, "Director", "Approved check")
    runner.plan()
    assert build_report(store)["records"] == []
    assert calls == []

    execution, = runner.run()
    report = build_report(Store(store.path))
    assert report["records"] == [execution]
    assert report["lanes"]["A"]["PASSED"] == 1
