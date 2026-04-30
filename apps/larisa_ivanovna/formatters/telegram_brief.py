"""Telegram-friendly форматирование brief дня."""

from __future__ import annotations

from ..schemas.brief import DayBrief
from ..schemas.calendar import CalendarEvent
from ..schemas.task import TaskItem
from ..timezone import extract_moscow_clock


def _extract_clock(value: str) -> str:
    return extract_moscow_clock(value)


def _format_time_range(start_at_msk: str, end_at_msk: str) -> str:
    return f"{_extract_clock(start_at_msk)}-{_extract_clock(end_at_msk)}"


def _render_meetings(meetings: tuple[CalendarEvent, ...]) -> str:
    if not meetings:
        return "Нет подтвержденных встреч."
    return "\n".join(
        _render_meeting_line(item)
        for item in meetings
    )


def _render_meeting_line(item: CalendarEvent) -> str:
    details: list[str] = []
    if item.participants:
        participants = ", ".join(participant for participant in item.participants if participant)
        if participants:
            details.append(f"<b>{participants}</b>")
    if item.location:
        details.append(item.location)
    suffix = f" ({'; '.join(details)})" if details else ""
    return f"- <b>{_format_time_range(item.start_at_msk, item.end_at_msk)}</b> {item.title}{suffix}"


def _render_task_line(item: TaskItem) -> str:
    details: list[str] = []
    if item.due_at_msk and "T" in item.due_at_msk:
        clock = _extract_clock(item.due_at_msk)
        if clock:
            details.append(clock)
    if item.priority:
        details.append(str(item.priority))
    if item.source:
        details.append(str(item.source))
    suffix = f" ({', '.join(details)})" if details else ""
    return f"- {item.title}{suffix}"


def format_telegram_brief(brief: DayBrief) -> str:
    lines = [
        f"<b>{brief.date_msk}, {brief.weekday_msk}</b>",
        "",
        "🗓️ <b>Календарь дня:</b>",
        _render_meetings(brief.meetings),
        "",
        "⏰ <b>Просроченные задачи:</b>",
    ]

    if brief.overdue_tasks:
        lines.extend(_render_task_line(item) for item in brief.overdue_tasks)
    else:
        lines.append("- Нет просроченных задач.")

    lines.extend(
        [
            "",
            "✅ <b>Задачи на сегодня:</b>",
        ]
    )

    if brief.tasks_for_today:
        lines.extend(_render_task_line(item) for item in brief.tasks_for_today)
    else:
        lines.append("- На сегодня открытых задач нет.")

    if brief.limitations:
        lines.extend(["", "⚠️ <b>Ограничения:</b>"])
        lines.extend(f"- {item}" for item in brief.limitations)

    return "\n".join(lines)
