from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError


def send_telegram(token: str, chat_id: int, text: str) -> bool:
    """Отправить Telegram-сообщение через Bot API без внешних зависимостей."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    request = urllib.request.Request(
        url,
        method="POST",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, json.JSONDecodeError) as exc:
        print(f"Telegram notify failed: {exc}", file=sys.stderr)
        return False
    return bool(body.get("ok"))
