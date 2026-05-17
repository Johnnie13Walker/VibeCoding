"""Ежедневный Telegram-дайджест по телемаркетингу."""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..config import (
    DIGEST_BITRIX_PORTAL,
    HOLD_REASON_BUSINESS_CLOSED,
    HOLD_REASON_LOW_REVENUE,
    LOG_DIR,
    TELEMARKETING_ASSIGNEES,
    TELEMARKETING_CATEGORY_ID,
)
from ..telegram_client import TelegramClient

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
ASSIGNEE_NAMES = {uid: name.split()[0] for uid, name in TELEMARKETING_ASSIGNEES}
REJECT_REASON_LABELS = {
    HOLD_REASON_BUSINESS_CLOSED: "Бизнес закрылся",
    HOLD_REASON_LOW_REVENUE: "Выручка <30M",
}


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
        _section_reactivations(bx, since),
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
    rows = _read_csv_rows(LOG_DIR / "auto_revive_lose.csv", since=since)
    revived = [row for row in rows if str(row.get("status") or "") == "REVIVED"]
    grouped: dict[str, list[str]] = {}
    for row in revived:
        assignee = str(row.get("new_assignee") or "").strip() or "unknown"
        grouped.setdefault(assignee, []).append(str(row.get("deal_id") or "").strip())

    lines = []
    for assignee, deal_ids in sorted(grouped.items()):
        name = ASSIGNEE_NAMES.get(assignee, assignee)
        links = ", ".join(_deal_link(deal_id) for deal_id in deal_ids if deal_id)
        lines.append(f"- {escape(name)} ({escape(assignee)}): {len(deal_ids)} сделок → {links}")
    return DigestSection("Авто-возврат из ОТЛОЖЕНО", lines)


def _section_auto_reject(bx: Any, since: str) -> DigestSection:
    rows = _read_csv_rows(LOG_DIR / "auto_reject_telemarketing.csv", since=since)
    by_reason: dict[str, list[str]] = {}
    for row in rows:
        reason = str(row.get("reason_id") or "").strip()
        if not reason:
            continue
        by_reason.setdefault(reason, []).append(str(row.get("deal_id") or "").strip())

    lines = []
    for reason, deal_ids in sorted(by_reason.items()):
        label = REJECT_REASON_LABELS.get(reason, f"reason {reason}")
        links = ", ".join(_deal_link(deal_id) for deal_id in deal_ids[:8] if deal_id)
        suffix = f" → {links}" if links else ""
        if len(deal_ids) > 8:
            suffix += f" + ещё {len(deal_ids) - 8}"
        lines.append(f"- {escape(reason)} «{escape(label)}»: {len(deal_ids)} сделок{suffix}")
    return DigestSection("Авто-отказ", lines)


def _section_reactivations(bx: Any, since: str) -> DigestSection:
    rows = _read_csv_rows(LOG_DIR / "reactivation_apology.csv", since=since)
    reactivated = [row for row in rows if str(row.get("status") or "") == "REACTIVATED"]
    by_reason: dict[str, list[str]] = {}
    for row in reactivated:
        reason = str(row.get("reason_id") or "").strip() or "unknown"
        by_reason.setdefault(reason, []).append(str(row.get("deal_id") or "").strip())

    lines = []
    for reason, deal_ids in sorted(by_reason.items()):
        links = ", ".join(_deal_link(deal_id) for deal_id in deal_ids[:8] if deal_id)
        suffix = f" → {links}" if links else ""
        if len(deal_ids) > 8:
            suffix += f" + ещё {len(deal_ids) - 8}"
        lines.append(f"- reason {escape(reason)}: {len(deal_ids)} сделок{suffix}")
    return DigestSection("Реактивации из ОТВАЛ", lines)


def _section_manager_conversions(bx: Any, since: str) -> DigestSection:
    start = (_parse_date(since) - timedelta(days=6)).isoformat()
    deals = _list_stage_deals(
        bx,
        ["C50:APOLOGY", "C50:WON"],
        closed="Y",
        select=["ID", "STAGE_ID", "ASSIGNED_BY_ID", "DATE_MODIFY"],
    )
    counters = {uid: {"APOLOGY": 0, "WON": 0} for uid, _ in TELEMARKETING_ASSIGNEES}
    for deal in deals:
        assignee = str(deal.get("ASSIGNED_BY_ID") or "")
        if assignee not in counters:
            continue
        modified = str(deal.get("DATE_MODIFY") or "")[:10]
        if modified and modified < start:
            continue
        stage_id = str(deal.get("STAGE_ID") or "")
        if stage_id == "C50:APOLOGY":
            counters[assignee]["APOLOGY"] += 1
        elif stage_id == "C50:WON":
            counters[assignee]["WON"] += 1

    lines = []
    for assignee, name in TELEMARKETING_ASSIGNEES:
        first_name = name.split()[0]
        values = counters[assignee]
        if values["APOLOGY"] or values["WON"]:
            lines.append(f"- {escape(first_name)}: APOLOGY {values['APOLOGY']} / WON {values['WON']}")
    return DigestSection("Конверсия менеджеров за 7 дней", lines)


def _section_stuck_alerts(bx: Any) -> DigestSection:
    from .telemarketing_stuck_alerts import find_stuck_preparation, find_stuck_wz4kqe

    prep = find_stuck_preparation(bx)
    wz4 = find_stuck_wz4kqe(bx)
    lines = []
    if prep:
        lines.append(f"<b>PREPARATION без касания &gt;21д:</b> {len(prep)}")
        lines.extend(_format_stuck_deal_lines(prep[:5]))
        if len(prep) > 5:
            lines.append(f"  + ещё {len(prep) - 5}")
    if wz4:
        if lines:
            lines.append("")
        lines.append(f"<b>WZ4KQE с прошедшей встречей &gt;14д:</b> {len(wz4)}")
        lines.extend(_format_stuck_deal_lines(wz4[:5]))
        if len(wz4) > 5:
            lines.append(f"  + ещё {len(wz4) - 5}")
    return DigestSection("Застрявшие сделки", lines)


def _read_csv_rows(path: Path, *, since: str) -> list[dict[str, str]]:
    if not path.exists():
        return []

    out: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ts = str(row.get("timestamp") or "")
            if ts[:10] == since:
                out.append({str(k): str(v or "") for k, v in row.items()})
    return out


def _list_stage_deals(
    bx: Any,
    stage_ids: list[str],
    *,
    closed: str,
    select: list[str],
) -> list[dict[str, Any]]:
    if hasattr(bx, "list_deals_by_stages"):
        return list(
            bx.list_deals_by_stages(
                category_id=int(TELEMARKETING_CATEGORY_ID),
                stage_ids=stage_ids,
                closed=closed,
                select=select,
            )
        )
    if hasattr(bx, "paginate"):
        return list(
            bx.paginate(
                "crm.deal.list",
                {
                    "filter": {
                        "CATEGORY_ID": int(TELEMARKETING_CATEGORY_ID),
                        "STAGE_ID": stage_ids,
                        "CLOSED": closed,
                    },
                    "select": select,
                },
            )
        )
    return []


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(str(value)[:10]).date()


def _format_stuck_deal_lines(deals: list[Any]) -> list[str]:
    lines = []
    for deal in deals:
        title = escape(str(getattr(deal, "title", "") or ""))
        assignee = escape(str(getattr(deal, "assignee", "") or ""))
        days = escape(str(getattr(deal, "days_stuck", "") or ""))
        link = _deal_link(getattr(deal, "deal_id", ""), f"#{getattr(deal, 'deal_id', '')} {title}".strip())
        lines.append(f"  • {link} ({days}д, {assignee})")
    return lines
