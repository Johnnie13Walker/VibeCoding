"""Конфигурация Telegram-маршрута Финансиста."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FinansistTelegramRoute:
    route_key: str = "finansist"
    command_namespace: str = "finance"
