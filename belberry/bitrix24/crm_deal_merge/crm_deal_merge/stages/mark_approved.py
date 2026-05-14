"""Approval gate — пометить выбранные группы как APPROVED."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from ..sheet_store import read_groups, update_group
from ..sheets_client import SheetsClient
from ..state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def run(
    sheets: SheetsClient,
    *,
    all_: bool = False,
    status: str = "PLAN_READY",
    company_id: str | None = None,
    domain: str | None = None,
) -> dict:
    target_status = Status(status)
    now = datetime.now(MOSCOW_TZ)
    changed = 0
    for row_number, group in read_groups(sheets):
        if group.status != target_status:
            continue
        if not all_ and (str(group.company_id) != str(company_id) or (group.domain or "") != (domain or "")):
            continue
        updated = replace(
            group,
            status=Status.APPROVED,
            approved=True,
            approved_by="deal-merge CLI",
            approved_at=now,
            last_action_at=now,
            error_message=None,
        )
        update_group(sheets, row_number, updated)
        changed += 1
    print(f"[mark-approved] APPROVED: {changed}")
    return {"approved": changed}
