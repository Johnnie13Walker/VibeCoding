"""Read-only verify — проверка инвариантов после merge."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..config import LOSE_STAGE_38, TIMELINE_TRANSFER_MARKER
from ..sheet_store import read_groups, update_group
from ..sheets_client import SheetsClient
from ..state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
CLOSED_STAGES = {LOSE_STAGE_38, "C50:LOSE", "C50:APOLOGY"}


def run(bx: BitrixClient, sheets: SheetsClient) -> dict:
    now = datetime.now(MOSCOW_TZ)
    ok = 0
    failed = 0
    for row_number, group in read_groups(sheets):
        if group.status != Status.MERGED:
            continue
        errors = _verify_group(bx, group)
        if errors:
            failed += 1
            update_group(sheets, row_number, replace(group, status=Status.FAILED, last_action_at=now, error_message="; ".join(errors)[:500]))
        else:
            ok += 1
            update_group(sheets, row_number, replace(group, status=Status.DONE, last_action_at=now, error_message=None))
    print(f"[verify] DONE: {ok}; FAILED: {failed}")
    return {"done": ok, "failed": failed}


def _verify_group(bx: BitrixClient, group) -> list[str]:
    errors: list[str] = []
    winner_contacts = len(bx.list_deal_contacts(group.winner_id)) if group.winner_id else 0
    winner_timeline = bx.list_deal_timeline_comments(group.winner_id) if group.winner_id else []
    if not any(TIMELINE_TRANSFER_MARKER in str(c.get("COMMENT") or "") for c in winner_timeline):
        errors.append("у WINNER нет timeline-маркера переноса")
    if winner_contacts < group.n_contacts_planned:
        errors.append("контактов на WINNER меньше планового количества")
    for loser_id in group.loser_ids:
        deal = bx.get_deal(loser_id)
        if not deal:
            errors.append(f"LOSER #{loser_id} не найден")
            continue
        if deal.get("STAGE_ID") not in CLOSED_STAGES:
            errors.append(f"LOSER #{loser_id} не закрыт в дубль/закрытую стадию")
        active = [a for a in bx.list_deal_activities(loser_id) if str(a.get("PROVIDER_ID") or "") != "VOXIMPLANT_CALL"]
        if active:
            errors.append(f"LOSER #{loser_id} имеет неперенесённые активности: {len(active)}")
    return errors
