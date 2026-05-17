"""Ежедневный Telegram-дайджест по телемаркетингу."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from ..config import DIGEST_BITRIX_PORTAL
from ..telegram_client import TelegramClient

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


@dataclass
class DigestSection:
    title: str
    lines: list[str]


def run(
    bx: Any,
    *,
    dry_run: bool = True,
    since: str | None = None,
    telegram: TelegramClient | None = None,
) -> dict[str, Any]:
    """Собирает дайджест за сутки и отправляет Ларисе.

    `since` — ISO date `YYYY-MM-DD`; по умолчанию вчера по МСК.
    """
    since = since or _default_since()
    sections = [
        _section_auto_revive(bx, since),
        _section_auto_reject(bx, since),
        _section_manager_conversions(bx, since),
        _section_stuck_alerts(bx),
    ]
    text = _format_html(sections, since)
    section_payload = [asdict(section) for section in sections]
    if dry_run:
        return {
            "dry_run": True,
            "since": since,
            "preview": text,
            "sections": section_payload,
        }

    tg = telegram or TelegramClient()
    result = tg.send_message(text)
    return {
        "dry_run": False,
        "since": since,
        "telegram": result,
        "sections": section_payload,
    }


def _default_since() -> str:
    return (datetime.now(MOSCOW_TZ).date() - timedelta(days=1)).isoformat()


def _format_html(sections: list[DigestSection], since: str) -> str:
    header = f"<b>Телемаркетинг — сводка за {escape(str(since))}</b>\n\n"
    body = ""
    for section in sections:
        if not section.lines:
            continue
        body += f"<b>{escape(section.title)}</b>\n"
        body += "\n".join(section.lines)
        body += "\n\n"
    return (header + body).strip()


def _deal_link(deal_id: str | int, text: str | None = None) -> str:
    deal_id_s = escape(str(deal_id))
    label = escape(text or f"#{deal_id_s}")
    return (
        f'<a href="https://{DIGEST_BITRIX_PORTAL}/crm/deal/details/'
        f'{deal_id_s}/">{label}</a>'
    )


def _section_auto_revive(bx: Any, since: str) -> DigestSection:
    return DigestSection("Авто-возврат из ОТЛОЖЕНО", [])


def _section_auto_reject(bx: Any, since: str) -> DigestSection:
    return DigestSection("Авто-отказ", [])


def _section_manager_conversions(bx: Any, since: str) -> DigestSection:
    return DigestSection("Конверсия менеджеров", [])


def _section_stuck_alerts(bx: Any) -> DigestSection:
    return DigestSection("Застрявшие сделки", [])
