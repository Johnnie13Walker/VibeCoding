"""Снять approval с группы merge."""
from __future__ import annotations

from dataclasses import replace

from ..sheet_store import read_groups, update_group
from ..sheets_client import SheetsClient
from ..state import Status


def run(sheets: SheetsClient, *, company_id: str, domain: str) -> dict:
    for row_number, group in read_groups(sheets):
        if group.company_id != str(company_id) or (group.domain or "") != domain:
            continue
        if group.status != Status.APPROVED:
            print(f"[unapprove] группа {company_id}:{domain} не APPROVED, status={group.status.value}")
            return {"changed": 0, "status": group.status.value}
        updated = replace(
            group,
            status=Status.PLAN_READY,
            approved=False,
            approved_by=None,
            approved_at=None,
            error_message=None,
        )
        update_group(sheets, row_number, updated)
        print(f"[unapprove] {company_id}:{domain} APPROVED -> PLAN_READY")
        return {"changed": 1, "status": Status.PLAN_READY.value}
    print(f"[unapprove] группа не найдена: {company_id}:{domain}")
    return {"changed": 0, "status": "NOT_FOUND"}
