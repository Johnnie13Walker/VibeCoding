"""Архивация старых backup-листов в локальные JSON-файлы."""
from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import date, datetime

from ..config import BACKUP_DIR, TAB_BACKUP_PREFIX
from ..sheet_store import read_groups, update_group
from ..sheets_client import SheetsClient
from ..state import Status


def run(sheets: SheetsClient, *, before: str) -> dict:
    before_date = date.fromisoformat(before)
    archived = 0
    skipped = 0
    deleted = 0
    for row_number, group in read_groups(sheets):
        backup_sheet = group.backup_sheet or ""
        if group.status != Status.DONE or not backup_sheet.startswith(TAB_BACKUP_PREFIX):
            continue
        rows = sheets.read(backup_sheet)
        if not rows:
            skipped += 1
            continue
        backup_date = _backup_date(rows)
        if backup_date is None or backup_date >= before_date:
            skipped += 1
            continue
        backup_file = _write_backup_file(group, rows)
        if sheets.delete_sheet(backup_sheet):
            deleted += 1
        update_group(sheets, row_number, replace(group, backup_sheet=str(backup_file)))
        archived += 1
    print(f"[archive-old-backups] archived={archived} deleted={deleted} skipped={skipped}")
    return {"archived": archived, "deleted": deleted, "skipped": skipped}


def _backup_date(rows: list[list]) -> date | None:
    if len(rows) < 2:
        return None
    headers = [str(x) for x in rows[0]]
    if "ts_msk" not in headers:
        return None
    ts_idx = headers.index("ts_msk")
    raw_ts = str(rows[1][ts_idx]) if ts_idx < len(rows[1]) else ""
    if not raw_ts:
        return None
    return datetime.fromisoformat(raw_ts).date()


def _write_backup_file(group, rows: list[list]):
    headers = [str(x) for x in rows[0]]
    losers = []
    ts_msk = ""
    for row in rows[1:]:
        values = {h: str(row[i]) if i < len(row) else "" for i, h in enumerate(headers)}
        if not ts_msk:
            ts_msk = values.get("ts_msk", "")
        loser_id = values.get("loser_id", "")
        raw_json = values.get("raw_json", "")
        if loser_id and raw_json:
            losers.append({"loser_id": loser_id, "raw": json.loads(raw_json)})
    backup_dir = BACKUP_DIR / _date_dir(ts_msk)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_file = backup_dir / f"{group.company_id}_{_safe_domain(group.domain)}.json"
    backup_data = {
        "ts_msk": ts_msk,
        "company_id": group.company_id,
        "domain": group.domain,
        "losers": losers,
    }
    backup_file.write_text(json.dumps(backup_data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return backup_file


def _date_dir(ts_msk: str) -> str:
    if not ts_msk:
        return date.today().strftime("%Y%m%d")
    return datetime.fromisoformat(ts_msk).strftime("%Y%m%d")


def _safe_domain(domain: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", domain or "no_domain")[:40]
