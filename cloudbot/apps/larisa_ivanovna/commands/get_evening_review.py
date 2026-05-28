"""Команда вечернего обзора."""

from __future__ import annotations

from ..workflows.evening_review import EveningReviewWorkflowDeps, run_evening_review_workflow


def build_command(deps: EveningReviewWorkflowDeps) -> dict[str, object]:
    def handler(payload: dict[str, object], context: dict[str, object] | None = None) -> dict[str, object]:
        result = run_evening_review_workflow(
            date_msk=str(payload.get("date_msk") or ""),
            deps=deps,
        )
        return {
            "text": str(result.get("text") or ""),
            "payload": result,
            "should_send": bool(result.get("should_send", True)),
            "skip_reason": str(result.get("skip_reason") or ""),
        }

    return {
        "name": "get_evening_review",
        "aliases": tuple(),
        "handler": handler,
    }
