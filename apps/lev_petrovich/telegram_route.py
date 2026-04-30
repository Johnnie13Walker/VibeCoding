"""Telegram route и identity Льва Петровича."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

LEV_PETROVICH_ROUTE_KEY = "lev-petrovich"
LEV_PETROVICH_DISPLAY_NAME = "Лев Петрович"
LEV_PETROVICH_BOT_USERNAME = "icom_dir_Belberry_bot"
DEFAULT_SALES_TELEGRAM_BOT_TOKEN_FILE = "/root/.openclaw/telegram/commercial-director.bot_token"


def _read_secret_file(path: str | None) -> str:
    raw_path = str(path or "").strip()
    if not raw_path:
        return ""
    try:
        return Path(raw_path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def describe_lev_petrovich_route() -> dict[str, str]:
    return {
        "route_key": LEV_PETROVICH_ROUTE_KEY,
        "display_name": LEV_PETROVICH_DISPLAY_NAME,
        "bot_username": LEV_PETROVICH_BOT_USERNAME,
    }


def resolve_lev_petrovich_bot_token(
    env_data: Mapping[str, str],
    *,
    allow_shared_fallback: bool = False,
) -> str:
    explicit_token = str(env_data.get("SALES_TELEGRAM_BOT_TOKEN") or "").strip()
    if explicit_token:
        return explicit_token

    token_file = str(
        env_data.get("SALES_TELEGRAM_BOT_TOKEN_FILE")
        or env_data.get("SALES_REMOTE_TELEGRAM_BOT_TOKEN_FILE")
        or DEFAULT_SALES_TELEGRAM_BOT_TOKEN_FILE
    ).strip()
    file_token = _read_secret_file(token_file)
    if file_token:
        return file_token

    if allow_shared_fallback:
        return str(env_data.get("TELEGRAM_BOT_TOKEN") or "").strip()
    return ""
