"""Workflow тем для постов через контур Ларисы Ивановны."""

from __future__ import annotations

from typing import Any

from cloudbot.workflows.larisa_runtime import build_content_topics_payload, run_larisa_command


def run(context: dict[str, Any]) -> dict[str, Any]:
    return run_larisa_command(
        "get_content_topics",
        context=context,
        payload=build_content_topics_payload(context),
    )
