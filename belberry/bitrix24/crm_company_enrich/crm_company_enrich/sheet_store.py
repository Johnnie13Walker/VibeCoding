"""Хелперы чтения/записи листа company_enrich_queue.

Идемпотентность: discover не перезаписывает строки status != NEW;
update_row пишет одну строку по row_number (1-based, как в Sheets A1).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from .config import TAB_QUEUE
from .models import QUEUE_HEADERS, QueueRow
from .sheets_client import SheetsClient


def ensure_queue_sheet(sheets: SheetsClient) -> None:
    sheets.ensure_sheet(TAB_QUEUE)
    existing = sheets.read(TAB_QUEUE, "A1:Z1")
    if not existing or not existing[0]:
        sheets.update(TAB_QUEUE, "A1", [QUEUE_HEADERS])


def read_queue(sheets: SheetsClient) -> list[tuple[int, QueueRow]]:
    """Возвращает [(row_number_1based, QueueRow), ...]; пропускает пустые строки.

    row_number включает строку заголовка (т.е. первая data-строка → 2).
    """
    rows = sheets.read(TAB_QUEUE)
    if not rows:
        return []
    headers = [str(x) for x in rows[0]]
    out: list[tuple[int, QueueRow]] = []
    for idx, raw in enumerate(rows[1:], start=2):
        if not raw or not str(raw[0]).strip():
            continue
        out.append((idx, QueueRow.from_sheet_row(raw, headers)))
    return out


def write_queue_rows(sheets: SheetsClient, rows: Iterable[QueueRow]) -> None:
    """Перезаписать всю очередь (используется только в discover при первом запуске).

    Бережно: при последующих запусках discover должен использовать
    upsert_queue_rows, чтобы не затирать уже обработанные строки.
    """
    ensure_queue_sheet(sheets)
    sheets.clear(TAB_QUEUE)
    sheets.update(TAB_QUEUE, "A1", [QUEUE_HEADERS])
    payload = [r.to_sheet_row() for r in rows]
    if payload:
        sheets.update(TAB_QUEUE, f"A2:T{len(payload) + 1}", payload)


def upsert_queue_rows(sheets: SheetsClient, rows: Iterable[QueueRow]) -> dict:
    """Идемпотентный апдейт. Существующие строки с status != NEW сохраняются.

    Возвращает {"updated": N, "appended": M, "kept": K}.
    """
    ensure_queue_sheet(sheets)
    existing = read_queue(sheets)
    existing_by_id = {row.company_id: (row_number, row) for row_number, row in existing}
    headers = QUEUE_HEADERS

    updates: list[dict] = []
    appends: list[list[str]] = []
    kept = 0
    new_rows = list(rows)

    for r in new_rows:
        if r.company_id in existing_by_id:
            row_number, existing_row = existing_by_id[r.company_id]
            if existing_row.status.value != "NEW":
                kept += 1
                continue
            updates.append(
                {"range": f"{TAB_QUEUE}!A{row_number}:T{row_number}", "values": [r.to_sheet_row()]}
            )
        else:
            appends.append(r.to_sheet_row())

    if updates:
        sheets.batch_update(updates)
    if appends:
        sheets.append(TAB_QUEUE, appends)

    return {"updated": len(updates), "appended": len(appends), "kept": kept}


def update_row(sheets: SheetsClient, row_number: int, row: QueueRow) -> None:
    sheets.update(
        TAB_QUEUE,
        f"A{row_number}:T{row_number}",
        [row.to_sheet_row()],
    )


def replace_row(row: QueueRow, **changes) -> QueueRow:
    """Удобный alias dataclasses.replace для импорта одной строкой."""
    return replace(row, **changes)
