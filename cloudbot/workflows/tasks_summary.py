"""Workflow задач через контур Ларисы Ивановны."""

from __future__ import annotations

from typing import Any

from cloudbot.workflows.larisa_runtime import build_day_brief_request, run_larisa_command


def run(context: dict[str, Any]) -> dict[str, Any]:
    request = build_day_brief_request()
    return run_larisa_command(
        "get_tasks",
        context=context,
        payload={"date_msk": request.date_msk},
    )
