"""Диагностика состояния Cloudbot на основе health-check."""

from __future__ import annotations

from typing import Any

from cloudbot.devops.health_check import run_health_check


def collect_diagnostics() -> dict[str, Any]:
    health = run_health_check()
    problems = [name for name, value in health["checks"].items() if not value.get("ok")]
    return {
        "ok": health.get("ok", False),
        "problems": problems,
        "health": health,
    }
