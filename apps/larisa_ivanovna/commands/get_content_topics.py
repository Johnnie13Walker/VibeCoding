"""Команда генерации тем для постов."""

from __future__ import annotations

from ..formatters.telegram_content_topics import format_telegram_content_topics
from ..workflows.content_topics import ContentTopicsWorkflowDeps, run_content_topics_workflow


def build_command(deps: ContentTopicsWorkflowDeps) -> dict[str, object]:
    def handler(payload: dict[str, object], context: dict[str, object] | None = None) -> dict[str, object]:
        result = run_content_topics_workflow(
            date_msk=str(payload.get("date_msk") or ""),
            period_key=str(payload.get("period_key") or "day"),
            deps=deps,
        )
        digest = result["digest"]
        return {
            "text": format_telegram_content_topics(digest),
            "payload": digest,
            "should_send": bool(result.get("should_send", True)),
            "skip_reason": str(result.get("skip_reason") or ""),
        }

    return {
        "name": "get_content_topics",
        "aliases": ("/topics", "/posts", "/ideas"),
        "handler": handler,
    }
