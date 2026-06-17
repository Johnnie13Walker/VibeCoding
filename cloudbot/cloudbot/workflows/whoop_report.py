"""Workflow WHOOP: адаптер к существующему JS workflow health."""

from __future__ import annotations

from typing import Any

from cloudbot.compat.node_bridge import call_js_export

LEGACY_MODULE = "cloudbot/workflows/health/index.js"


def run(context: dict[str, Any]) -> dict[str, Any]:
    try:
        legacy_result = call_js_export(LEGACY_MODULE, "workflow", "run", [context])
    except Exception as error:  # noqa: BLE001
        legacy_result = {"ok": False, "error": str(error)}

    return {
        "ok": True,
        "workflow": "whoop_report",
        "text": "WHOOP-отчет подготовлен.",
        "legacy": legacy_result,
    }
