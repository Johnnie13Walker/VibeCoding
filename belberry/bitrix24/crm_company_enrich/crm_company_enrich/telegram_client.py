"""Минимальный Telegram-клиент для операционных дайджестов."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

from .config import LARISA_BOT_TOKEN_ENV, LARISA_CHAT_ID_LARISA_ENV


class TelegramClient:
    """Отправляет сообщения Ларисе Ивановне.

    Если ENV не настроены, отправка считается пропущенной, а не ошибочной:
    это важно для локальных dry-run и CI.
    """

    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token or os.environ.get(LARISA_BOT_TOKEN_ENV)
        self.chat_id = chat_id or os.environ.get(LARISA_CHAT_ID_LARISA_ENV)

    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send_message(
        self,
        text: str,
        *,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = True,
    ) -> dict[str, Any]:
        if not self.is_configured():
            return {"skipped": True, "reason": "no_config"}

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = urllib.parse.urlencode(
            {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": str(disable_web_page_preview).lower(),
            }
        ).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)[:200]}
