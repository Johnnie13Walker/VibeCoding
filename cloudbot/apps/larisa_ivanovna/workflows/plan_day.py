"""Workflow планирования дня."""

from __future__ import annotations

from ..schemas.brief import DayBriefRequest
from .daily_brief import DailyBriefWorkflowDeps, build_day_brief


def run_plan_day_workflow(
    request: DayBriefRequest,
    deps: DailyBriefWorkflowDeps,
) -> dict[str, object]:
    brief = build_day_brief(request, deps)
    lines = [
        f"План дня на {brief.date_msk}:",
        f"Фокус: {brief.focus}",
        "",
        "Приоритеты:",
    ]
    if brief.action_items:
        lines.extend(f"- {item}" for item in brief.action_items)
    else:
        lines.append("- Подтвержденных приоритетов пока нет.")
    if brief.limitations:
        lines.extend(["", "Ограничения:"])
        lines.extend(f"- {item}" for item in brief.limitations)
    return {
        "text": "\n".join(lines),
        "brief": brief,
    }
