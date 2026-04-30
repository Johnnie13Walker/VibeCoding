"""Workflow веб-поиска через контур Ларисы Ивановны."""

from __future__ import annotations

from typing import Any

from cloudbot.workflows.larisa_runtime import build_search_payload, run_larisa_command


def run(context: dict[str, Any]) -> dict[str, Any]:
    return run_larisa_command(
        "get_web_search",
        context=context,
        payload=build_search_payload(context),
    )
