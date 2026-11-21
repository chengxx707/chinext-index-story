"""A workflow must form a single valid graph across both production lanes."""

import pytest

from orchestration.adapters import ADAPTERS
from orchestration.registry import Registry, Task, load_registry


def test_registry_rejects_cross_lane_cycle():
    with pytest.raises(ValueError, match="dependency cycle"):
        Registry([
            Task("A.first", "A", "First", dependencies=("B.second",), adapter="check"),
            Task("B.second", "B", "Second", dependencies=("A.first",), adapter="check"),
        ])


def test_registry_rejects_unknown_dependency():
    with pytest.raises(ValueError, match="unknown dependencies"):
        Registry([
            Task("A.first", "A", "First", dependencies=("A.missing",), adapter="check"),
        ])


def test_registry_rejects_duplicate_task_id():
    task = Task("A.first", "A", "First", adapter="check")
    with pytest.raises(ValueError, match="Duplicate task ID"):
        Registry([task, task])


def test_production_registry_has_both_lanes_and_valid_dependency_order():
    registry = load_registry()
    assert {task.lane for task in registry.tasks.values()} == {"A", "B"}
    assert any(task.approval for task in registry.tasks.values())
    index = {task_id: i for i, task_id in enumerate(registry.order)}
    assert index.keys() == registry.tasks.keys()
    for task in registry.tasks.values():
        assert all(index[dependency] < index[task.task_id] for dependency in task.dependencies)


def test_production_render_adapters_are_protected_and_have_no_automatic_retries():
    registry = load_registry()
    for task in registry.tasks.values():
        if task.adapter and ADAPTERS[task.adapter].render:
            assert task.approval
            assert task.max_attempts == 1
    assert registry.tasks["A.full-render"].unavailable
    assert registry.tasks["A.full-render"].adapter is None
