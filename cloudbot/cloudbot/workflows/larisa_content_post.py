"""Workflow черновика поста через контур Ларисы Ивановны."""

from __future__ import annotations

from typing import Any

from cloudbot.workflows.larisa_runtime import build_content_post_payload, run_larisa_command


def run(context: dict[str, Any]) -> dict[str, Any]:
    return run_larisa_command(
        "get_content_post",
        context=context,
        payload=build_content_post_payload(context),
    )
