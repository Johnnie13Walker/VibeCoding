"""WRITE escape hatch — частичный rollback группы из backup."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..config import TAB_BACKUP_PREFIX, TIMELINE_TRANSFER_MARKER
from ..sheet_store import read_groups, read_inventory, update_group
from ..sheets_client import SheetsClient
from ..state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def run(
    bx: BitrixClient,
    sheets: SheetsClient,
    *,
    company_id: str,
    domain: str,
    confirm_rollback: bool,
) -> dict:
    if not confirm_rollback:
        raise ValueError("rollback требует --confirm-rollback")
    matches = [(row, g) for row, g in read_groups(sheets) if g.company_id == company_id and (g.domain or "") == domain]
    if not matches:
        raise ValueError(f"Группа не найдена: {company_id}:{domain}")
    row_number, group = matches[0]
    backup_sheet = group.backup_sheet or f"{TAB_BACKUP_PREFIX}{company_id}_{domain}"
    backups = _read_backups(sheets, backup_sheet)
    headers, inventory = read_inventory(sheets)
    restored = 0
    for loser_id, raw in backups.items():
        stage_id = raw.get("STAGE_ID")
        if stage_id:
            bx.update_deal(loser_id, {"STAGE_ID": stage_id, "COMMENTS": raw.get("COMMENTS") or ""})
            restored += 1
    for _, inv in inventory:
        if inv.get("company_id") != company_id or inv.get("loser_id") not in group.loser_ids:
            continue
        if inv.get("entity_type") == "activity" and inv.get("transferred") == "1":
            bx.reassign_activity(inv.get("child_id", ""), inv.get("loser_id", ""))
    if group.winner_id:
        for comment in bx.list_deal_timeline_comments(group.winner_id):
            text = str(comment.get("COMMENT") or "")
            if any(f"{TIMELINE_TRANSFER_MARKER} #{loser_id}" in text for loser_id in group.loser_ids):
                bx.delete_timeline_comment(str(comment.get("ID") or ""))
    update_group(sheets, row_number, replace(group, status=Status.ROLLED_BACK, last_action_at=datetime.now(MOSCOW_TZ), error_message=None))
    print(f"[rollback] restored losers: {restored}")
    return {"restored_losers": restored}


def _read_backups(sheets: SheetsClient, backup_sheet: str) -> dict[str, dict]:
    if _looks_like_file_path(backup_sheet):
        return _read_file_backups(Path(backup_sheet))
    return _read_sheet_backups(sheets, backup_sheet)


def _read_file_backups(backup_file: Path) -> dict[str, dict]:
    if not backup_file.exists():
        raise ValueError(f"Бэкап не найден: {backup_file}")
    data = json.loads(backup_file.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for entry in data.get("losers", []):
        loser_id = str(entry.get("loser_id") or "")
        raw = entry.get("raw")
        if loser_id and isinstance(raw, dict):
            out[loser_id] = raw
    return out


def _read_sheet_backups(sheets: SheetsClient, backup_sheet: str) -> dict[str, dict]:
    rows = sheets.read(backup_sheet)
    if not rows:
        return {}
    headers = [str(x) for x in rows[0]]
    out: dict[str, dict] = {}
    for row in rows[1:]:
        values = {h: str(row[i]) if i < len(row) else "" for i, h in enumerate(headers)}
        loser_id = values.get("loser_id")
        raw_json = values.get("raw_json")
        if loser_id and raw_json:
            out[loser_id] = json.loads(raw_json)
    return out


def _looks_like_file_path(value: str) -> bool:
    return "/" in value or "\\" in value or value.endswith(".json")
