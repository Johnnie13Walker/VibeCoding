#!/usr/bin/env python3
"""Удаление строгих пустых компаний из Б24 с backup и архивом в Google Sheets."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_DIR.parents[2]
sys.path.insert(0, str(PROJECT_DIR))

from crm_deal_merge.bitrix_client import BitrixClient  # noqa: E402
from crm_deal_merge.config import LOG_PATH, SERVICE_ACCOUNT_JSON, STATE_PATH  # noqa: E402
from crm_deal_merge.sheets_client import SheetsClient  # noqa: E402

SHEET_ID = "13L0gqwkNzrWacYeI5TzkOxZuRuXn5bBCtfxx-uzHH_4"
SOURCE_TAB = "Пустые компании"
ARCHIVE_TAB = "Удаленные пустые компании"
MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-delete", action="store_true")
    parser.add_argument("--include-phone-title", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.confirm_delete and not _delete_env_enabled():
        raise SystemExit("Для реального удаления нужен BITRIX_ALLOW_DELETE=1 вместе с --confirm-delete.")

    bx = BitrixClient(STATE_PATH, log_path=LOG_PATH)
    sheets = SheetsClient(SHEET_ID, SERVICE_ACCOUNT_JSON)
    rows = sheets.read(SOURCE_TAB, "A1:AC2000", unformatted=True)
    if not rows:
        raise RuntimeError("Лист пуст")
    headers = [str(x) for x in rows[0]]
    idx = {h: i for i, h in enumerate(headers)}
    candidates = []
    for row_number, row in enumerate(rows[1:], start=2):
        if is_strict_candidate(row, idx, include_phone_title=args.include_phone_title):
            candidates.append((row_number, normalize_row(row, len(headers))))
    if args.limit:
        candidates = candidates[: args.limit]

    print(json.dumps({"strict_candidates": len(candidates), "confirm_delete": args.confirm_delete}, ensure_ascii=False))
    if not args.confirm_delete:
        for row_number, row in candidates[:50]:
            print(f"DRY-RUN row={row_number} company_id={value(row, idx, 'company_id')} title={row[0] if row else ''}")
        return

    now = datetime.now(MOSCOW_TZ)
    backup_dir = REPO_ROOT / "belberry" / "bitrix24" / "backups" / "delete_empty_companies" / now.strftime("%Y%m%d")
    backup_dir.mkdir(parents=True, exist_ok=True)
    archive_rows = build_archive_rows(headers, candidates, now)

    deleted: list[tuple[int, str]] = []
    skipped: list[dict] = []
    for row_number, row in candidates:
        company_id = value(row, idx, "company_id")
        check = fresh_check(bx, company_id)
        if not check["ok_to_delete"]:
            skipped.append({"row": row_number, "company_id": company_id, "reason": check["reason"]})
            continue
        backup_path = backup_dir / f"{company_id}_{safe_name(row[0] if row else 'company')}.json"
        backup_path.write_text(json.dumps(check["backup"], ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        body = bx.call("crm.company.delete", {"id": company_id})
        if body.get("result") is True:
            deleted.append((row_number, company_id))
        else:
            skipped.append({"row": row_number, "company_id": company_id, "reason": f"delete_result={body.get('result')!r}"})

    if deleted:
        sheets.ensure_sheet(ARCHIVE_TAB)
        existing = sheets.read(ARCHIVE_TAB, "A1:AZ2")
        if not existing:
            sheets.update(ARCHIVE_TAB, "A1", [archive_rows[0]], value_input_option="USER_ENTERED")
            sheets.append(ARCHIVE_TAB, archive_rows[1:], value_input_option="USER_ENTERED")
        else:
            sheets.append(ARCHIVE_TAB, archive_rows[1:], value_input_option="USER_ENTERED")
        delete_sheet_rows(sheets, SOURCE_TAB, [row_number for row_number, _ in deleted])

    verify_deleted = []
    for _row_number, company_id in deleted:
        company = bx.get_company(company_id)
        verify_deleted.append({"company_id": company_id, "deleted": company is None})

    print(json.dumps({
        "deleted": len(deleted),
        "skipped": skipped,
        "verify_deleted": verify_deleted,
        "backup_dir": str(backup_dir),
    }, ensure_ascii=False, indent=2))


def is_strict_candidate(row: list, idx: dict[str, int], include_phone_title: bool = False) -> bool:
    if not value(row, idx, "company_id"):
        return False
    if value(row, idx, "Есть дубль") != "нет":
        return False
    if "кандидат на удаление" not in value(row, idx, "Рекомендация"):
        return False
    if to_number(value(row, idx, "Контактов")) or to_number(value(row, idx, "Сделок")) or to_number(value(row, idx, "Лидов")):
        return False
    if to_number(value(row, idx, "Оборот компании")) != 0:
        return False
    phone = value(row, idx, "Телефон в карточке")
    if value(row, idx, "Email в карточке") or value(row, idx, "Комментарий"):
        return False
    if value(row, idx, "Сайт в Б24") or value(row, idx, "Сайт найден"):
        return False
    if phone and not (include_phone_title and title_is_phone(value(row, idx, "Компания (название, гиперссылка в Б24)"))):
        return False
    return True


def fresh_check(bx: BitrixClient, company_id: str) -> dict:
    company = bx.get_company(company_id)
    if not company:
        return {"ok_to_delete": False, "reason": "company_not_found", "backup": {}}
    contacts = list(bx.paginate("crm.contact.list", {"filter": {"COMPANY_ID": company_id}, "select": ["ID", "COMPANY_ID"]}))
    deals = list(bx.paginate("crm.deal.list", {"filter": {"COMPANY_ID": company_id}, "select": ["ID", "TITLE", "COMPANY_ID"]}))
    leads = list(bx.paginate("crm.lead.list", {"filter": {"COMPANY_ID": company_id}, "select": ["ID", "TITLE", "COMPANY_ID"]}))
    requisites = list(bx.paginate("crm.requisite.list", {"filter": {"ENTITY_TYPE_ID": 4, "ENTITY_ID": company_id}}))
    ok = not contacts and not deals and not leads
    reason = "ok" if ok else f"fresh_links contacts={len(contacts)} deals={len(deals)} leads={len(leads)}"
    return {
        "ok_to_delete": ok,
        "reason": reason,
        "backup": {
            "company": company,
            "contacts": contacts,
            "deals": deals,
            "leads": leads,
            "requisites": requisites,
            "checked_at_msk": datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
        },
    }


def build_archive_rows(headers: list[str], candidates: list[tuple[int, list]], now: datetime) -> list[list]:
    archive_headers = ["deleted_at_msk", "source_row"] + headers
    out = [archive_headers]
    ts = now.isoformat(timespec="seconds")
    for row_number, row in candidates:
        out.append([ts, str(row_number)] + row)
    return out


def delete_sheet_rows(sheets: SheetsClient, title: str, row_numbers_1_based: list[int]) -> None:
    sheet_id = sheets.ensure_sheet(title)
    requests = []
    for row_number in sorted(row_numbers_1_based, reverse=True):
        start_index = row_number - 1
        requests.append({
            "deleteDimension": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": start_index,
                    "endIndex": start_index + 1,
                }
            }
        })
    for off in range(0, len(requests), 100):
        body = {"requests": requests[off : off + 100]}
        req = sheets.service.spreadsheets().batchUpdate(spreadsheetId=sheets.sheet_id, body=body)
        sheets._execute_with_retry(req)


def normalize_row(row: list, width: int) -> list:
    return list(row) + [""] * max(0, width - len(row))


def value(row: list, idx: dict[str, int], name: str) -> str:
    i = idx.get(name)
    return str(row[i]).strip() if i is not None and len(row) > i else ""


def to_number(raw: str) -> float:
    try:
        return float(str(raw or "0").replace(" ", "").replace(",", "."))
    except ValueError:
        return 0.0


def title_is_phone(title: str) -> bool:
    text = str(title or "").strip().lower()
    digits = re.sub(r"\D+", "", text)
    letters = re.sub(r"[^a-zа-я]+", "", text)
    return len(digits) >= 7 and len(letters) <= 2


def _delete_env_enabled() -> bool:
    return os.environ.get("BITRIX_ALLOW_DELETE", "0") == "1"


def safe_name(raw: str) -> str:
    out = "".join(ch if ch.isalnum() else "_" for ch in str(raw).lower()).strip("_")
    return out[:80] or "company"


if __name__ == "__main__":
    main()
