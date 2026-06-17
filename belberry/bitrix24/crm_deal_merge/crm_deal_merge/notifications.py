from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError

STATUS_ICONS = {
    "MERGED": "✅",
    "DONE": "✅",
    "TRANSFERRED": "🟡",
    "APPROVED": "🔵",
    "PLAN_READY": "🔵",
    "MANUAL": "🟣",
    "INVENTORIED": "⚪",
    "NEW": "⚪",
    "ROLLED_BACK": "↩️",
    "FAILED": "🔴",
}

STATUS_ORDER = [
    "MERGED",
    "DONE",
    "TRANSFERRED",
    "APPROVED",
    "PLAN_READY",
    "INVENTORIED",
    "NEW",
    "MANUAL",
    "ROLLED_BACK",
    "FAILED",
]


def build_progress_message(
    *,
    stage_title: str,
    batch_stats: list[tuple[str, int]],
    queue_counts: dict[str, int],
) -> str:
    done = queue_counts.get("MERGED", 0) + queue_counts.get("DONE", 0)
    failed = queue_counts.get("FAILED", 0)
    total = sum(queue_counts.values())
    actionable = max(total - failed, 1)

    pct = round(done / actionable * 100)
    bar_len = 10
    filled = round(done / actionable * bar_len)
    bar = "▓" * filled + "░" * (bar_len - filled)

    lines = [f"✅ {stage_title}", ""]
    lines.append("Результат пакета:")
    for label, value in batch_stats:
        lines.append(f"  • {label}: {value}")
    lines.append("")
    lines.append("📈 Прогресс дедупа:")
    lines.append(f"  {bar} {done} / {actionable}  ({pct}%)")
    lines.append("")
    lines.append("Очередь сейчас:")
    for status in STATUS_ORDER:
        count = queue_counts.get(status, 0)
        if count > 0:
            icon = STATUS_ICONS.get(status, "")
            lines.append(f"  {icon} {status:<13} {count:>3}")
    return "\n".join(lines)


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
