"""Стадия classify — READ-ONLY Bitrix.

Для каждой строки status=ENRICHED ищем в Bitrix реквизит с RQ_INN=discovered_inn
(ENTITY_TYPE_ID=4) и выставляем target_action:

  - CREATE_REQ   — ИНН ни у кого нет → создаём реквизит для текущей компании
  - SKIP_ALREADY — ИНН уже принадлежит этой же компании (no-op)
  - MERGE_INTO   — ИНН принадлежит другой компании → готовим merge

Идемпотентность: строки уже со статусом >= CLASSIFIED пропускаются.
in_active_deal_merge=True → пропускаем со SKIP_NO_INN-меткой
(чтобы deal-merge мог сначала свести дубли, а потом мы доделаем enrich).
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..models import TargetAction
from ..sheet_store import read_queue, replace_row, update_row
from ..sheets_client import SheetsClient
from ..state import Status, is_at_least

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def run(bx: BitrixClient, sheets: SheetsClient, *, limit: int | None = None) -> dict:
    now = datetime.now(MOSCOW_TZ)
    classified = 0
    skipped_already = 0
    create_req = 0
    merge_into = 0
    skipped_active = 0

    targets = []
    for row_number, row in read_queue(sheets):
        if row.status != Status.ENRICHED:
            continue
        if is_at_least(row.status, Status.CLASSIFIED):
            continue
        targets.append((row_number, row))
        if limit is not None and len(targets) >= limit:
            break

    for row_number, row in targets:
        if row.in_active_deal_merge:
            updated = replace_row(
                row,
                status=Status.CLASSIFIED,
                target_action=TargetAction.SKIP_NO_INN,
                last_action_at=now,
                error_message="skipped: company is in active deal-merge group",
            )
            update_row(sheets, row_number, updated)
            skipped_active += 1
            continue

        if not row.discovered_inn:
            updated = replace_row(
                row,
                status=Status.CLASSIFIED,
                target_action=TargetAction.SKIP_NO_INN,
                last_action_at=now,
                error_message="enrich did not produce discovered_inn",
            )
            update_row(sheets, row_number, updated)
            continue

        matches = bx.search_requisite_by_inn(row.discovered_inn)
        target_action, merge_target = _decide(row.company_id, matches)
        updated = replace_row(
            row,
            status=Status.CLASSIFIED,
            target_action=target_action,
            merge_target_company_id=merge_target,
            last_action_at=now,
            error_message=None,
        )
        update_row(sheets, row_number, updated)

        classified += 1
        if target_action == TargetAction.CREATE_REQ:
            create_req += 1
        elif target_action == TargetAction.MERGE_INTO:
            merge_into += 1
        elif target_action == TargetAction.SKIP_ALREADY:
            skipped_already += 1

    print(
        f"[classify] CLASSIFIED: {classified}; CREATE_REQ: {create_req}; "
        f"MERGE_INTO: {merge_into}; SKIP_ALREADY: {skipped_already}; "
        f"skipped_active_deal_merge: {skipped_active}"
    )
    return {
        "classified": classified,
        "create_req": create_req,
        "merge_into": merge_into,
        "skip_already": skipped_already,
        "skipped_active_deal_merge": skipped_active,
    }


def _decide(company_id: str, matches: list[dict]) -> tuple[TargetAction, str | None]:
    """Логика classify по результатам search_requisite_by_inn."""
    if not matches:
        return TargetAction.CREATE_REQ, None
    same_owner = [m for m in matches if str(m.get("ENTITY_ID")) == str(company_id)]
    if same_owner:
        return TargetAction.SKIP_ALREADY, None
    # Берём первого «другого» владельца как target merge
    other = matches[0]
    return TargetAction.MERGE_INTO, str(other.get("ENTITY_ID"))
