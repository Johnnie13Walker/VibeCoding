"""Команда погодного блока."""

from __future__ import annotations

from ..config import COMMAND_ALIASES, DEFAULT_CONFIG
from ..workflows.weather import WeatherWorkflowDeps, run_weather_workflow


def build_command(deps: WeatherWorkflowDeps) -> dict[str, object]:
    def handler(payload: dict[str, str], context: dict[str, object] | None = None) -> dict[str, object]:
        result = run_weather_workflow(
            date_msk=str(payload.get("date_msk") or ""),
            city=str(payload.get("city") or DEFAULT_CONFIG.default_city),
            deps=deps,
        )
        return {
            "text": str(result.get("text") or ""),
            "payload": result,
        }

    return {
        "name": "get_weather",
        "aliases": COMMAND_ALIASES["get_weather"],
        "handler": handler,
    }
