#!/usr/bin/env python3
"""Отправляет в Telegram статус ежедневного обновления маркетингового дашборда."""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT_DIR = Path(os.environ.get("MARKETING_DASHBOARD_ROOT_DIR", Path(__file__).resolve().parents[1]))
ENGINEER_ENV = Path(
    os.environ.get(
        "MARKETING_DASHBOARD_ENGINEER_ENV",
        str(ROOT_DIR / ".env.integrations"),
    )
)
STATUS_FILE = ROOT_DIR / "tmp" / "marketing_dashboard_daily_status.json"
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
DEFAULT_LARISA_TOKEN_FILES = (
    Path.home() / ".config" / "vibecoding" / "assistant" / "secrets" / "larisa_telegram.bot_token",
    Path.home() / ".config" / "openclo" / "assistant" / "secrets" / "larisa_telegram.bot_token",
    Path.home() / ".openclaw" / "telegram" / "larisa_telegram.bot_token",
)


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip("'\"")
    return env


def read_secret_file(path: str) -> str:
    prepared = path.strip()
    if not prepared:
        return ""
    try:
        return Path(prepared).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def merged_env() -> dict[str, str]:
    env = load_env_file(ENGINEER_ENV)
    env.update({key: value for key, value in os.environ.items() if value})
    return env


def resolve_token(env: dict[str, str]) -> str:
    for key in (
        "LARISA_TELEGRAM_BOT_TOKEN",
        "TELEGRAM_BOT_TOKEN",
    ):
        value = env.get(key, "").strip()
        if value:
            return value
    for key in (
        "LARISA_TELEGRAM_BOT_TOKEN_FILE",
        "TELEGRAM_BOT_TOKEN_FILE",
        "MARKETING_TELEGRAM_BOT_TOKEN_FILE",
        "SALES_TELEGRAM_BOT_TOKEN_FILE",
        "SALES_REMOTE_TELEGRAM_BOT_TOKEN_FILE",
    ):
        token = read_secret_file(env.get(key, ""))
        if token:
            return token
    for path in DEFAULT_LARISA_TOKEN_FILES:
        token = read_secret_file(str(path))
        if token:
            return token
    return ""


def resolve_chat_id(env: dict[str, str]) -> str:
    for key in (
        "LARISA_TELEGRAM_CHAT_ID",
        "TELEGRAM_CHAT_ID",
        "MARKETING_TELEGRAM_CHAT_ID",
        "STATUS_CHAT_ID",
        "SALES_TELEGRAM_CHAT_ID",
    ):
        value = env.get(key, "").strip()
        if value:
            return value.removeprefix("telegram:")
    return ""


def fmt_int(value: Any) -> str:
    try:
        return f"{int(round(float(value))):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def status_is_today(payload: dict[str, Any]) -> bool:
    ended_at = str(payload.get("ended_at") or "")
    if not ended_at:
        return False
    return ended_at[:10] == datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d")


def load_status_payload() -> dict[str, Any] | None:
    if not STATUS_FILE.exists():
        return None
    return json.loads(STATUS_FILE.read_text(encoding="utf-8"))


def wait_for_fresh_status(timeout_sec: int, poll_sec: int = 15) -> dict[str, Any] | None:
    deadline = time.monotonic() + max(0, timeout_sec)
    while True:
        payload = load_status_payload()
        if payload is not None and status_is_today(payload):
            return payload
        if time.monotonic() >= deadline:
            return payload
        time.sleep(max(1, poll_sec))


def build_message(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "UNKNOWN")
    verification = payload.get("verification") if isinstance(payload.get("verification"), dict) else {}
    totals = verification.get("totals") if isinstance(verification.get("totals"), dict) else {}
    cohort = totals.get("cohort") if isinstance(totals.get("cohort"), dict) else {}
    event = totals.get("event") if isinstance(totals.get("event"), dict) else {}
    quality = totals.get("quality") if isinstance(totals.get("quality"), dict) else {}
    dashboard_url = str(payload.get("dashboard_url") or "")
    ended_at = str(payload.get("ended_at") or "")

    if status == "OK" and status_is_today(payload):
        title = "Маркетинговый дашборд обновлён"
        lines = [
            f"<b>{html.escape(title)}</b>",
            f"Время: {html.escape(ended_at)}",
            f"Проверка: OK, проверок: {fmt_int(verification.get('checked'))}",
            "",
            f"Когортно: обращения {fmt_int(cohort.get('obr'))}, лиды {fmt_int(cohort.get('lead'))}, КП {fmt_int(cohort.get('kp'))}, договоры {fmt_int(cohort.get('contract'))}, продажи {fmt_int(cohort.get('sale'))}, выручка {fmt_int(cohort.get('revenue'))} ₽",
            f"Событийно: лиды {fmt_int(event.get('lead'))}, КП {fmt_int(event.get('kp'))}, договоры {fmt_int(event.get('contract'))}, продажи {fmt_int(event.get('sale'))}, выручка {fmt_int(event.get('revenue'))} ₽",
            f"Качество данных: проблемных строк {fmt_int(quality.get('total'))}",
            f'<a href="{html.escape(dashboard_url)}">Открыть дашборд</a>',
        ]
        return "\n".join(lines)

    failed_step = str(payload.get("failed_step") or "не определён")
    log_path = str(payload.get("log_path") or "")
    return "\n".join(
        [
            "<b>Маркетинговый дашборд не обновился</b>",
            f"Время: {html.escape(ended_at or datetime.now(MOSCOW_TZ).strftime('%Y-%m-%d %H:%M:%S %Z'))}",
            f"Статус: {html.escape(status)}",
            f"Проблемный шаг: {html.escape(failed_step)}",
            f"Лог: {html.escape(log_path)}",
            f'<a href="{html.escape(dashboard_url)}">Открыть дашборд</a>' if dashboard_url else "",
        ]
    ).strip()


def send_telegram(text: str, *, token: str, chat_id: str, api_base: str) -> dict[str, Any]:
    payload = urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = Request(f"{api_base.rstrip('/')}/bot{token}/sendMessage", data=payload, method="POST")
    with urlopen(request, timeout=20) as response:  # noqa: S310
        result = json.loads(response.read().decode("utf-8", errors="replace"))
    if result.get("ok") is not True:
        raise RuntimeError(f"Telegram sendMessage failed: {result.get('description') or 'unknown error'}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Не отправлять сообщение, только собрать текст.")
    parser.add_argument(
        "--wait-fresh-status",
        type=int,
        default=int(os.environ.get("MARKETING_DASHBOARD_STATUS_WAIT_SECONDS", "1200")),
        help="Сколько секунд ждать свежий status за текущий день перед отправкой.",
    )
    args = parser.parse_args()

    payload = wait_for_fresh_status(args.wait_fresh_status)
    if payload is None:
        payload: dict[str, Any] = {
            "status": "FAIL",
            "ended_at": datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S %Z"),
            "failed_step": "нет файла статуса после запуска обновления",
            "dashboard_url": "https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit",
        }

    message = build_message(payload)
    if args.dry_run:
        print(message)
        return 0

    env = merged_env()
    token = resolve_token(env)
    chat_id = resolve_chat_id(env)
    if not token or not chat_id:
        missing = []
        if not token:
            default_paths = ", ".join(str(path) for path in DEFAULT_LARISA_TOKEN_FILES)
            missing.append(
                "LARISA_TELEGRAM_BOT_TOKEN, LARISA_TELEGRAM_BOT_TOKEN_FILE "
                f"или default token-file ({default_paths})"
            )
        if not chat_id:
            missing.append("LARISA_TELEGRAM_CHAT_ID")
        raise RuntimeError("Не настроена Telegram-отправка: " + ", ".join(missing))

    api_base = env.get("TELEGRAM_API_BASE_URL", "https://api.telegram.org")
    send_telegram(message, token=token, chat_id=chat_id, api_base=api_base)
    print("telegram_status=sent")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001
        print(f"telegram_status=failed error={error}", file=sys.stderr)
        raise
