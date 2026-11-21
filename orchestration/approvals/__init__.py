"""Explicit local human decisions bound to one workflow input."""

from pathlib import Path

from orchestration.state import read_record, record_path, utc_now, write_record


class ApprovalStore:
    """Record approval for a specific task and SHA-256 fingerprint."""

    def __init__(self, path: Path) -> None:
        self._directory = path.resolve() / "approvals"

    def get(self, task_id: str, input_hash: str) -> dict | None:
        return read_record(record_path(self._directory, task_id, input_hash))

    def grant(self, task_id: str, input_hash: str, actor: str, note: str) -> dict:
        actor = actor.strip()
        note = note.strip()
        if not actor or not note:
            raise ValueError("Approval requires a human approver and a decision note")
        path = record_path(self._directory, task_id, input_hash)
        approval = {"task_id": task_id, "input_hash": input_hash, "actor": actor,
                    "note": note, "at": utc_now()}
        try:
            write_record(path, approval, replace=False)
        except FileExistsError:
            saved = read_record(path)
            if saved is None:
                raise ValueError(f"Approval was removed during the update: {path}") from None
            return saved
        return approval
