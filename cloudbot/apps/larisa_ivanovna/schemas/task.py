"""Контракты task-слоя."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TaskItem:
    id: str
    title: str
    bucket: str
    priority: str = "medium"
    due_at_msk: str = ""
    notes: str = ""
    source: str = "todo"


@dataclass(frozen=True)
class TaskDaySnapshot:
    date_msk: str
    tasks_for_today: tuple[TaskItem, ...] = field(default_factory=tuple)
    overdue_tasks: tuple[TaskItem, ...] = field(default_factory=tuple)
    source_available: bool = False
    limitation: str | None = None
