"""Workflow self-healing для команды /repair."""

from __future__ import annotations

from typing import Any

from cloudbot.devops.self_healing import run_self_healing


def run(context: dict[str, Any]) -> dict[str, Any]:
    result = run_self_healing()
    return {
        "ok": bool(result.get("ok")),
        "workflow": "self_healing",
        "text": str(result.get("text") or "SELF HEALING REPORT\n\nSelf-healing недоступен."),
        "checks": result.get("checks") or {},
        "warnings": result.get("warnings") or [],
        "actions": result.get("actions") or [],
    }
