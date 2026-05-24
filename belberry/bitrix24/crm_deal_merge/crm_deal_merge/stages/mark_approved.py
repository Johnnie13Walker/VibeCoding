"""Approval gate — пометить выбранные группы как APPROVED."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..grouping import funnel_id
from ..sheet_store import read_groups, update_group
from ..sheets_client import SheetsClient
from ..state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def run(
    sheets: SheetsClient,
    *,
    bx: BitrixClient | None = None,
    all_: bool = False,
    smart: bool = False,
    limit: int | None = None,
    status: str = "PLAN_READY",
    company_id: str | None = None,
    domain: str | None = None,
) -> dict:
    target_status = Status(status)
    now = datetime.now(MOSCOW_TZ)
    changed = 0
    skipped: Counter[str] = Counter()
    for row_number, group in read_groups(sheets):
        if group.status != target_status:
            continue
        if limit is not None and changed >= limit:
            break
        if smart:
            ok, reason = is_smart_approvable(group, bx=bx)
            if not ok:
                skipped[reason] += 1
                continue
        elif not all_ and (str(group.company_id) != str(company_id) or (group.domain or "") != (domain or "")):
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
    if smart:
        print(f"[mark-approved] smart skipped: {dict(skipped)}")
    return {"approved": changed, "skipped": dict(skipped)}


def is_smart_approvable(group, *, bx: BitrixClient | None = None) -> tuple[bool, str]:
    if not group.inn or group.inn == "—":
        return False, "no_inn"
    if len(group.loser_ids) > 3:
        return False, "too_many_losers"
    if str(group.winner_stage or "").endswith(":WON"):
        return False, "winner_won"
    transferable = (
        group.n_activities_planned
        + group.n_timeline_planned
        + group.n_contacts_planned
        + group.n_sp_planned
    )
    if transferable > 100:
        return False, "heavy_group"
    if bx is None:
        return False, "bitrix_required"

    loser_funnels: set[str] = set()
    for loser_id in group.loser_ids:
        deal = bx.get_deal(loser_id)
        if not deal:
            return False, "loser_not_found"
        loser_funnels.add(funnel_id(deal))
    if len(loser_funnels) != 1:
        return False, "mixed_loser_funnels"
    if not loser_funnels <= {"38", "50"}:
        return False, "unsupported_loser_funnel"
    return True, "ok"
