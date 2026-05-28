"""Workflow дня: adapter к агенту Ларисы Ивановны."""

from __future__ import annotations

from typing import Any

from cloudbot.workflows.larisa_runtime import build_day_brief_request, run_larisa_command


def run(context: dict[str, Any]) -> dict[str, Any]:
    return run_larisa_command(
        "get_day_brief",
        context=context,
        payload=build_day_brief_request(),
    )
