#!/usr/bin/env python3
"""Точечно одобрить PLAN_READY группы, отсеянные только по heavy/mixed причинам."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crm_deal_merge.bitrix_client import BitrixClient
from crm_deal_merge.config import LOG_PATH, SERVICE_ACCOUNT_JSON, SHEET_ID, STATE_PATH
from crm_deal_merge.sheet_store import read_groups
from crm_deal_merge.sheets_client import SheetsClient
from crm_deal_merge.stages import mark_approved
from crm_deal_merge.stages.mark_approved import is_smart_approvable
from crm_deal_merge.state import Status

TARGET_REASONS = {"heavy_group", "mixed_loser_funnels"}


def main() -> int:
    bx = BitrixClient(state_path=STATE_PATH, log_path=LOG_PATH)
    sheets = SheetsClient(SHEET_ID, SERVICE_ACCOUNT_JSON)
    reasons: Counter[str] = Counter()
    approved = 0

    candidates = []
    for _, group in read_groups(sheets):
        if group.status != Status.PLAN_READY:
            continue
        ok, reason = is_smart_approvable(group, bx=bx)
        if ok:
            continue
        reasons[reason] += 1
        if reason in TARGET_REASONS:
            candidates.append(group)

    for group in candidates:
        result = mark_approved.run(
            sheets,
            company_id=group.company_id,
            domain=group.domain or "",
        )
        changed = int(result.get("approved", 0))
        approved += changed
        print(f"[approve-remaining-safe] {group.company_id}:{group.domain or ''} -> approved={changed}")

    print(f"[approve-remaining-safe] reasons={dict(reasons)}")
    print(f"[approve-remaining-safe] approved={approved}")
    return 0 if approved == len(candidates) else 1


if __name__ == "__main__":
    raise SystemExit(main())
