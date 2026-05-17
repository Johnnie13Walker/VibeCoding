"""Миграция orphan-ID поля UF_CRM_REGION_RF после пересоздания enum."""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..config import COMPANY_REGION_ENUM_MAP, COMPANY_UF_REGION, LOG_DIR
from ..scripts.region_enum_id_history import OLD_REGION_ENUM_MAP_0e32811

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
AUDIT_HEADERS = ["timestamp", "company_id", "title", "old_id", "new_id", "status", "error"]


@dataclass
class MigrationOutcome:
    company_id: str
    title: str
    old_id: str
    new_id: str
    status: str
    error: str = ""


def _build_reverse_map() -> dict[str, str]:
    """Построить orphan_old_id → new_id через нормализованный VALUE-key."""
    reverse: dict[str, str] = {}
    normalized_current = _normalized_current_region_map()
    for key, old_id in OLD_REGION_ENUM_MAP_0e32811.items():
        new_id = normalized_current.get(_normalize_region_key(key))
        if new_id:
            reverse[str(old_id)] = str(new_id)
    return reverse


def run(bx: BitrixClient, *, dry_run: bool = True, limit: int | None = None) -> dict[str, Any]:
    """Найти компании с orphan-ID в UF_CRM_REGION_RF и мигрировать на актуальный enum-ID."""
    reverse_map = _build_reverse_map()
    current_enum_ids = _current_enum_ids(bx)
    companies = list(
        bx.paginate(
            "crm.company.list",
            {
                "filter": {f"!{COMPANY_UF_REGION}": False},
                "select": ["ID", "TITLE", COMPANY_UF_REGION],
            },
        )
    )
    if limit:
        companies = companies[:limit]

    outcomes: list[MigrationOutcome] = []
    current_ids: set[str] = set()
    orphan_examples: dict[str, list[dict[str, str]]] = defaultdict(list)

    for company in companies:
        old_id = str(company.get(COMPANY_UF_REGION) or "").strip()
        if not old_id:
            continue
        current_ids.add(old_id)
        if old_id in current_enum_ids:
            continue

        company_id = str(company.get("ID") or "")
        title = str(company.get("TITLE") or "")
        if len(orphan_examples[old_id]) < 5:
            orphan_examples[old_id].append({"company_id": company_id, "title": title})

        new_id = reverse_map.get(old_id, "")
        if not new_id:
            outcomes.append(MigrationOutcome(company_id, title, old_id, "", "UNKNOWN_OLD_ID"))
            continue
        if dry_run:
            outcomes.append(MigrationOutcome(company_id, title, old_id, new_id, "DRY_RUN"))
            continue
        try:
            bx.update_company(company_id, {COMPANY_UF_REGION: new_id})
            outcome = MigrationOutcome(company_id, title, old_id, new_id, "MIGRATED")
            outcomes.append(outcome)
            _append_audit_row(outcome)
        except Exception as exc:  # noqa: BLE001
            outcomes.append(MigrationOutcome(company_id, title, old_id, new_id, "FAILED", str(exc)[:200]))

    summary = _summary(outcomes, dry_run=dry_run)
    orphan_ids = sorted(current_ids - current_enum_ids, key=lambda x: int(x) if x.isdigit() else x)
    summary.update(
        {
            "scanned_companies": len(companies),
            "actual_enum_ids": len(current_enum_ids),
            "current_value_ids": len(current_ids),
            "orphan_ids": orphan_ids,
            "orphan_breakdown": dict(Counter(outcome.old_id for outcome in outcomes)),
            "orphan_examples": dict(orphan_examples),
            "unknown_old_ids": sorted({o.old_id for o in outcomes if o.status == "UNKNOWN_OLD_ID"}),
            "outcomes": [outcome.__dict__ for outcome in outcomes],
        }
    )
    return summary


def _current_enum_ids(bx: BitrixClient) -> set[str]:
    fields = bx.get_company_user_fields()
    for field in fields:
        if str(field.get("FIELD_NAME") or "") == COMPANY_UF_REGION:
            return {str(item.get("ID") or "") for item in (field.get("LIST") or []) if str(item.get("ID") or "")}
    return set()


def _normalized_current_region_map() -> dict[str, str]:
    return {_normalize_region_key(key): value for key, value in COMPANY_REGION_ENUM_MAP.items()}


def _normalize_region_key(value: str) -> str:
    norm = str(value or "").replace("—", "-").strip().lower()
    norm = re.split(r"\s+-\s+", norm, maxsplit=1)[0]
    return re.sub(r"\s+", " ", norm).strip(" .,-")


def _summary(outcomes: list[MigrationOutcome], *, dry_run: bool) -> dict[str, Any]:
    return {
        "dry_run": dry_run,
        "dry_run_migrations": sum(1 for outcome in outcomes if outcome.status == "DRY_RUN"),
        "migrated": sum(1 for outcome in outcomes if outcome.status == "MIGRATED"),
        "failed": sum(1 for outcome in outcomes if outcome.status == "FAILED"),
        "unknown": sum(1 for outcome in outcomes if outcome.status == "UNKNOWN_OLD_ID"),
    }


def _append_audit_row(outcome: MigrationOutcome) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / "migrate_region_enum_ids.csv"
    write_header = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=AUDIT_HEADERS)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
                "company_id": outcome.company_id,
                "title": outcome.title,
                "old_id": outcome.old_id,
                "new_id": outcome.new_id,
                "status": outcome.status,
                "error": outcome.error,
            }
        )
