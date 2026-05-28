"""Workflow списка встреч."""

from __future__ import annotations

from dataclasses import dataclass

from ..providers.calendar_provider import CalendarProvider
from ..schemas.calendar import CalendarDaySnapshot


@dataclass(frozen=True)
class MeetingsWorkflowDeps:
    calendar_provider: CalendarProvider


def run_meetings_workflow(
    *,
    date_msk: str,
    deps: MeetingsWorkflowDeps,
) -> dict[str, object]:
    try:
        snapshot = deps.calendar_provider.get_day_snapshot(date_msk)
    except Exception as error:  # noqa: BLE001
        snapshot = CalendarDaySnapshot(
            date_msk=date_msk,
            source_available=False,
            limitation=f"Календарь недоступен: {error}",
        )
    return {
        "snapshot": snapshot,
    }
