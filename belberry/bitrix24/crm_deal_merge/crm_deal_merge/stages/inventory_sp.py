"""Добор smart-process строк в уже собранный inventory."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..models import InventoryRecord
from ..sheet_store import append_inventory, read_groups, read_inventory, update_group
from ..sheets_client import SheetsClient
from ..state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
DEFAULT_STATUSES = {Status.PLAN_READY, Status.INVENTORIED}


def run(
    bx: BitrixClient,
    sheets: SheetsClient,
    *,
    limit: int | None = None,
    statuses: set[Status] | None = None,
) -> dict:
    target_statuses = statuses or DEFAULT_STATUSES
    targets = [(row, group) for row, group in read_groups(sheets) if group.status in target_statuses]
    if limit:
        targets = targets[:limit]
    if not targets:
        print("[enrich-sp] нет групп для добора SP")
        return {"processed": 0, "added": 0, "types": {}}

    headers, rows = read_inventory(sheets)
    existing_keys = {
        (row.get("company_id", ""), row.get("loser_id", ""), row.get("entity_type", ""), row.get("child_id", ""))
        for _, row in rows
    }
    sp_counts_by_group = _sp_counts_by_group(rows)
    processed = 0
    added = 0
    counts: Counter[str] = Counter()
    now = datetime.now(MOSCOW_TZ)

    for row_number, group in targets:
        records = _collect_sp_records(bx, group.company_id, group.loser_ids)
        new_records = [
            record
            for record in records
            if (record.company_id, record.loser_id, record.entity_type, record.child_id) not in existing_keys
        ]
        append_inventory(sheets, new_records)
        for record in new_records:
            key = (record.company_id, record.loser_id, record.entity_type, record.child_id)
            existing_keys.add(key)
            sp_counts_by_group[record.company_id][record.entity_type] += 1
            counts[record.entity_type] += 1

        n_sp_planned = sum(sp_counts_by_group[group.company_id].values())
        update_group(
            sheets,
            row_number,
            replace(group, n_sp_planned=n_sp_planned, last_action_at=now, error_message=None),
        )
        processed += 1
        added += len(new_records)
        print(
            f"[enrich-sp] group {group.company_id}:{group.domain or '-'} — "
            f"новых SP {len(new_records)}, всего SP {n_sp_planned}"
        )

    return {"processed": processed, "added": added, "types": dict(counts)}


def parse_statuses(raw: str | None) -> set[Status] | None:
    if not raw:
        return None
    return {Status(item.strip()) for item in raw.split(",") if item.strip()}


def _collect_sp_records(bx: BitrixClient, company_id: str, loser_ids: list[str]) -> list[InventoryRecord]:
    records: list[InventoryRecord] = []
    for loser_id in loser_ids:
        print(f"[enrich-sp]   loser #{loser_id}: ищу smart-process")
        for entity_type_id, items in bx.list_smart_items_for_deal(loser_id):
            for item in items:
                records.append(
                    InventoryRecord(
                        company_id=company_id,
                        loser_id=loser_id,
                        entity_type=f"sp:{entity_type_id}",
                        child_id=str(item.get("id") or item.get("ID") or ""),
                        child_subject=str(item.get("title") or item.get("TITLE") or ""),
                        details=json.dumps(item, ensure_ascii=False, sort_keys=True),
                    )
                )
    return records


def _sp_counts_by_group(rows: list[tuple[int, dict[str, str]]]) -> dict[str, Counter[str]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for _, row in rows:
        entity_type = row.get("entity_type", "")
        if entity_type.startswith("sp:"):
            counts[row.get("company_id", "")][entity_type] += 1
    return counts
