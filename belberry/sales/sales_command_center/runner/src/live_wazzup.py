"""Часовой проход Wazzup-чатов для «Сегодня». Тяжёлый per-deal скан timeline
(как в daily), поэтому отдельно от лёгкого 20-мин live. Считает диалоги за
сегодня на менеджера, пишет live_chats."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .collect import _fetch_all, _range, _collect_wazzup, compute_messenger_dialogs


def collect_chat_payload(today: date, bx=None, now: datetime | None = None) -> dict[str, Any]:
    d0, d1 = _range(today)
    deals_open = _fetch_all(
        bx, "crm.deal.list",
        {"filter": {"CLOSED": "N", "@CATEGORY_ID": [10, 50]}, "select": ["ID", "ASSIGNED_BY_ID"]},
    )
    deal_manager = {
        str(d.get("ID")): str(d.get("ASSIGNED_BY_ID"))
        for d in deals_open
        if d.get("ID") and d.get("ASSIGNED_BY_ID")
    }
    deal_ids = {str(d.get("ID")) for d in deals_open if d.get("ID")}
    wazzup = _collect_wazzup(deal_ids, bx)
    dialogs = compute_messenger_dialogs(wazzup, deal_manager, d0, d1)  # {manager_id(str): count}

    managers = {str(mid): int(cnt) for mid, cnt in dialogs.items() if cnt}
    total = sum(managers.values())
    return {"report_date": today.isoformat(), "managers": managers, "total": total, "scanned_deals": len(deal_ids)}
