#!/usr/bin/env python3
"""Аудит PLAN_READY групп, отсеянных smart-фильтром как loser_not_found."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crm_deal_merge.bitrix_client import BitrixClient
from crm_deal_merge.config import LOG_PATH, SERVICE_ACCOUNT_JSON, SHEET_ID, STATE_PATH
from crm_deal_merge.sheet_store import read_groups
from crm_deal_merge.sheets_client import SheetsClient
from crm_deal_merge.stages import mark_approved, mark_manual
from crm_deal_merge.stages.mark_approved import is_smart_approvable
from crm_deal_merge.state import Status


def main() -> int:
    bx = BitrixClient(state_path=STATE_PATH, log_path=LOG_PATH)
    sheets = SheetsClient(SHEET_ID, SERVICE_ACCOUNT_JSON)
    audited = 0
    approved = 0
    manual = 0

    for _, group in read_groups(sheets):
        if group.status != Status.PLAN_READY:
            continue
        ok, reason = is_smart_approvable(group, bx=bx)
        if ok or reason != "loser_not_found":
            continue

        audited += 1
        existing: list[str] = []
        deleted: list[str] = []
        for loser_id in group.loser_ids:
            if bx.get_deal(loser_id):
                existing.append(loser_id)
            else:
                deleted.append(loser_id)

        key = f"{group.company_id}:{group.domain or ''}"
        if deleted and not existing:
            result = mark_manual.run(
                sheets,
                company_id=group.company_id,
                domain=group.domain or "",
                reason=f"all_losers_deleted: {','.join(deleted)}",
            )
            manual += int(result.get("changed", 0))
            print(f"[audit-loser-not-found] {key}: all deleted {deleted} -> MANUAL")
        elif deleted and existing:
            result = mark_manual.run(
                sheets,
                company_id=group.company_id,
                domain=group.domain or "",
                reason=f"partial_losers_deleted: deleted={','.join(deleted)} exists={','.join(existing)}",
            )
            manual += int(result.get("changed", 0))
            print(f"[audit-loser-not-found] {key}: partial deleted={deleted} exists={existing} -> MANUAL")
        else:
            result = mark_approved.run(
                sheets,
                company_id=group.company_id,
                domain=group.domain or "",
            )
            approved += int(result.get("approved", 0))
            print(f"[audit-loser-not-found] {key}: all exist {existing} -> APPROVED")

    print(f"[audit-loser-not-found] audited={audited} approved={approved} manual={manual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
