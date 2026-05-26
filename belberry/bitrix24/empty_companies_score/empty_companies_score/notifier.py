"""Telegram-сводка для Ларисы: текущие цифры + дельта за сутки.

State (предыдущий снапшот) хранится в `<DATA_DIR>/state.json` — простая структура:
{"snapshot": {"total": 2543, "score_3_safe": 1842, ...}, "ts": "ISO8601"}
"""

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .config import TG_BOT_TOKEN_FILE, TG_CHAT_ID


def _load_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text())
    except json.JSONDecodeError:
        return {}


def _save_state(state_path: Path, snapshot: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(
        {"snapshot": snapshot, "ts": datetime.now(timezone.utc).isoformat()},
        ensure_ascii=False, indent=2,
    ))


def _delta_line(label: str, now: int, prev: int) -> str:
    if prev == 0 and now == 0:
        return f"{label}: 0"
    if not prev:
        return f"{label}: {now} (новая метрика)"
    diff = now - prev
    sign = "+" if diff > 0 else ""
    return f"{label}: {now} ({sign}{diff} за сутки)"


def render_summary(now: dict, prev: dict, tab_url: str) -> str:
    """Markdown-сообщение в чат Ларисы."""
    lines = [
        "📋 *Пустые компании — скоринг*",
        "",
        _delta_line("score=3 + safe", now.get("score_3_safe", 0), prev.get("score_3_safe", 0)),
        _delta_line("score=3", now.get("score_3", 0), prev.get("score_3", 0)),
        _delta_line("score=2", now.get("score_2", 0), prev.get("score_2", 0)),
        _delta_line("safe-to-delete", now.get("safe", 0), prev.get("safe", 0)),
        _delta_line("всего во вкладке", now.get("total", 0), prev.get("total", 0)),
        "",
        f"[Открыть вкладку]({tab_url})",
    ]
    return "\n".join(lines)


def _read_token() -> str | None:
    """Приоритет: env LARISA_TELEGRAM_BOT_TOKEN (прямое значение) → env
    TELEGRAM_BOT_TOKEN (общий env Cloudbot) → файл LARISA_TELEGRAM_BOT_TOKEN_FILE."""
    for env_name in ("LARISA_TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"):
        v = os.environ.get(env_name, "").strip()
        if v:
            return v
    if TG_BOT_TOKEN_FILE:
        p = Path(TG_BOT_TOKEN_FILE)
        if p.exists():
            return p.read_text().strip()
    return None


def send_telegram(text: str) -> bool:
    """Шлём в чат Ларисы. Тихий no-op если токена нет — лог без Sheet-нагрузки."""
    token = _read_token()
    if not token:
        print("[notifier] LARISA_TELEGRAM_BOT_TOKEN_FILE not set — пропускаем TG")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": "true",
    }).encode()
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, data=data), timeout=15
        ) as r:
            r.read()
        return True
    except Exception as e:  # noqa: BLE001 — TG-сбой не должен ронять весь cron
        print(f"[notifier] TG send failed: {e}")
        return False


def notify_if_morning(snapshot: dict, state_path: Path, tab_url: str, force: bool = False) -> None:
    """Шлём TG только при `force=True` (управляется через CLI-флаг `--notify`).

    Сравниваем с прошлым snapshot из state-файла, потом перезаписываем state.
    """
    prev = _load_state(state_path).get("snapshot", {})
    if force:
        msg = render_summary(snapshot, prev, tab_url)
        sent = send_telegram(msg)
        print(f"[notifier] TG sent={sent}")
    _save_state(state_path, snapshot)
