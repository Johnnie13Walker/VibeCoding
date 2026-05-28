"""Пометить выбранные inventory-строки как пропущенные."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import TAB_INVENTORY
from ..sheet_store import read_inventory, update_inventory_row
from ..sheets_client import SheetsClient

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def run(
    sheets: SheetsClient,
    *,
    entity_type_prefix: str,
    where: dict[str, str] | None = None,
    all_companies: bool = False,
    note: str = "skipped_sp_telemetry",
) -> dict:
    if len(entity_type_prefix) < len("sp:1040"):
        raise ValueError("entity_type_prefix должен быть точным, например sp:1040")
    where = where or {}
    company_id = where.get("company_id")
    if not all_companies and not company_id:
        raise ValueError("skip-inventory требует --where company-id=ID или --all-companies")
    headers, rows = read_inventory(sheets)
    now = datetime.now(MOSCOW_TZ)
    changed = 0
    changed_rows: list[tuple[int, dict[str, str]]] = []
    for row_number, values in rows:
        if company_id and values.get("company_id") != str(company_id):
            continue
        if not values.get("entity_type", "").startswith(entity_type_prefix):
            continue
        values["transferred"] = "1"
        values["transferred_at"] = now.isoformat(timespec="seconds")
        values["note"] = note
        changed_rows.append((row_number, values))
        changed += 1
    if all_companies and changed_rows:
        _bulk_update_inventory(sheets, headers, rows)
    else:
        for row_number, values in changed_rows:
            update_inventory_row(
                sheets,
                row_number,
                headers,
                values,
                transferred=True,
                transferred_at=now,
                note=note,
            )
    scope = "all-companies" if all_companies else f"company_id={company_id}"
    print(f"[skip-inventory] {scope} prefix={entity_type_prefix}: {changed}")
    return {
        "changed": changed,
        "company_id": str(company_id) if company_id else None,
        "all_companies": all_companies,
        "entity_type_prefix": entity_type_prefix,
    }


def _bulk_update_inventory(sheets: SheetsClient, headers: list[str], rows: list[tuple[int, dict[str, str]]]) -> None:
    if not rows:
        return
    start_row = min(row_number for row_number, _ in rows)
    end_row = max(row_number for row_number, _ in rows)
    payload = [[values.get(header, "") for header in headers] for _, values in rows]
    sheets.update(TAB_INVENTORY, f"A{start_row}:I{end_row}", payload)


def parse_where(items: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"--where должен быть key=value, получено: {item}")
        key, value = item.split("=", 1)
        normalized_key = key.strip().replace("-", "_")
        out[normalized_key] = value.strip()
    return out
