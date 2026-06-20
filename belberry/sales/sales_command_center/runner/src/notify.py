import html
import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import date
from typing import Any, Callable

LOGGER = logging.getLogger(__name__)
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

HttpPost = Callable[[str, dict[str, Any]], Any]


def _mask(text: str, token: str | None = None) -> str:
    masked = text
    if token:
        masked = masked.replace(token, "***")
    return re.sub(r"bot[0-9]{5,}:[A-Za-z0-9_-]+", "bot***", masked)


def _env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _report_date(value: str | date) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


def _default_http_post(url: str, payload: dict[str, Any]) -> bool:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return 200 <= response.status < 300


def _post(
    token: str,
    chat_id: str,
    text: str,
    *,
    http_post: HttpPost | None = None,
) -> bool:
    url = TELEGRAM_API.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        result = (http_post or _default_http_post)(url, payload)
        if isinstance(result, bool):
            return result
        status = getattr(result, "status", getattr(result, "status_code", None))
        return status is None or 200 <= int(status) < 300
    except urllib.error.HTTPError as exc:
        LOGGER.warning("Telegram send failed: %s", _mask(str(exc), token))
    except Exception as exc:
        LOGGER.warning("Telegram send failed: %s", _mask(str(exc), token))
    return False


def send_alert(
    message: str,
    *,
    report_date: str | date | None = None,
    http_post: HttpPost | None = None,
) -> bool:
    token = _env("TELEGRAM_BOT_TOKEN", "SCC_TELEGRAM_BOT_TOKEN")
    chat_id = _env(
        "TELEGRAM_ALERT_CHAT_ID",
        "SCC_TELEGRAM_ALERT_CHAT_ID",
        "TELEGRAM_CHAT_ID",
        "SCC_TELEGRAM_CHAT_ID",
    )

    if not token or not chat_id:
        LOGGER.warning("Telegram alert skipped: missing env")
        return False

    date_part = f" за {html.escape(_report_date(report_date))}" if report_date else ""
    text = f"⚠️ Сбой ежедневного прогона{date_part}: {html.escape(message)}"

    return _post(token, chat_id, text, http_post=http_post)
