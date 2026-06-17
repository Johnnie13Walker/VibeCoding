"""Команда генерации черновика поста."""

from __future__ import annotations

from ..formatters.telegram_content_post import format_telegram_content_post
from ..workflows.content_topics import ContentTopicsWorkflowDeps, run_content_post_workflow


def build_command(deps: ContentTopicsWorkflowDeps) -> dict[str, object]:
    def handler(payload: dict[str, object], context: dict[str, object] | None = None) -> dict[str, object]:
        topic_index = int(payload.get("topic_index") or 0)
        result = run_content_post_workflow(
            date_msk=str(payload.get("date_msk") or ""),
            period_key=str(payload.get("period_key") or "day"),
            topic_index=topic_index,
            tone=str(payload.get("tone") or "default"),
            deps=deps,
        )
        draft = result.get("draft")
        if draft is None:
            return {
                "text": str(result.get("text") or ""),
                "payload": result,
                "should_send": bool(result.get("should_send", True)),
            }
        return {
            "text": format_telegram_content_post(draft, topic_index=topic_index),
            "payload": draft,
            "should_send": bool(result.get("should_send", True)),
        }

    return {
        "name": "get_content_post",
        "aliases": ("/draft", "/write-post", "/harder", "/softer", "/business"),
        "handler": handler,
    }
