"""Read-only аудит бизнес-SP у уже обработанных пилотных групп."""
from __future__ import annotations

from collections import Counter
from typing import Any

from ..bitrix_client import BitrixClient
from ..sheet_store import read_groups
from ..sheets_client import SheetsClient
from .inventory_spotcheck import TELEMETRY_SP_TYPES


def run(bx: BitrixClient, sheets: SheetsClient, *, groups_arg: str) -> dict[str, Any]:
    requested = set(parse_groups(groups_arg))
    groups = [group for _, group in read_groups(sheets) if (group.company_id, group.domain or "") in requested]
    found_keys = {(group.company_id, group.domain or "") for group in groups}
    missing = sorted(f"{company_id}:{domain}" for company_id, domain in requested - found_keys)

    type_names = _smart_type_names(bx)
    manual_actions: list[dict[str, str]] = []
    counts: Counter[str] = Counter()

    for group in groups:
        group_has_business_sp = False
        for loser_id in group.loser_ids:
            for entity_type_id, items in bx.list_smart_items_for_deal(loser_id):
                entity_type_id = int(entity_type_id)
                if entity_type_id in TELEMETRY_SP_TYPES:
                    continue
                for item in items:
                    group_has_business_sp = True
                    item_id = str(item.get("id") or item.get("ID") or "")
                    title = str(item.get("title") or item.get("TITLE") or "")
                    action = {
                        "company_id": group.company_id,
                        "domain": group.domain or "",
                        "loser_id": loser_id,
                        "winner_id": group.winner_id or "",
                        "entity_type_id": str(entity_type_id),
                        "entity_name": type_names.get(entity_type_id, ""),
                        "item_id": item_id,
                        "title": title,
                    }
                    manual_actions.append(action)
                    counts[str(entity_type_id)] += 1
                    print(
                        "[РУЧНОЙ ПЕРЕНОС НУЖЕН] "
                        f"LOSER #{loser_id} domain {group.domain} -> "
                        f"перепривязать SP:{entity_type_id} #{item_id} к WINNER #{group.winner_id} в UI"
                    )
        if not group_has_business_sp:
            print(f"OK, пилот {group.company_id}:{group.domain} без бизнес-SP")

    if missing:
        print(f"[audit-pilot-sp] группы не найдены: {', '.join(missing)}")

    return {
        "groups_checked": len(groups),
        "missing": missing,
        "manual_actions": manual_actions,
        "business_sp_counts": dict(counts),
    }


def parse_groups(raw: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        if ":" not in value:
            raise ValueError(f"--groups ожидает COMPANY_ID:DOMAIN, получено: {value}")
        company_id, domain = value.split(":", 1)
        out.append((company_id.strip(), domain.strip()))
    return out


def _smart_type_names(bx: BitrixClient) -> dict[int, str]:
    names: dict[int, str] = {}
    for item in bx.smart_process_types():
        raw_id = item.get("entityTypeId")
        if raw_id is None:
            continue
        names[int(raw_id)] = str(
            item.get("title")
            or item.get("TITLE")
            or item.get("name")
            or item.get("NAME")
            or ""
        )
    return names
