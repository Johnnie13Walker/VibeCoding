"""Workflow погоды через контур Ларисы Ивановны."""

from __future__ import annotations

from typing import Any

from cloudbot.workflows.larisa_runtime import build_day_brief_request, extract_message_tail, run_larisa_command


def run(context: dict[str, Any]) -> dict[str, Any]:
    request = build_day_brief_request()
    city = extract_message_tail(context) or "Москва"
    return run_larisa_command(
        "get_weather",
        context=context,
        payload={
            "date_msk": request.date_msk,
            "city": city,
        },
    )
