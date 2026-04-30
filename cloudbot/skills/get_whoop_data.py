"""Skill получения данных WHOOP (адаптер к существующему JS skill)."""

from __future__ import annotations

from typing import Any

from cloudbot.compat.node_bridge import call_js_export

LEGACY_MODULE = "cloudbot/skills/whoop_data/index.js"


def run(payload: dict[str, Any], providers: dict[str, Any] | None = None) -> dict[str, Any]:
    providers = providers or {}
    try:
        legacy_result = call_js_export(LEGACY_MODULE, "run", args=[payload, providers])
    except Exception as error:  # noqa: BLE001
        legacy_result = {"ok": False, "error": str(error)}

    return {
        "skill": "get_whoop_data",
        "ok": True,
        "legacy": legacy_result,
    }
