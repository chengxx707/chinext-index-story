"""Check production dependency boundaries with safe local fixtures."""

from dataclasses import replace
import json
from pathlib import Path
import sys

import pytest

from orchestration.adapters import Adapter, PrerequisiteBlocked
from orchestration.engine import Runner
from orchestration.registry import Registry, load_registry
from orchestration.state import Store
from orchestration.workflows.preview import build_preview


def test_production_graph_keeps_photo_work_off_preview_and_visual_review_paths():
    tasks = load_registry().tasks

    def ancestors(task_id):
        deps = tasks[task_id].dependencies
        return {parent for dep in deps for parent in {dep} | ancestors(dep)}

    photo = "A.archive-photos"
    assert photo not in ancestors("B.representative-review")
    assert photo not in ancestors("A.full-preview")
    assert photo not in ancestors("A.full-preview-render")
    assert photo in ancestors("A.full-render")
    assert "B.representative-review" in ancestors("A.full-render")
    assert "A.full-content-review" in ancestors("A.full-render")
    assert tasks["A.full-render"].approval
    assert tasks["A.final-review"].approval
    assert tasks["A.final-review"].dependencies == ("A.full-render",)
    assert tasks["A.2015-master-adoption"].approval
    assert tasks["A.2015-master-adoption"].dependencies == ("A.2015-story",)


def test_preview_and_body_review_advance_with_photo_prerequisite_blocked(tmp_path):
    tasks = load_registry().tasks
    names = [
        "A.production-docs", "A.production-check", "A.full-preview",
        "A.archive-photos", "A.album-render", "B.component-keyframes",
        "B.representative-render", "B.representative-review",
    ]
    fixture_tasks = [replace(tasks[name], inputs=(), adapter=(
        "missing-photos" if name == "A.archive-photos" else "noop" if tasks[name].adapter else None
    )) for name in names]

    def command(*_):
        return (sys.executable, "-c", "print('fixture only')")

    def missing_photos(_):
        raise PrerequisiteBlocked("Zero qualified photos")

    runner = Runner(tmp_path, Registry(fixture_tasks), Store(tmp_path / "state"), {
        "noop": Adapter(command, lambda _: (), retry_safe=True),
        "missing-photos": Adapter(command, missing_photos),
    })
    runner.run()
    runner.approve("B.representative-render", "Fixture reviewer", "Permit fixture check")
    runner.run()
    runner.approve("B.representative-review", "Fixture reviewer", "Approve body fixture")
    statuses = {record["task_id"]: record["status"] for record in runner.run()}
    assert statuses["B.representative-review"] == statuses["A.full-preview"] == "PASSED"
    assert statuses["A.archive-photos"] == statuses["A.album-render"] == "BLOCKED"


def test_candidate_adoption_is_a_version_scoped_gate_and_keeps_master_read_only(tmp_path):
    master = tmp_path / "config/production/film_master_v1.json"
    master.parent.mkdir(parents=True)
    original = b'{"original": true}\n'
    master.write_bytes(original)
    tasks = load_registry().tasks
    gate = tasks["A.2015-master-adoption"]
    root = tasks["A.2015-research"]
    candidate = tasks["A.2015-story"]
    runner = Runner(tmp_path, Registry([
        replace(root, adapter="noop", inputs=()),
        replace(candidate, adapter="noop", inputs=()),
        gate,
    ]), Store(tmp_path / "state"), {
        "noop": Adapter(lambda *_: (sys.executable, "-c", "pass"), lambda _: (), retry_safe=True),
    })
    with pytest.raises(ValueError, match="Prerequisites"):
        runner.approve(gate.task_id, "Fixture reviewer", "Attempt before evidence")
    blocked = runner.run()[-1]
    assert blocked["status"] == "BLOCKED" and blocked["attempts"] == []
    assert master.read_bytes() == original
    runner.approve(gate.task_id, "Fixture reviewer", "Consider the exact candidate for adoption",
                   input_hash=blocked["input_hash"])
    assert runner.run()[-1]["status"] == "PASSED"
    assert master.read_bytes() == original
    master.write_bytes(b'{"different_formal_draft": true}\n')
    assert runner.plan()[-1]["status"] == "BLOCKED"


def test_timing_preview_marks_album_placeholders_and_uses_compiled_frame_ranges(tmp_path):
    compiled = tmp_path / "compiled.json"
    beat = {
        "id": "A01_b01", "start_frame": 0, "end_frame_exclusive": 90,
        "screen_lines": ["正式照片缺失", "</script>"], "source_line": None,
        "historical_date": "2015-06", "market_observation_date": "2015-06-30",
    }
    timeline = {
        "master_sha256": "fixture",
        "video": {"fps": 30, "frame_count_plan": 90},
        "scenes": [{"id": "A01", "role": "album", "title": "档案", "beats": [beat]}],
    }
    compiled.write_text(json.dumps(timeline))
    build_preview(compiled, tmp_path / "out")
    result = json.loads((tmp_path / "out/preview_timing.json").read_text())
    assert result["placeholder_scene_ids"] == ["A01"] and result["duration_seconds"] == 3
    assert result["visual_rendered"] is False
    assert result["beats"][0]["market_observation_date"] == "2015-06-30"
    assert "\\u003c/script>" in (tmp_path / "out/preview.html").read_text()

    beat["start_frame"] = 1
    compiled.write_text(json.dumps(timeline))
    with pytest.raises(ValueError, match="coverage"):
        build_preview(compiled, tmp_path / "invalid")


def test_dependency_adapter_reads_exact_validated_attempt(tmp_path):
    upstream = "A.data"
    template = "first"
    calls = []

    def write_data(_root, out):
        calls.append(out)
        return sys.executable, "-c", "import sys; print(sys.argv[1])", template

    def consume(_root, _out, deps: dict[str, Path]):
        calls.append(deps[upstream])
        return sys.executable, "-c", "from pathlib import Path; import sys; print(Path(sys.argv[1]).read_text())", str(deps[upstream] / "command.log")

    runner = Runner(tmp_path, Registry([
        replace(load_registry().tasks["A.production-docs"], task_id=upstream, adapter="write", inputs=("fingerprint",)),
        replace(load_registry().tasks["A.full-preview"], task_id="A.consume", adapter="consume",
                dependencies=(upstream,), inputs=()),
    ]), Store(tmp_path / "state"), {
        "write": Adapter(write_data, lambda _: ()),
        "consume": Adapter(None, lambda _: (), dependency_command=consume),
    })
    assert all(record["status"] == "PASSED" for record in runner.run())
    assert calls[0] == calls[1]
    assert all(record["status"] == "PASSED" for record in runner.run())
    assert len(calls) == 2
    (tmp_path / "fingerprint").write_text("changed")
    assert all(record["status"] == "PASSED" for record in runner.run())
    assert calls[2] == calls[3] and calls[2] != calls[0]
