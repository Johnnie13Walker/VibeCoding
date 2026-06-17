"""Вернуть FAILED группу в APPROVED после ручного разбора причины."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from ..sheet_store import read_groups, update_group
from ..sheets_client import SheetsClient
from ..state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def run(sheets: SheetsClient, *, company_id: str, domain: str) -> dict:
    now = datetime.now(MOSCOW_TZ)
    for row_number, group in read_groups(sheets):
        if group.company_id != str(company_id) or (group.domain or "") != domain:
            continue
        if group.status != Status.FAILED:
            print(f"[unfail] группа {company_id}:{domain} не FAILED, status={group.status.value}")
            return {"changed": 0, "status": group.status.value}
        updated = replace(
            group,
            status=Status.APPROVED,
            approved=True,
            last_action_at=now,
            error_message=None,
        )
        update_group(sheets, row_number, updated)
        print(f"[unfail] {company_id}:{domain} FAILED -> APPROVED")
        return {"changed": 1, "status": Status.APPROVED.value}
    print(f"[unfail] группа не найдена: {company_id}:{domain}")
    return {"changed": 0, "status": "NOT_FOUND"}
