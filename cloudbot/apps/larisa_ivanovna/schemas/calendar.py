"""Контракты календарного слоя."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CalendarEvent:
    id: str
    title: str
    start_at_msk: str
    end_at_msk: str
    status: str = "confirmed"
    description: str = ""
    participants: tuple[str, ...] = field(default_factory=tuple)
    location: str = ""
    join_url: str = ""
    source: str = "calendar"


@dataclass(frozen=True)
class CreateCalendarEventInput:
    title: str
    start_at_msk: str
    end_at_msk: str = ""
    description: str = ""
    participants: tuple[str, ...] = field(default_factory=tuple)
    location: str = ""
    join_url: str = ""
    timezone: str = "Europe/Moscow"


@dataclass(frozen=True)
class CalendarDaySnapshot:
    date_msk: str
    meetings: tuple[CalendarEvent, ...] = field(default_factory=tuple)
    source_available: bool = False
    limitation: str | None = None
