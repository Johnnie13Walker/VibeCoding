"""Погодные адаптеры Ларисы Ивановны."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..schemas.brief import WeatherSnapshot

OPEN_METEO_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_RETRY_DELAYS_SEC = (0.0, 1.0, 3.0)
OPEN_METEO_USER_AGENT = "Cloudbot-Larisa/1.0 (+weather)"
CITY_COORDINATES = {
    "москва": (55.7558, 37.6173),
}
WEATHER_CODES = {
    0: "ясно",
    1: "преимущественно ясно",
    2: "переменная облачность",
    3: "пасмурно",
    45: "туман",
    48: "изморозь",
    51: "морось",
    53: "морось",
    55: "морось",
    61: "дождь",
    63: "дождь",
    65: "сильный дождь",
    71: "снег",
    73: "снег",
    75: "сильный снег",
    80: "ливни",
    81: "ливни",
    82: "сильные ливни",
    95: "гроза",
}


class WeatherProvider(ABC):
    @abstractmethod
    def get_weather(self, date_msk: str, city: str) -> WeatherSnapshot:
        raise NotImplementedError


class NullWeatherProvider(WeatherProvider):
    def get_weather(self, date_msk: str, city: str) -> WeatherSnapshot:
        return WeatherSnapshot(
            city=city,
            summary="Источник погоды не подключен.",
            source_available=False,
            limitation="Weather provider не подтвержден в этом контуре.",
        )


class OpenMeteoWeatherProvider(WeatherProvider):
    def __init__(self, *, timeout_sec: int = 15, retry_delays_sec: tuple[float, ...] = OPEN_METEO_RETRY_DELAYS_SEC) -> None:
        self.timeout_sec = int(timeout_sec)
        self.retry_delays_sec = tuple(float(delay) for delay in retry_delays_sec) or (0.0,)

    def get_weather(self, date_msk: str, city: str) -> WeatherSnapshot:
        normalized_city = str(city or "Москва").strip() or "Москва"
        coordinates = CITY_COORDINATES.get(normalized_city.lower())
        if coordinates is None:
            return WeatherSnapshot(
                city=normalized_city,
                summary="Пока поддерживается только погодный блок по Москве.",
                source_available=False,
                limitation=f"Координаты для города {normalized_city} не настроены.",
            )

        params = urlencode(
            {
                "latitude": coordinates[0],
                "longitude": coordinates[1],
                "current_weather": "true",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "Europe/Moscow",
                "forecast_days": 1,
            }
        )
        request = Request(
            f"{OPEN_METEO_ENDPOINT}?{params}",
            headers={"User-Agent": OPEN_METEO_USER_AGENT},
        )

        payload: dict[str, Any] | None = None
        last_error: Exception | None = None
        for attempt, delay_sec in enumerate(self.retry_delays_sec, start=1):
            if delay_sec > 0:
                time.sleep(delay_sec)
            try:
                with urlopen(request, timeout=self.timeout_sec) as response:  # noqa: S310
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except Exception as error:  # noqa: BLE001
                last_error = error
                if attempt >= len(self.retry_delays_sec):
                    break

        if payload is None:
            return WeatherSnapshot(
                city=normalized_city,
                summary="Не удалось загрузить погоду.",
                source_available=False,
                limitation=f"Open-Meteo недоступен: {last_error}",
            )

        current = payload.get("current_weather") or {}
        daily = payload.get("daily") or {}
        current_temp = current.get("temperature")
        weather_code = int(current.get("weathercode") or 0)
        max_temp = _first_number(daily.get("temperature_2m_max"))
        min_temp = _first_number(daily.get("temperature_2m_min"))
        precipitation = _first_number(daily.get("precipitation_probability_max"))

        summary = WEATHER_CODES.get(weather_code, "без уточнения по условиям")
        temperature_parts: list[str] = []
        if current_temp is not None:
            temperature_parts.append(f"сейчас {round(float(current_temp))}°C")
        if max_temp is not None and min_temp is not None:
            temperature_parts.append(f"днем до {round(max_temp)}°C, ночью около {round(min_temp)}°C")

        alerts: list[str] = []
        if precipitation is not None and precipitation >= 60:
            alerts.append(f"вероятность осадков до {round(precipitation)}%")

        return WeatherSnapshot(
            city=normalized_city,
            summary=summary,
            temperature_text=", ".join(temperature_parts),
            alerts=tuple(alerts),
            source_available=True,
            source="open-meteo",
        )


def _first_number(values: Any) -> float | None:
    if not isinstance(values, list) or not values:
        return None
    try:
        return float(values[0])
    except (TypeError, ValueError):
        return None
