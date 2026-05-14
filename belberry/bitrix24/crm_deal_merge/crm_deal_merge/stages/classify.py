"""Стадия classify — перевести инвентаризированные группы в PLAN_READY."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from ..sheet_store import read_groups, update_group
from ..sheets_client import SheetsClient
from ..state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def run(sheets: SheetsClient) -> dict:
    now = datetime.now(MOSCOW_TZ)
    plan_ready = 0
    manual = 0
    for row_number, group in read_groups(sheets):
        if group.status != Status.INVENTORIED:
            continue
        if not group.domain or not group.winner_id or len(group.loser_ids) < 1:
            updated = replace(group, status=Status.MANUAL, last_action_at=now, error_message="нет домена или LOSER")
            manual += 1
        else:
            updated = replace(group, status=Status.PLAN_READY, last_action_at=now, error_message=None)
            plan_ready += 1
        update_group(sheets, row_number, updated)
    print(f"[classify] PLAN_READY: {plan_ready}; MANUAL: {manual}")
    return {"plan_ready": plan_ready, "manual": manual}
