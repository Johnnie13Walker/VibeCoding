"""Команда midday replan."""

from __future__ import annotations

from ..workflows.midday_replan import MiddayReplanWorkflowDeps, run_midday_replan_workflow


def build_command(deps: MiddayReplanWorkflowDeps) -> dict[str, object]:
    def handler(payload: dict[str, object], context: dict[str, object] | None = None) -> dict[str, object]:
        result = run_midday_replan_workflow(
            date_msk=str(payload.get("date_msk") or ""),
            now_hour_msk=int(payload.get("now_hour_msk") or 14),
            deps=deps,
        )
        return {
            "text": str(result.get("text") or ""),
            "payload": result,
            "should_send": bool(result.get("should_send", True)),
            "skip_reason": str(result.get("skip_reason") or ""),
        }

    return {
        "name": "get_midday_replan",
        "aliases": tuple(),
        "handler": handler,
    }
