"""Тонкий слой Telegram: получает update, нормализует, передает в orchestrator."""

from __future__ import annotations

from typing import Any, Callable

from cloudbot.bot.telegram.commands import extract_command
from cloudbot.orchestrator.orchestrator import handle_incoming_message


def normalize_update(update: dict[str, Any]) -> dict[str, Any]:
    message = update.get("message") or {}
    text = message.get("text") or update.get("text") or ""

    chat = message.get("chat") or {}
    user = message.get("from") or {}

    normalized = {
        "text": str(text).strip(),
        "command": extract_command(text),
        "chat_id": str(chat.get("id") or update.get("chat_id") or ""),
        "user_id": str(user.get("id") or update.get("user_id") or ""),
        "raw_update": update,
    }
    return normalized


def handle_update(
    update: dict[str, Any],
    send_reply: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_update(update)
    result = handle_incoming_message(normalized)

    reply_chunks = result.get("message_chunks") or []
    parse_mode = result.get("parse_mode")
    if reply_chunks:
        reply_text = "\n\n".join(str(chunk) for chunk in reply_chunks)
    else:
        reply_text = str(result.get("text") or f"Workflow: {result.get('workflow', 'unknown')}")
    if send_reply and normalized["chat_id"]:
        if reply_chunks:
            for chunk in reply_chunks:
                if parse_mode is not None:
                    try:
                        send_reply(normalized["chat_id"], str(chunk), parse_mode=parse_mode)
                    except TypeError:
                        send_reply(normalized["chat_id"], str(chunk))
                else:
                    send_reply(normalized["chat_id"], str(chunk))
        else:
            if parse_mode is not None:
                try:
                    send_reply(normalized["chat_id"], reply_text, parse_mode=parse_mode)
                except TypeError:
                    send_reply(normalized["chat_id"], reply_text)
            else:
                send_reply(normalized["chat_id"], reply_text)

    return {
        "normalized": normalized,
        "result": result,
        "reply_text": reply_text,
    }
