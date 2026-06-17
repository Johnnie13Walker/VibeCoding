"""Telegram-friendly форматирование задач."""

from __future__ import annotations

from ..schemas.task import TaskDaySnapshot


def format_telegram_tasks(snapshot: TaskDaySnapshot) -> str:
    if not snapshot.source_available:
        return snapshot.limitation or "Источник задач недоступен."
    lines = ["Задачи на сегодня:"]
    if snapshot.tasks_for_today:
        lines.extend(f"- Сегодня: {item.title}" for item in snapshot.tasks_for_today)
    else:
        lines.append("- Сегодня: нет подтвержденных задач.")
    if snapshot.overdue_tasks:
        lines.extend(f"- Просрочено: {item.title}" for item in snapshot.overdue_tasks)
    else:
        lines.append("- Просрочено: нет.")
    return "\n".join(lines)
