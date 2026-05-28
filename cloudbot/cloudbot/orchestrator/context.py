"""Контекст обработки входящего сообщения."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_context(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "source": "telegram",
        "message": message,
    }
