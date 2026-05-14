"""Общие операции чтения/обновления очереди merge в Sheets."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Iterable

from .config import TAB_GROUPS, TAB_INVENTORY
from .models import GROUP_HEADERS, INVENTORY_HEADERS, Group, InventoryRecord
from .sheets_client import SheetsClient


def read_groups(sheets: SheetsClient) -> list[tuple[int, Group]]:
    rows = sheets.read(TAB_GROUPS)
    if not rows:
        return []
    headers = [str(x) for x in rows[0]]
    missing = [h for h in GROUP_HEADERS if h not in headers]
    if missing:
        raise ValueError(f"Лист {TAB_GROUPS} не содержит колонки: {missing}")
    out: list[tuple[int, Group]] = []
    for row_number, row in enumerate(rows[1:], start=2):
        if any(str(x).strip() for x in row):
            out.append((row_number, Group.from_sheet_row([str(x) for x in row], headers)))
    return out


def update_group(sheets: SheetsClient, row_number: int, group: Group) -> None:
    end_col = _col_name(len(GROUP_HEADERS))
    sheets.update(
        TAB_GROUPS,
        f"A{row_number}:{end_col}{row_number}",
        [group.to_sheet_row()],
        value_input_option="USER_ENTERED",
    )


def write_groups(sheets: SheetsClient, groups: Iterable[Group]) -> None:
    sheets.ensure_sheet(TAB_GROUPS)
    sheets.clear(TAB_GROUPS)
    sheets.append(TAB_GROUPS, [GROUP_HEADERS])
    rows = [g.to_sheet_row() for g in groups]
    for off in range(0, len(rows), 200):
        sheets.append(TAB_GROUPS, rows[off : off + 200], value_input_option="USER_ENTERED")


def ensure_inventory(sheets: SheetsClient) -> None:
    sheets.ensure_sheet(TAB_INVENTORY)
    rows = sheets.read(TAB_INVENTORY, "A1:I1")
    if not rows:
        sheets.update(TAB_INVENTORY, "A1", [INVENTORY_HEADERS])


def append_inventory(sheets: SheetsClient, records: list[InventoryRecord]) -> None:
    if records:
        ensure_inventory(sheets)
        sheets.append(TAB_INVENTORY, [r.to_sheet_row() for r in records])


def read_inventory(sheets: SheetsClient) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    rows = sheets.read(TAB_INVENTORY)
    if not rows:
        return INVENTORY_HEADERS, []
    headers = [str(x) for x in rows[0]]
    out: list[tuple[int, dict[str, str]]] = []
    for row_number, row in enumerate(rows[1:], start=2):
        values = {h: str(row[i]) if i < len(row) else "" for i, h in enumerate(headers)}
        if values.get("company_id"):
            out.append((row_number, values))
    return headers, out


def update_inventory_row(
    sheets: SheetsClient,
    row_number: int,
    headers: list[str],
    values: dict[str, str],
    *,
    transferred: bool,
    transferred_at: datetime | None,
    note: str = "",
) -> None:
    values["transferred"] = "1" if transferred else "0"
    values["transferred_at"] = transferred_at.isoformat(timespec="seconds") if transferred_at else ""
    values["note"] = note
    row = [values.get(h, "") for h in headers]
    sheets.update(TAB_INVENTORY, f"A{row_number}:{_col_name(len(headers))}{row_number}", [row])


def touch(group: Group, *, status, now: datetime, error_message: str | None = None, **kwargs) -> Group:
    return replace(group, status=status, last_action_at=now, error_message=error_message, **kwargs)


def _col_name(index: int) -> str:
    out = ""
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out
