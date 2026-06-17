"""Мониторинг: короткий статус для ежедневного отчета."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from cloudbot.devops.diagnostics import collect_diagnostics

MSK = ZoneInfo("Europe/Moscow")


def daily_status() -> dict[str, str]:
    diagnostics = collect_diagnostics()
    now_msk = datetime.now(MSK).strftime("%Y-%m-%d %H:%M:%S")
    if diagnostics["ok"]:
        return {
            "timestamp_msk": now_msk,
            "status": "ОК",
            "details": "Критичных проблем не обнаружено",
        }

    return {
        "timestamp_msk": now_msk,
        "status": "есть проблемы",
        "details": ", ".join(diagnostics["problems"]) or "неизвестная проблема",
    }
