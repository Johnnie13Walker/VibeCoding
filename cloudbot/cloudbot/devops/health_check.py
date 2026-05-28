"""Быстрый health-check основных модулей Cloudbot."""

from __future__ import annotations

from typing import Any

from cloudbot.providers.bitrix_provider import healthcheck as bitrix_health
from cloudbot.providers.search_provider import healthcheck as search_health
from cloudbot.providers.telegram_provider import healthcheck as telegram_health
from cloudbot.providers.todo_provider import healthcheck as todo_health
from cloudbot.providers.whoop_provider import healthcheck as whoop_health


def run_health_check() -> dict[str, Any]:
    checks = {
        "telegram": telegram_health(),
        "bitrix": bitrix_health(),
        "todo": todo_health(),
        "whoop": whoop_health(),
        "search": search_health(),
    }

    ok = all(item.get("ok") for item in checks.values())
    return {"ok": ok, "checks": checks}
