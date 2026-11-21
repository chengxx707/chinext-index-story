"""Local workflow state and checked transitions."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
import fcntl
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Iterator


class Status(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    VALIDATING = "VALIDATING"
    PASSED = "PASSED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


_TRANSITIONS = {
    Status.PENDING: {Status.READY, Status.BLOCKED},
    Status.READY: {Status.RUNNING, Status.BLOCKED},
    Status.RUNNING: {Status.VALIDATING, Status.FAILED},
    Status.VALIDATING: {Status.PASSED, Status.FAILED, Status.BLOCKED},
    Status.PASSED: {Status.READY},
    Status.BLOCKED: {Status.READY},
    Status.FAILED: {Status.READY},
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def transition(record: dict, status: Status, reason: str | None = None) -> None:
    current = Status(record["status"])
    target = Status(status)
    if target not in _TRANSITIONS[current]:
        raise ValueError(f"Invalid workflow transition {current} -> {target}")
    record["history"].append({"status": target.value, "at": utc_now(), "reason": reason})
    record["status"] = target.value


class WorkflowBusyError(RuntimeError):
    """Another process is updating the state directory."""


def record_path(directory: Path, task_id: str, input_hash: str) -> Path:
    if re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", task_id) is None:
        raise ValueError(f"Invalid task id {task_id!r}")
    if re.fullmatch(r"[a-f0-9]{64}", input_hash) is None:
        raise ValueError(f"Invalid SHA-256 digest {input_hash!r}")
    return directory / task_id / f"{input_hash}.json"


def read_record(path: Path) -> dict | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if (
        not isinstance(record, dict)
        or record.get("task_id") != path.parent.name
        or record.get("input_hash") != path.stem
    ):
        raise ValueError(f"Record identity does not match {path}")
    return record


def write_record(path: Path, record: dict, *, replace: bool = True) -> None:
    """Write one complete record, optionally refusing to replace an existing file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=".record-", delete=False
    ) as temporary:
        candidate = Path(temporary.name)
        try:
            json.dump(record, temporary, ensure_ascii=False, indent=2, allow_nan=False)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            if replace:
                candidate.replace(path)
            else:
                os.link(candidate, path)
        finally:
            candidate.unlink(missing_ok=True)


class Store:
    """Persist one execution record per task and input hash."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self._records = self.path / "records"

    @contextmanager
    def lock(self) -> Iterator[None]:
        """Hold across a workflow run or an approval update."""
        self.path.mkdir(parents=True, exist_ok=True)
        with (self.path / ".lock").open("a", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise WorkflowBusyError(f"Workflow state is busy: {self.path}") from error
            yield

    def get(self, task_id: str, input_hash: str) -> dict | None:
        return read_record(record_path(self._records, task_id, input_hash))

    def put(self, record: dict) -> None:
        Status(record["status"])
        write_record(record_path(self._records, record["task_id"], record["input_hash"]), record)

    def records(self) -> list[dict]:
        records = []
        for path in sorted(self._records.glob("*/*.json")):
            record = read_record(path)
            if record is not None:
                records.append(record)
        return records
