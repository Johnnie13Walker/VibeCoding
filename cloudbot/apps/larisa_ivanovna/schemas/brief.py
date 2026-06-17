"""Контракты brief и планирования дня."""

from __future__ import annotations

from dataclasses import dataclass, field

from .calendar import CalendarEvent
from .task import TaskItem


@dataclass(frozen=True)
class DayBriefRequest:
    date_msk: str
    weekday_msk: str


@dataclass(frozen=True)
class FreeWindow:
    start_at_msk: str
    end_at_msk: str
    source: str = "calendar"


@dataclass(frozen=True)
class FocusBlock:
    start_at_msk: str
    end_at_msk: str
    title: str
    source: str = "larisa_focus"


@dataclass(frozen=True)
class WeatherSnapshot:
    city: str
    summary: str
    temperature_text: str = ""
    alerts: tuple[str, ...] = field(default_factory=tuple)
    source_available: bool = False
    limitation: str | None = None
    source: str = "weather"


@dataclass(frozen=True)
class DayBrief:
    date_msk: str
    weekday_msk: str
    timezone: str
    meetings: tuple[CalendarEvent, ...] = field(default_factory=tuple)
    tasks_for_today: tuple[TaskItem, ...] = field(default_factory=tuple)
    overdue_tasks: tuple[TaskItem, ...] = field(default_factory=tuple)
    free_windows: tuple[FreeWindow, ...] = field(default_factory=tuple)
    focus_blocks: tuple[FocusBlock, ...] = field(default_factory=tuple)
    weather: WeatherSnapshot = field(default_factory=lambda: WeatherSnapshot(city="Москва", summary=""))
    focus: str = ""
    action_items: tuple[str, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)
