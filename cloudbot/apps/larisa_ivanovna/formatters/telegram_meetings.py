"""Telegram-friendly форматирование списка встреч."""

from __future__ import annotations

from ..schemas.calendar import CalendarDaySnapshot
from ..timezone import extract_moscow_clock


def format_telegram_meetings(snapshot: CalendarDaySnapshot) -> str:
    if not snapshot.source_available:
        return snapshot.limitation or "Календарь недоступен."
    if not snapshot.meetings:
        return "На сегодня подтвержденных встреч нет."
    lines = ["Встречи на сегодня:"]
    for item in snapshot.meetings:
        lines.append(
            f"- {extract_moscow_clock(item.start_at_msk)}-{extract_moscow_clock(item.end_at_msk)} {item.title}"
        )
    return "\n".join(lines)
