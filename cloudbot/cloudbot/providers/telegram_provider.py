"""Telegram provider: адаптер к существующему JS provider."""

from __future__ import annotations

from typing import Any

from cloudbot.compat.node_bridge import call_js_export

LEGACY_MODULE = "cloudbot/providers/telegram/index.js"


def healthcheck(config: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        provider = call_js_export(LEGACY_MODULE, "createProvider", args=[config or {}])
    except Exception as error:  # noqa: BLE001
        return {"provider": "telegram", "ok": False, "error": str(error)}

    return {
        "provider": "telegram",
        "ok": True,
        "legacy": provider,
    }
