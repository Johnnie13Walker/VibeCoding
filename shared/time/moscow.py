"""Общие утилиты нормализации времени в Europe/Moscow."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MSK_TIMEZONE = "Europe/Moscow"
MOSCOW_TZ = ZoneInfo(MSK_TIMEZONE)


def to_moscow_datetime(value: str, *, source_timezone: str | None = None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_resolve_timezone(source_timezone))

    return parsed.astimezone(MOSCOW_TZ)


def normalize_to_moscow(value: str, *, source_timezone: str | None = None) -> str:
    parsed = to_moscow_datetime(value, source_timezone=source_timezone)
    if parsed is None:
        return str(value or "").strip()
    return parsed.isoformat()


def extract_moscow_clock(value: str, *, source_timezone: str | None = None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    parsed = to_moscow_datetime(raw, source_timezone=source_timezone)
    if parsed is None:
        return raw[:5]
    return parsed.strftime("%H:%M")


def ensure_moscow_datetime(value: datetime | None = None) -> datetime:
    current = value or datetime.now(MOSCOW_TZ)
    if current.tzinfo is None:
        return current.replace(tzinfo=MOSCOW_TZ)
    return current.astimezone(MOSCOW_TZ)


def _resolve_timezone(name: str | None) -> ZoneInfo:
    raw = str(name or "").strip()
    if not raw:
        return MOSCOW_TZ
    try:
        return ZoneInfo(raw)
    except ZoneInfoNotFoundError:
        return MOSCOW_TZ
