"""Стадия inventory — собрать связи LOSER-сделок перед переносом."""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..models import InventoryRecord
from ..sheet_store import append_inventory, read_groups, read_inventory, update_group
from ..sheets_client import SheetsClient
from ..state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def run(bx: BitrixClient, sheets: SheetsClient, limit: int | None = None) -> dict:
    targets = [(row, g) for row, g in read_groups(sheets) if g.status in {Status.NEW, Status.INVENTORIED}]
    if limit:
        targets = targets[:limit]
    if not targets:
        print("[inventory] нет групп NEW/INVENTORIED")
        return {"processed": 0}

    processed = 0
    total = 0
    counts: Counter[str] = Counter()
    now = datetime.now(MOSCOW_TZ)
    _, existing_rows = read_inventory(sheets)
    existing_keys = {
        (row.get("company_id", ""), row.get("loser_id", ""), row.get("entity_type", ""), row.get("child_id", ""))
        for _, row in existing_rows
    }
    for row_number, group in targets:
        records = _collect_group_inventory(bx, group.company_id, group.loser_ids)
        new_records = [
            r for r in records
            if (r.company_id, r.loser_id, r.entity_type, r.child_id) not in existing_keys
        ]
        existing_keys.update((r.company_id, r.loser_id, r.entity_type, r.child_id) for r in new_records)
        counts.update(r.entity_type for r in records)
        append_inventory(sheets, new_records)
        updated = replace(
            group,
            status=Status.INVENTORIED,
            n_activities_planned=sum(1 for r in records if r.entity_type == "activity"),
            n_timeline_planned=sum(1 for r in records if r.entity_type == "timeline"),
            n_contacts_planned=sum(1 for r in records if r.entity_type == "contact"),
            n_sp_planned=sum(1 for r in records if r.entity_type.startswith("sp:")),
            last_action_at=now,
            error_message=None,
        )
        update_group(sheets, row_number, updated)
        processed += 1
        total += len(records)
        print(f"[inventory] group {group.company_id}:{group.domain or '-'} — {len(records)} связей, новых {len(new_records)}")
    return {"processed": processed, "records": total, "types": dict(counts)}


def _collect_group_inventory(bx: BitrixClient, company_id: str, loser_ids: list[str]) -> list[InventoryRecord]:
    records: list[InventoryRecord] = []
    for loser_id in loser_ids:
        for activity in bx.list_deal_activities(loser_id):
            records.append(
                InventoryRecord(
                    company_id=company_id,
                    loser_id=loser_id,
                    entity_type="activity",
                    child_id=str(activity.get("ID") or ""),
                    child_subject=str(activity.get("SUBJECT") or ""),
                    details=json.dumps(
                        {
                            "PROVIDER_ID": activity.get("PROVIDER_ID"),
                            "TYPE_ID": activity.get("TYPE_ID"),
                            "COMPLETED": activity.get("COMPLETED"),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )
            )
        for comment in bx.list_deal_timeline_comments(loser_id):
            records.append(
                InventoryRecord(
                    company_id=company_id,
                    loser_id=loser_id,
                    entity_type="timeline",
                    child_id=str(comment.get("ID") or ""),
                    child_subject=str(comment.get("COMMENT") or "")[:200],
                    details=json.dumps(comment, ensure_ascii=False, sort_keys=True),
                )
            )
        for contact in bx.list_deal_contacts(loser_id):
            records.append(
                InventoryRecord(
                    company_id=company_id,
                    loser_id=loser_id,
                    entity_type="contact",
                    child_id=str(contact.get("CONTACT_ID") or contact.get("ID") or ""),
                    child_subject=str(contact.get("SORT") or ""),
                    details=json.dumps(contact, ensure_ascii=False, sort_keys=True),
                )
            )
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
