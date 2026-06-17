"""Команда веб-поиска Ларисы Ивановны."""

from __future__ import annotations

from ..config import COMMAND_ALIASES
from ..workflows.search import run_search_workflow


def build_command() -> dict[str, object]:
    def handler(payload: dict[str, str], context: dict[str, object] | None = None) -> dict[str, object]:
        result = run_search_workflow(
            query=str(payload.get("query") or ""),
            chat_id=str(payload.get("chat_id") or ""),
            user_id=str(payload.get("user_id") or ""),
        )
        return {
            "text": str(result.get("text") or ""),
            "payload": result,
        }

    return {
        "name": "get_web_search",
        "aliases": COMMAND_ALIASES["get_web_search"],
        "handler": handler,
    }
