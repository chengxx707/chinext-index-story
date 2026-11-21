"""Task definitions and dependency validation for the production workflow."""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from pathlib import Path


@dataclass(frozen=True)
class Task:
    task_id: str
    lane: str
    title: str
    dependencies: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    adapter: str | None = None
    approval: bool = False
    unavailable: str | None = None
    max_attempts: int = 1


class Registry:
    def __init__(self, tasks: Iterable[Task]):
        self.tasks: dict[str, Task] = {}
        for task in tasks:
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", task.task_id):
                raise ValueError(f"Invalid task ID: {task.task_id!r}")
            if task.task_id in self.tasks:
                raise ValueError(f"Duplicate task ID: {task.task_id}")
            if task.lane not in {"A", "B"}:
                raise ValueError(f"{task.task_id} has an unknown lane: {task.lane}")
            if type(task.max_attempts) is not int or not 1 <= task.max_attempts <= 3:
                raise ValueError(f"{task.task_id} must allow one to three attempts")
            if task.unavailable and task.adapter is not None:
                raise ValueError(f"{task.task_id} is unavailable but has an executable adapter")
            if task.adapter is None and not (task.approval or task.unavailable):
                raise ValueError(f"{task.task_id} has no adapter, approval or availability reason")
            if len(task.dependencies) != len(set(task.dependencies)):
                raise ValueError(f"{task.task_id} lists the same dependency more than once")
            self.tasks[task.task_id] = task

        graph = {task_id: task.dependencies for task_id, task in self.tasks.items()}
        for task_id, dependencies in graph.items():
            unknown = set(dependencies) - self.tasks.keys()
            if unknown:
                raise ValueError(f"{task_id} has unknown dependencies: {', '.join(sorted(unknown))}")
        try:
            self.order = tuple(TopologicalSorter(graph).static_order())
        except CycleError as error:
            raise ValueError(f"Task dependency cycle: {' -> '.join(error.args[1])}") from error


def load_registry() -> Registry:
    records = json.loads(Path(__file__).with_name("production.json").read_text(encoding="utf-8"))
    for record in records:
        for attribute in ("dependencies", "inputs"):
            if attribute in record:
                entries = record[attribute]
                if not isinstance(entries, list) or not all(isinstance(entry, str) for entry in entries):
                    raise ValueError(f"{record.get('task_id')} has invalid {attribute}")
                record[attribute] = tuple(entries)
    return Registry(Task(**record) for record in records)
