#!/usr/bin/env python3
"""Удаление компаний с Score=3 + Safe-to-delete=да из вкладки «Пустые компании (скоринг)».

Перед удалением каждая компания заново проверяется через Bitrix API
(не появилось ли deals/contacts/leads между snapshot и сейчас). Удалённые
переносятся в архивную вкладку «Удаленные пустые компании (скоринг)»;
бэкапы (компания + связки + реквизиты) сохраняются в JSON.

Запуск (на VPS, через wrapper для env):
  /usr/local/bin/cloudbot-empty-companies-score.sh -- DOES NOT SUPPORT this script;
запускается напрямую:

  BITRIX_STATE_PATH=/opt/openclaw/state/bitrix_app/install.latest.json \\
  GOOGLE_SERVICE_ACCOUNT_JSON=/opt/openclaw/secrets/finance-director-sheets.json \\
  BITRIX_ALLOW_DELETE=1 \\
  /opt/openclaw/venvs/crm_company_merge/bin/python \\
  /opt/openclaw/repos/vibecoding/belberry/bitrix24/empty_companies_score/scripts/delete_score3_safe.py \\
  [--confirm-delete] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_DIR.parents[2]
sys.path.insert(0, str(PROJECT_DIR))

from google.oauth2.service_account import Credentials  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402

from empty_companies_score.bitrix_client import BitrixClient  # noqa: E402
from empty_companies_score.config import (  # noqa: E402
    BITRIX_STATE,
    PORTAL_BASE,
    SA_KEY,
    SHEET_ID,
    TARGET_TAB,
)

ARCHIVE_TAB = "Удаленные пустые компании (скоринг)"
BACKUP_ROOT = REPO_ROOT / "belberry" / "bitrix24" / "backups" / "delete_score3_safe"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--confirm-delete", action="store_true", help="без флага — dry-run")
    p.add_argument("--limit", type=int, help="обработать не больше N кандидатов")
    args = p.parse_args()
    if args.confirm_delete and not _delete_env_enabled():
        print(
            "Для реального удаления нужен BITRIX_ALLOW_DELETE=1 вместе с --confirm-delete.",
            file=sys.stderr,
        )
        return 2

    bx = BitrixClient(BITRIX_STATE)
    sheets = _sheets()
    source_gid = _gid(sheets, TARGET_TAB)

    rows = _read(sheets, TARGET_TAB, "A1:R5000")
    if not rows:
        print("source tab пуста", file=sys.stderr)
        return 1
    headers = rows[0]
    idx = {h: i for i, h in enumerate(headers)}
    required = ["Score (0-3)", "Safe-to-delete", "company_id"]
    missing = [r for r in required if r not in idx]
    if missing:
        print(f"в шапке не хватает колонок: {missing}", file=sys.stderr)
        return 1

    candidates: list[tuple[int, list]] = []
    for row_number, row in enumerate(rows[1:], start=2):
        score = _to_int(_get(row, idx, "Score (0-3)"))
        safe = _get(row, idx, "Safe-to-delete").lower()
        cid = _get(row, idx, "company_id")
        if score == 3 and safe == "да" and cid:
            candidates.append((row_number, row))

    if args.limit:
        candidates = candidates[: args.limit]

    print(json.dumps({"candidates": len(candidates), "confirm_delete": args.confirm_delete}, ensure_ascii=False))

    if not args.confirm_delete:
        for row_number, row in candidates[:10]:
            cid = _get(row, idx, "company_id")
            title = (row[0] if row else "").strip()
            print(f"DRY row={row_number} company_id={cid} title={title!r} "
                  f"link={PORTAL_BASE}/{cid}/")
        if len(candidates) > 10:
            print(f"... и ещё {len(candidates) - 10} кандидатов")
        print("\nДля реального удаления добавь --confirm-delete.")
        return 0

    now = datetime.now(timezone.utc).astimezone()
    backup_dir = BACKUP_ROOT / now.strftime("%Y%m%d_%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)

    deleted: list[tuple[int, str]] = []
    skipped: list[dict] = []

    for row_number, row in candidates:
        cid = _get(row, idx, "company_id")
        title = (row[0] if row else "").strip()
        check = _fresh_check(bx, cid)

        # Already-deleted (например, прошлый прогон упал посреди итерации) — заархивируем,
        # backup-файл не пишем (карточки уже нет в Bitrix).
        if check["reason"] == "already_deleted":
            deleted.append((row_number, cid))
            print(f"GONE row={row_number} #{cid} '{title[:60]}' — already removed")
            continue

        if not check["ok_to_delete"]:
            skipped.append({"row": row_number, "company_id": cid, "reason": check["reason"]})
            print(f"SKIP row={row_number} #{cid} — {check['reason']}")
            continue

        (backup_dir / f"{cid}_{_safe_name(title)}.json").write_text(
            json.dumps(check["backup"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        body = bx.call("crm.company.delete", [("id", cid)])
        if body.get("result") is True:
            deleted.append((row_number, cid))
            print(f"DEL  row={row_number} #{cid} '{title[:60]}'")
        else:
            err = body.get("error_description") or body.get("error") or str(body.get("result"))
            skipped.append({"row": row_number, "company_id": cid, "reason": f"delete_failed: {err}"})
            print(f"FAIL row={row_number} #{cid} — {err}")

    if deleted:
        _ensure_tab(sheets, ARCHIVE_TAB, len(deleted) + 50, len(headers) + 2)
        ts = now.isoformat(timespec="seconds")
        archive_headers = ["deleted_at_msk", "source_row"] + list(headers)
        archive_rows = [[ts, str(rn)] + list(rows[rn - 1]) for rn, _ in deleted]
        _append(sheets, ARCHIVE_TAB, "A1", [archive_headers], replace_if_empty=True)
        _append(sheets, ARCHIVE_TAB, "A1", archive_rows, replace_if_empty=False)
        _delete_rows(sheets, source_gid, [rn for rn, _ in deleted])

    verify = []
    for _, cid in deleted:
        body = bx.call("crm.company.get", [("id", cid)])
        gone = body.get("error_description") == "Not found" or body.get("result") in (None, False, [])
        verify.append({"company_id": cid, "deleted": gone})

    print()
    print(json.dumps({
        "deleted": len(deleted),
        "skipped": skipped,
        "verify_all_gone": all(v["deleted"] for v in verify),
        "backup_dir": str(backup_dir),
    }, ensure_ascii=False, indent=2))
    return 0


# ---- helpers ----

def _sheets():
    creds = Credentials.from_service_account_file(
        SA_KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _delete_env_enabled() -> bool:
    return os.environ.get("BITRIX_ALLOW_DELETE", "0") == "1"


def _gid(svc, tab: str) -> int:
    meta = svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == tab:
            return s["properties"]["sheetId"]
    raise RuntimeError(f"tab not found: {tab}")


def _read(svc, tab: str, range_a1: str) -> list[list]:
    res = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=f"{tab}!{range_a1}", valueRenderOption="UNFORMATTED_VALUE"
    ).execute()
    return res.get("values", [])


def _append(svc, tab: str, anchor: str, rows: list[list], replace_if_empty: bool) -> None:
    if not rows:
        return
    if replace_if_empty:
        existing = _read(svc, tab, "A1:B2")
        if not existing:
            svc.spreadsheets().values().update(
                spreadsheetId=SHEET_ID, range=f"{tab}!{anchor}",
                valueInputOption="USER_ENTERED", body={"values": rows},
            ).execute()
            return
    svc.spreadsheets().values().append(
        spreadsheetId=SHEET_ID, range=f"{tab}!{anchor}",
        valueInputOption="USER_ENTERED", body={"values": rows},
    ).execute()


def _ensure_tab(svc, tab: str, rows: int, cols: int) -> int:
    meta = svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == tab:
            return s["properties"]["sheetId"]
    body = {"requests": [{
        "addSheet": {"properties": {"title": tab, "gridProperties": {"rowCount": rows, "columnCount": cols}}}
    }]}
    resp = svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body=body).execute()
    return resp["replies"][0]["addSheet"]["properties"]["sheetId"]


def _delete_rows(svc, gid: int, row_numbers_1_based: list[int]) -> None:
    requests = []
    for rn in sorted(row_numbers_1_based, reverse=True):
        requests.append({"deleteDimension": {
            "range": {"sheetId": gid, "dimension": "ROWS", "startIndex": rn - 1, "endIndex": rn},
        }})
    for off in range(0, len(requests), 100):
        svc.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID, body={"requests": requests[off:off + 100]}
        ).execute()


def _fresh_check(bx: BitrixClient, company_id: str) -> dict:
    """Re-check компанию прямо перед удалением. Если что-то добавилось — skip."""
    g = bx.call("crm.company.get", [("id", company_id)])
    if g.get("error_description") == "Not found":
        return {"ok_to_delete": False, "reason": "already_deleted", "backup": {}}
    company = g.get("result")
    if not company:
        return {"ok_to_delete": False, "reason": f"unexpected response: {g!r}", "backup": {}}

    def _list_all(method: str, filter_key: str) -> list[dict]:
        out: list[dict] = []
        last_id = 0
        while True:
            params = [
                (f"filter[{filter_key}]", company_id),
                ("filter[>ID]", str(last_id)),
                ("order[ID]", "ASC"),
                ("start", "-1"),
                ("select[]", "ID"),
                ("select[]", filter_key),
            ]
            resp = bx.call(method, params)
            batch = resp.get("result", [])
            if not batch:
                return out
            out.extend(batch)
            last_id = int(batch[-1]["ID"])
            if len(batch) < 50:
                return out

    contacts = _list_all("crm.contact.list", "COMPANY_ID")
    deals = _list_all("crm.deal.list", "COMPANY_ID")
    leads = _list_all("crm.lead.list", "COMPANY_ID")

    reqs_resp = bx.call("crm.requisite.list", [
        ("filter[ENTITY_TYPE_ID]", "4"),
        ("filter[ENTITY_ID]", company_id),
        ("select[]", "ID"),
        ("select[]", "RQ_INN"),
        ("select[]", "RQ_OGRN"),
        ("select[]", "RQ_OGRNIP"),
    ])
    requisites = reqs_resp.get("result", [])

    ok = not contacts and not deals and not leads
    reason = "ok" if ok else (
        f"fresh_links_appeared: contacts={len(contacts)} deals={len(deals)} leads={len(leads)}"
    )
    return {
        "ok_to_delete": ok,
        "reason": reason,
        "backup": {
            "company": company,
            "contacts": contacts,
            "deals": deals,
            "leads": leads,
            "requisites": requisites,
            "checked_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        },
    }


def _get(row: list, idx: dict[str, int], name: str) -> str:
    i = idx.get(name)
    if i is None or len(row) <= i:
        return ""
    return str(row[i]).strip()


def _to_int(raw: str) -> int:
    try:
        return int(float(raw or 0))
    except (TypeError, ValueError):
        return 0


def _safe_name(raw: str) -> str:
    out = "".join(ch if ch.isalnum() else "_" for ch in str(raw).lower()).strip("_")
    return out[:60] or "company"


if __name__ == "__main__":
    sys.exit(main())
