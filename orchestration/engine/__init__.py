"""Schedule dependency-ready tasks and preserve evidence from each attempt."""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from hashlib import file_digest, sha256
import json
from pathlib import Path
import os
import signal
import subprocess

from orchestration.adapters import Adapter, PrerequisiteBlocked
from orchestration.approvals import ApprovalStore
from orchestration.registry import Registry, Task
from orchestration.state import Status, Store, transition, utc_now


def _sha(path: Path) -> str:
    with path.open("rb") as handle:
        return file_digest(handle, "sha256").hexdigest()


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class InputChanged(RuntimeError):
    """The task's fingerprint no longer describes the input on disk."""


@dataclass
class Decision:
    task: Task
    input_hash: str
    dependencies: dict
    record: dict | None
    status: Status
    reason: str | None = None
    code: str | None = None

    def row(self) -> dict:
        return {
            "task_id": self.task.task_id, "lane": self.task.lane, "title": self.task.title,
            "dependencies": self.dependencies, "input_hash": self.input_hash,
            "adapter": self.task.adapter, "approval_required": self.task.approval,
            "status": self.status, "reason": self.reason,
        }


class Runner:
    def __init__(self, root: Path, registry: Registry, store: Store, adapters: dict[str, Adapter]):
        self.root = root.resolve()
        self.registry = registry
        self.store = store
        self.adapters = adapters
        self.approvals = ApprovalStore(store.path)
        implementation = Path(__file__).parents[1]
        self._implementation = {
            name: _sha(implementation / name / "__init__.py")
            for name in ("adapters", "engine")
        }
        for task in registry.tasks.values():
            if task.adapter is None:
                continue
            adapter = adapters.get(task.adapter)
            if adapter is None:
                raise ValueError(f"{task.task_id}: unknown adapter {task.adapter}")
            if task.max_attempts > 1 and not adapter.retry_safe:
                raise ValueError(f"{task.task_id}: retries require a retry-safe adapter")
            if adapter.render and (not task.approval or task.max_attempts != 1):
                raise ValueError(f"{task.task_id}: rendering requires approval and a single attempt")

    def _input_hash(self, task: Task, dependencies: dict) -> str:
        adapter = self.adapters.get(task.adapter)
        patterns = task.inputs
        if adapter is not None and adapter.extra_inputs is not None:
            patterns += adapter.extra_inputs(self.root)
        inputs = {}
        for pattern in sorted(set(patterns)):
            literal = self.root / pattern
            paths = (literal,) if literal.is_file() or Path(pattern).is_absolute() else self.root.glob(pattern)
            inputs[pattern] = {
                str(path.relative_to(self.root) if path.is_relative_to(self.root) else path): _sha(path)
                for path in sorted(paths) if path.is_file()
            }
        return _digest({
            "task": asdict(task), "inputs": inputs, "dependencies": dependencies,
            "implementation": self._implementation,
        })

    def _artifact(self, path: Path) -> dict:
        path = path.resolve()
        return {"path": path.relative_to(self.store.path).as_posix(),
                "sha256": _sha(path), "bytes": path.stat().st_size}

    def _valid_manifest(self, record: dict) -> bool:
        manifest = record.get("manifest")
        if manifest is None:
            return False
        try:
            path = self.store.path / record["manifest_path"]
            if json.loads(path.read_text(encoding="utf-8")) != manifest:
                return False
            return all(self._artifact(self.store.path / item["path"]) == item
                       for item in manifest["artifacts"])
        except (KeyError, OSError, TypeError, ValueError):
            return False

    @staticmethod
    def _dependency_artifacts(record: dict) -> list[str]:
        return [item["sha256"] for item in record["manifest"]["artifacts"]
                if not item["path"].endswith("/command.log")]

    def _decide(self, task: Task, prior: dict[str, Decision], allow_render: bool) -> Decision:
        parents = [prior[dep] for dep in task.dependencies]
        dependencies = {}
        for parent in parents:
            artifacts = None
            if parent.status == Status.PASSED:
                artifacts = self._dependency_artifacts(parent.record)
            dependencies[parent.task.task_id] = {"input_hash": parent.input_hash, "artifacts": artifacts}
        input_hash = self._input_hash(task, dependencies)
        record = self.store.get(task.task_id, input_hash)
        decision = Decision(task, input_hash, dependencies, record, Status.READY)

        def block(reason: str, code: str) -> Decision:
            decision.status = Status.BLOCKED
            decision.reason = reason
            decision.code = code
            return decision

        waiting = [f"{parent.task.task_id} ({parent.status})" for parent in parents
                   if parent.status != Status.PASSED]
        if task.unavailable:
            reason = task.unavailable
            if waiting:
                reason += "。Prerequisites have not passed: " + ", ".join(waiting)
            return block(reason, "unavailable")
        if waiting:
            return block("Prerequisites have not passed: " + ", ".join(waiting), "dependencies")
        if task.approval and self.approvals.get(task.task_id, input_hash) is None:
            return block("Human approval required for this input hash", "approval")
        if record:
            if record["status"] == Status.PASSED and self._valid_manifest(record):
                decision.status = Status.PASSED
                return decision
            if record["status"] == Status.BLOCKED and record.get("code") == "prerequisite_result":
                return block(record["reason"], "prerequisite_result")
            if record["status"] == Status.FAILED and self._remaining(task, record) == 0:
                decision.status = Status.FAILED
                decision.reason = record["reason"]
                return decision
        adapter = self.adapters.get(task.adapter)
        if adapter and adapter.render and not allow_render:
            return block("Rendering requires explicit --allow-render", "render_disabled")
        return decision

    def plan(self, *, allow_render: bool = False) -> list[dict]:
        decisions = {}
        for task_id in self.registry.order:
            decisions[task_id] = self._decide(self.registry.tasks[task_id], decisions, allow_render)
        return [decision.row() for decision in decisions.values()]

    def approve(self, task_id: str, actor: str, note: str, *, input_hash: str | None = None) -> dict:
        with self.store.lock():
            task = self.registry.tasks.get(task_id)
            if task is None or not task.approval or task.unavailable:
                raise ValueError(f"Task is not an available approval gate: {task_id}")
            rows = {row["task_id"]: row for row in self.plan(allow_render=True)}
            if any(rows[dep]["status"] != Status.PASSED for dep in task.dependencies):
                raise ValueError(f"Prerequisites must pass before approving {task_id}")
            current_hash = rows[task_id]["input_hash"]
            if input_hash is not None and input_hash != current_hash:
                raise ValueError(f"Approval hash is stale for {task_id}; review the current plan")
            return self.approvals.grant(task_id, current_hash, actor, note)

    def _set(self, record: dict, status: Status, reason: str | None = None, code: str | None = None):
        transition(record, status, reason)
        record["reason"] = reason
        record["code"] = code
        self.store.put(record)

    def _record(self, decision: Decision) -> dict:
        if decision.record is None:
            decision.record = {
                **decision.row(), "status": Status.PENDING, "reason": None,
                "history": [{"status": Status.PENDING, "at": utc_now(), "reason": None}],
                "attempts": [], "manifest": None, "manifest_path": None,
            }
            self.store.put(decision.record)
        return decision.record

    @staticmethod
    def _remaining(task: Task, record: dict) -> int:
        if record.get("code") == "input_changed":
            return 0
        used = 0
        for attempt in reversed(record["attempts"]):
            if attempt.get("status") == Status.PASSED:
                break
            used += 1
        return max(0, task.max_attempts - used)

    def _prepare(self, decision: Decision) -> dict | None:
        record = self._record(decision)
        old = Status(record["status"])
        if old in (Status.RUNNING, Status.VALIDATING):
            error = "Previous workflow stopped before completing the attempt"
            record["attempts"][-1].update(status=Status.FAILED, error=error, finished_at=utc_now())
            self._set(record, Status.FAILED, error)
            old = Status.FAILED
            if self._remaining(decision.task, record) == 0:
                decision.status, decision.reason = old, error
        if decision.status == Status.BLOCKED:
            if old == Status.PASSED:
                self._set(record, Status.READY, "Previous pass could not be reused")
                old = Status.READY
            if old in (Status.PENDING, Status.READY):
                self._set(record, Status.BLOCKED, decision.reason, decision.code)
            elif old == Status.BLOCKED and (record["reason"], record["code"]) != (decision.reason, decision.code):
                self._set(record, Status.READY, "Reevaluating a blocked task")
                self._set(record, Status.BLOCKED, decision.reason, decision.code)
            return None
        if decision.status in (Status.PASSED, Status.FAILED):
            return None
        if old != Status.READY:
            self._set(record, Status.READY, "Previous pass could not be reused" if old == Status.PASSED else None)
        return record

    def _start(self, decision: Decision, record: dict):
        adapter = self.adapters.get(decision.task.adapter)
        number = len(record["attempts"]) + 1
        directory = self.store.path / "attempts" / decision.task.task_id / decision.input_hash / str(number)
        attempt = {"number": number, "status": Status.RUNNING, "started_at": utc_now(),
                   "finished_at": None, "exit_code": None, "error": None, "command": None, "log": None}
        record["attempts"].append(attempt)
        self._set(record, Status.RUNNING)
        try:
            self._check_inputs(decision)
            directory.mkdir(parents=True, exist_ok=False)
            if adapter:
                if adapter.dependency_command is None:
                    command = adapter.command(self.root, directory)
                else:
                    prerequisites = {}
                    for task_id, evidence in decision.dependencies.items():
                        dependency = self.store.get(task_id, evidence["input_hash"])
                        prerequisites[task_id] = (self.store.path / dependency["manifest_path"]).parent
                    command = adapter.dependency_command(self.root, directory, prerequisites)
                attempt["command"] = list(command)
                attempt["log"] = (directory / "command.log").relative_to(self.store.path).as_posix()
                self.store.put(record)
        except Exception as error:
            self._fail(record, error)
            return None
        return directory

    def _invoke(self, adapter: Adapter, attempt: dict) -> int:
        with (self.store.path / attempt["log"]).open("x", encoding="utf-8") as log:
            with subprocess.Popen(attempt["command"], cwd=self.root, stdin=subprocess.DEVNULL,
                                  stdout=log, stderr=subprocess.STDOUT, start_new_session=True) as process:
                try:
                    return process.wait(timeout=adapter.timeout)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    raise

    def _fail(self, record: dict, error: Exception):
        detail = f"{type(error).__name__}: {error}"
        record["attempts"][-1].update(status=Status.FAILED, error=detail, finished_at=utc_now())
        self._set(record, Status.FAILED, detail, "input_changed" if isinstance(error, InputChanged) else None)

    def _check_inputs(self, decision: Decision):
        checked = set()

        def check(task: Task, digest: str, dependencies: dict):
            if self._input_hash(task, dependencies) != digest:
                raise InputChanged(f"Inputs for {task.task_id} changed during execution")
            for task_id, evidence in dependencies.items():
                parent_hash = evidence["input_hash"]
                if (task_id, parent_hash) in checked:
                    continue
                parent = self.store.get(task_id, parent_hash)
                if (not parent or parent["status"] != Status.PASSED
                        or not self._valid_manifest(parent)
                        or self._dependency_artifacts(parent) != evidence["artifacts"]):
                    raise InputChanged(f"Evidence for {task_id} changed during execution")
                check(self.registry.tasks[task_id], parent_hash, parent["dependencies"])
                checked.add((task_id, parent_hash))

        check(decision.task, decision.input_hash, decision.dependencies)

    def _finish(self, decision: Decision, record: dict, directory: Path, future=None):
        task = decision.task
        attempt = record["attempts"][-1]
        try:
            if future is not None:
                attempt["exit_code"] = future.result()
                self._check_inputs(decision)
                if attempt["exit_code"] != 0:
                    raise RuntimeError(f"Command exited with status {attempt['exit_code']}; see {attempt['log']}")
            attempt["status"] = Status.VALIDATING
            self._set(record, Status.VALIDATING)
            paths = []
            if task.adapter:
                paths = ["command.log", *self.adapters[task.adapter].validate(directory)]
            files = []
            for name in sorted(set(paths)):
                path = (directory / name).resolve()
                if not path.is_relative_to(directory):
                    raise ValueError(f"Artifact escapes the attempt directory: {name}")
                files.append(self._artifact(path))
            self._check_inputs(decision)
            manifest = {
                "task_id": task.task_id, "input_hash": decision.input_hash,
                "attempt": attempt["number"], "artifacts": files,
                "approval": self.approvals.get(task.task_id, decision.input_hash) if task.approval else None,
            }
            manifest_path = directory / "manifest.json"
            with manifest_path.open("x", encoding="utf-8") as handle:
                json.dump(manifest, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            record.update(manifest=manifest, manifest_path=manifest_path.relative_to(self.store.path).as_posix())
            attempt.update(status=Status.PASSED, finished_at=utc_now(), manifest_path=record["manifest_path"])
            self._set(record, Status.PASSED)
        except PrerequisiteBlocked as error:
            attempt.update(status=Status.BLOCKED, error=str(error), finished_at=utc_now())
            self._set(record, Status.BLOCKED, str(error), "prerequisite_result")
        except Exception as error:
            self._fail(record, error)

    def run(self, *, jobs: int = 2, allow_render: bool = False) -> list[dict]:
        if jobs < 1:
            raise ValueError("jobs must be positive")
        decisions: dict[str, Decision] = {}
        pending: dict[str, Decision | None] = dict.fromkeys(self.registry.order)
        active = {}
        with self.store.lock(), ThreadPoolExecutor(max_workers=jobs) as pool:
            while pending or active:
                for task_id in list(pending):
                    if len(active) >= jobs:
                        break
                    task = self.registry.tasks[task_id]
                    if any(dep not in decisions for dep in task.dependencies):
                        continue
                    decision = pending[task_id] or self._decide(task, decisions, allow_render)
                    record = self._prepare(decision)
                    if record is None:
                        decisions[task_id] = decision
                        del pending[task_id]
                        continue
                    directory = self._start(decision, record)
                    if directory is not None and task.adapter is not None:
                        future = pool.submit(self._invoke, self.adapters[task.adapter], record["attempts"][-1])
                        active[future] = (decision, record, directory)
                        del pending[task_id]
                        continue
                    if directory is not None:
                        self._finish(decision, record, directory)
                    if record["status"] != Status.FAILED or not self._remaining(task, record):
                        decisions[task_id] = self._result(decision, record)
                        del pending[task_id]
                    else:
                        pending[task_id] = decision
                if active:
                    completed, _ = wait(active, return_when=FIRST_COMPLETED)
                    for future in completed:
                        decision, record, directory = active.pop(future)
                        self._finish(decision, record, directory, future)
                        task = decision.task
                        if record["status"] == Status.FAILED and self._remaining(task, record):
                            pending[task.task_id] = decision
                        else:
                            decisions[task.task_id] = self._result(decision, record)
            return [decisions[task_id].record for task_id in self.registry.order]

    @staticmethod
    def _result(decision: Decision, record: dict) -> Decision:
        decision.status = Status(record["status"])
        decision.reason = record["reason"]
        return decision
