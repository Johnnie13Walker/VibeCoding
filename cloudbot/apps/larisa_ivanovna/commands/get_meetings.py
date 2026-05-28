"""Команда списка встреч."""

from __future__ import annotations

from ..config import COMMAND_ALIASES
from ..formatters.telegram_meetings import format_telegram_meetings
from ..workflows.meetings import MeetingsWorkflowDeps, run_meetings_workflow


def build_command(deps: MeetingsWorkflowDeps) -> dict[str, object]:
    def handler(payload: dict[str, str], context: dict[str, object] | None = None) -> dict[str, object]:
        result = run_meetings_workflow(date_msk=str(payload.get("date_msk") or ""), deps=deps)
        snapshot = result["snapshot"]
        return {
            "text": format_telegram_meetings(snapshot),
            "payload": result,
        }

    return {
        "name": "get_meetings",
        "aliases": COMMAND_ALIASES["get_meetings"],
        "handler": handler,
    }
