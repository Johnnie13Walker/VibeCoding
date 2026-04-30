"""Workflow системного health-check для команды /health."""

from __future__ import annotations

from typing import Any

from cloudbot.devops.system_health import run_system_health


def run(context: dict[str, Any]) -> dict[str, Any]:
    result = run_system_health()
    return {
        "ok": bool(result.get("ok")),
        "workflow": "system_health",
        "text": str(result.get("text") or "🔴 ЕСТЬ ПРОБЛЕМЫ\n\nHealth check недоступен."),
        "parse_mode": "HTML",
        "checks": result.get("checks") or {},
        "warnings": result.get("warnings") or [],
    }
