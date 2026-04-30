"""Общие Telegram routing helpers без доступа к секретам."""

from __future__ import annotations


def normalize_chat_id(value: str | None) -> str:
    raw = str(value or "").strip()
    if raw.startswith("telegram:"):
        raw = raw.split(":", 1)[1].strip()
    return raw
