"""Execution state and approval decisions survive reopening their stores."""

import pytest

from orchestration.approvals import ApprovalStore
from orchestration.state import Status, Store, WorkflowBusyError, transition


def test_state_persists_valid_transition_history(tmp_path):
    record = {"task_id": "A.check", "input_hash": "a" * 64, "status": "PENDING", "history": []}
    store = Store(tmp_path)
    for status in (Status.READY, Status.RUNNING, Status.VALIDATING, Status.PASSED):
        transition(record, status)
        store.put(record)
    saved = Store(tmp_path).get("A.check", "a" * 64)
    assert saved["status"] == "PASSED"
    assert [event["status"] for event in saved["history"]] == [
        "READY", "RUNNING", "VALIDATING", "PASSED",
    ]
    assert Store(tmp_path).records() == [saved]


@pytest.mark.parametrize(("source", "target"), [
    (Status.PENDING, Status.RUNNING),
    (Status.BLOCKED, Status.RUNNING),
    (Status.READY, Status.PASSED),
    (Status.RUNNING, Status.PASSED),
    (Status.FAILED, Status.PASSED),
])
def test_illegal_state_transition_leaves_record_untouched(source, target):
    record = {"status": source.value, "history": []}
    with pytest.raises(ValueError, match="Invalid workflow transition"):
        transition(record, target)
    assert record == {"status": source.value, "history": []}


def test_state_lock_rejects_a_second_writer_then_releases(tmp_path):
    first, second = Store(tmp_path), Store(tmp_path)
    with first.lock():
        with pytest.raises(WorkflowBusyError), second.lock():
            pytest.fail("Second writer acquired the workflow state lock")
    with second.lock():
        assert second.records() == []


def test_approval_is_immutable_and_bound_to_task_and_content(tmp_path):
    approvals = ApprovalStore(tmp_path)
    approved = approvals.grant("A.review", "a" * 64, "Director", "Representative reviewed")
    reopened = ApprovalStore(tmp_path)
    assert approved == reopened.get("A.review", "a" * 64)
    assert approved == reopened.grant("A.review", "a" * 64, "Other", "Do not overwrite")
    assert reopened.get("A.review", "b" * 64) is None
    assert reopened.get("B.review", "a" * 64) is None
