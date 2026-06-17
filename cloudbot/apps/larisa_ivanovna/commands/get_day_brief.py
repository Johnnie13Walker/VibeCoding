"""Команда получения brief дня."""

from __future__ import annotations

from ..config import COMMAND_ALIASES
from ..formatters.telegram_brief import format_telegram_brief
from ..schemas.brief import DayBriefRequest
from ..workflows.daily_brief import DailyBriefWorkflowDeps, build_day_brief


def build_command(deps: DailyBriefWorkflowDeps) -> dict[str, object]:
    def handler(payload: DayBriefRequest, context: dict[str, object] | None = None) -> dict[str, object]:
        brief = build_day_brief(payload, deps)
        return {
            "text": format_telegram_brief(brief),
            "payload": brief,
        }

    return {
        "name": "get_day_brief",
        "aliases": COMMAND_ALIASES["get_day_brief"],
        "handler": handler,
    }
