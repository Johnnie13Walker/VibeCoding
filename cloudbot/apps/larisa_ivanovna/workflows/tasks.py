"""Workflow списка задач."""

from __future__ import annotations

from dataclasses import dataclass

from ..providers.tasks_provider import TasksProvider
from ..schemas.task import TaskDaySnapshot


@dataclass(frozen=True)
class TasksWorkflowDeps:
    tasks_provider: TasksProvider


def run_tasks_workflow(
    *,
    date_msk: str,
    deps: TasksWorkflowDeps,
) -> dict[str, object]:
    try:
        snapshot = deps.tasks_provider.get_day_snapshot(date_msk)
    except Exception as error:  # noqa: BLE001
        snapshot = TaskDaySnapshot(
            date_msk=date_msk,
            source_available=False,
            limitation=f"Задачи недоступны: {error}",
        )
    return {
        "snapshot": snapshot,
    }
