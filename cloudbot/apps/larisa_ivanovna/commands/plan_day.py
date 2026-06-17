"""Команда планирования дня."""

from __future__ import annotations

from ..config import COMMAND_ALIASES
from ..schemas.brief import DayBriefRequest
from ..workflows.daily_brief import DailyBriefWorkflowDeps
from ..workflows.plan_day import run_plan_day_workflow


def build_command(deps: DailyBriefWorkflowDeps) -> dict[str, object]:
    def handler(payload: DayBriefRequest, context: dict[str, object] | None = None) -> dict[str, object]:
        result = run_plan_day_workflow(payload, deps)
        return {
            "text": str(result.get("text") or ""),
            "payload": result,
        }

    return {
        "name": "plan_day",
        "aliases": COMMAND_ALIASES["plan_day"],
        "handler": handler,
    }
