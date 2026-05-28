"""Telegram-friendly форматирование погоды."""

from __future__ import annotations

from ..schemas.brief import WeatherSnapshot


def format_telegram_weather(weather: WeatherSnapshot) -> str:
    if not weather.source_available:
        return weather.limitation or "Источник погоды недоступен."

    parts = [part for part in (weather.temperature_text, weather.summary) if part]
    if weather.alerts:
        parts.append(f"Важно: {', '.join(weather.alerts)}")
    return ", ".join(parts) if parts else "Погодный блок пуст."
