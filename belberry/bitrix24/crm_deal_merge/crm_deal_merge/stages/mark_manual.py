"""Перевести группу в MANUAL для ручного разбора."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from ..sheet_store import read_groups, update_group
from ..sheets_client import SheetsClient
from ..state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def run(sheets: SheetsClient, *, company_id: str, domain: str, reason: str) -> dict:
    now = datetime.now(MOSCOW_TZ)
    for row_number, group in read_groups(sheets):
        if group.company_id != str(company_id) or (group.domain or "") != domain:
            continue
        updated = replace(
            group,
            status=Status.MANUAL,
            approved=False,
            approved_by=None,
            approved_at=None,
            last_action_at=now,
            error_message=reason[:500] if reason else None,
        )
        update_group(sheets, row_number, updated)
        print(f"[mark-manual] {company_id}:{domain} -> MANUAL")
        return {"changed": 1, "status": Status.MANUAL.value}
    print(f"[mark-manual] группа не найдена: {company_id}:{domain}")
    return {"changed": 0, "status": "NOT_FOUND"}
