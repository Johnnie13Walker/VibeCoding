"""Midday replan для Ларисы Ивановны."""

from __future__ import annotations

from dataclasses import dataclass

from ..providers.tasks_provider import TasksProvider
from ..schemas.task import TaskDaySnapshot, TaskItem


@dataclass(frozen=True)
class MiddayReplanWorkflowDeps:
    tasks_provider: TasksProvider


def run_midday_replan_workflow(
    *,
    date_msk: str,
    now_hour_msk: int,
    deps: MiddayReplanWorkflowDeps,
) -> dict[str, object]:
    try:
        snapshot = deps.tasks_provider.get_day_snapshot(date_msk)
    except Exception as error:  # noqa: BLE001
        snapshot = TaskDaySnapshot(
            date_msk=date_msk,
            source_available=False,
            limitation=f"Задачи недоступны: {error}",
        )

    if not snapshot.source_available:
        return {
            "text": snapshot.limitation or "Источник задач недоступен.",
            "snapshot": snapshot,
            "should_send": True,
        }

    open_tasks = _sort_tasks((*snapshot.overdue_tasks, *snapshot.tasks_for_today))
    capacity = max(1, round(max(0, 20 - int(now_hour_msk)) * 0.75))
    remaining = len(open_tasks)
    if remaining <= capacity:
        return {
            "text": f"midday_skip_balanced remaining={remaining} cap={capacity}",
            "snapshot": snapshot,
            "scope": {"remaining": remaining, "capacity": capacity},
            "should_send": False,
            "skip_reason": "balanced",
        }

    doable = open_tasks[:capacity]
    postpone = open_tasks[capacity:]
    low_priority_drop = [task for task in postpone if _priority_bucket(task.priority) >= 3]

    lines = [
        "⚠️ Обновление плана",
        f"Осталось {remaining} задач.",
        f"Реально успеть сегодня ≈ {capacity}.",
        "",
        "Реально сегодня:",
        f"✔ сделать {len(doable)}",
        f"⏳ перенести {len(postpone)}",
        f"❌ убрать {len(low_priority_drop)} (низкий приоритет)",
        "",
        "🎯 Сфокусируйся:",
    ]
    if doable:
        lines.extend(f"- {task.title}" for task in doable[:3])
    else:
        lines.append("- Закрой хотя бы одну приоритетную задачу.")

    return {
        "text": "\n".join(lines),
        "snapshot": snapshot,
        "scope": {"remaining": remaining, "capacity": capacity},
        "should_send": True,
    }


def _sort_tasks(tasks: tuple[TaskItem, ...]) -> tuple[TaskItem, ...]:
    return tuple(
        sorted(
            tasks,
            key=lambda item: (
                0 if item.bucket == "overdue" else 1,
                _priority_bucket(item.priority),
                item.title.lower(),
            ),
        )
    )


def _priority_bucket(raw_priority: str) -> int:
    prepared = str(raw_priority or "").strip().lower()
    if prepared.isdigit():
        return max(1, 5 - int(prepared))
    if prepared in {"p1", "high", "highest"}:
        return 1
    if prepared in {"p2", "medium"}:
        return 2
    if prepared in {"p3", "low"}:
        return 3
    return 4
