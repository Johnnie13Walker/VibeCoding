"""Workflow погодного блока."""

from __future__ import annotations

from dataclasses import dataclass

from ..formatters.telegram_weather import format_telegram_weather
from ..providers.weather_provider import WeatherProvider


@dataclass(frozen=True)
class WeatherWorkflowDeps:
    weather_provider: WeatherProvider


def run_weather_workflow(
    *,
    date_msk: str,
    city: str,
    deps: WeatherWorkflowDeps,
) -> dict[str, object]:
    weather = deps.weather_provider.get_weather(date_msk, city)
    return {
        "text": format_telegram_weather(weather),
        "weather": weather,
    }
