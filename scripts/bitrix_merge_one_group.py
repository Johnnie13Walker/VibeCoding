#!/usr/bin/env python3
"""
Точечный merge ОДНОЙ группы дублей по ИНН.
Делает: бэкап LOSER → перенос контактов с пометкой → удаление реквизитов LOSER
→ удаление LOSER → проверка результата.

Запуск:
  python3 bitrix_merge_one_group.py 1003001854
"""
from __future__ import annotations
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

BX_STATE = Path("/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json")
GS_KEY = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json"
SHEET_ID = "1WaCtF2BeBorGXkZa0a53Bi6T_lKHeZZwQPEO8qIzmFU"


def auth():
    s = json.loads(BX_STATE.read_text())["payload"]
    return s["auth[client_endpoint]"].rstrip("/"), s["auth[access_token]"]


def bx(method, params=None):
    endpoint, token = auth()
    flat = [("auth", token)]
    for k, v in (params or {}).items():
        if isinstance(v, list):
            for it in v: flat.append((k, str(it)))
        else: flat.append((k, str(v)))
    req = urllib.request.Request(
        f"{endpoint}/{method}",
        data=urllib.parse.urlencode(flat).encode(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


def gs():
    creds = Credentials.from_service_account_file(
        GS_KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return build("sheets", "v4", credentials=creds)


def find_companies_by_inn(inn: str) -> list[str]:
    r = bx("crm.requisite.list", {
        "filter[RQ_INN]": inn,
        "filter[ENTITY_TYPE_ID]": 4,
        "select[]": ["ENTITY_ID"],
    })
    return sorted({str(req["ENTITY_ID"]) for req in (r.get("result") or [])})


def main():
    inn = sys.argv[1] if len(sys.argv) > 1 else None
    if not inn:
        sys.exit("Использование: python3 bitrix_merge_one_group.py <ИНН>")

    print(f"\n{'='*70}\nMERGE ОДНОЙ ГРУППЫ: ИНН {inn}\n{'='*70}")
    cids = find_companies_by_inn(inn)
    print(f"\nКомпаний с этим ИНН: {len(cids)} → {cids}")
    if len(cids) < 2:
        print("Дублей нет — нечего объединять.")
        return

    # Метрики для каждой
    print("\nМетрики компаний:")
    metrics = {}
    for cid in cids:
        c = bx("crm.company.get", {"id": cid}).get("result") or {}
        d = bx("crm.deal.list", {"filter[COMPANY_ID]": cid, "select[]": "ID", "start": -1}).get("result") or []
        ct = bx("crm.contact.list", {"filter[COMPANY_ID]": cid, "select[]": "ID", "start": -1}).get("result") or []
        metrics[cid] = {"title": c.get("TITLE", ""), "date": (c.get("DATE_CREATE","") or "")[:10],
                         "modify": (c.get("DATE_MODIFY","") or "")[:10], "deals": len(d), "contacts": len(ct)}
        print(f"  id={cid:>6}  «{c.get('TITLE',''):30}»  created={metrics[cid]['date']}  modify={metrics[cid]['modify']}  deals={len(d)}  contacts={len(ct)}")

    # Эвристика выбора winner: max(deals) → max(contacts) → старшая по дате
    winner = sorted(
        cids,
        key=lambda c: (-metrics[c]["deals"], -metrics[c]["contacts"],
                       metrics[c]["date"] or ""),
    )[0]
    losers = [c for c in cids if c != winner]
    print(f"\n→ WINNER: {winner}")
    print(f"→ LOSERS: {losers}")

    log = []
    backup = []

    for lose_id in losers:
        print(f"\n--- LOSER {lose_id} ---")
        # 0. Бэкап
        full = bx("crm.company.get", {"id": lose_id}).get("result") or {}
        backup.append({
            "inn": inn, "company_id": lose_id, "title": full.get("TITLE"),
            "raw": json.dumps(full, ensure_ascii=False),
            "ts": datetime.now().isoformat(timespec="seconds"),
        })

        # 1. Перенос контактов
        contacts = bx("crm.contact.list", {
            "filter[COMPANY_ID]": lose_id,
            "select[]": ["ID", "NAME", "LAST_NAME"],
            "start": -1,
        }).get("result") or []
        for c in contacts:
            cid = c["ID"]
            name = f"{c.get('LAST_NAME','')} {c.get('NAME','')}".strip()
            r = bx("crm.contact.update", {
                "id": cid,
                "fields[COMPANY_ID]": winner,
            })
            ok = bool(r.get("result"))
            print(f"  MOVE_CONTACT {cid} ({name}) → company {winner}: {'OK' if ok else r.get('error_description')}")
            log.append({"op": "MOVE_CONTACT", "contact_id": cid, "from": lose_id, "to": winner, "ok": ok})

        # 2. Удалить реквизиты LOSER
        reqs = bx("crm.requisite.list", {
            "filter[ENTITY_TYPE_ID]": 4,
            "filter[ENTITY_ID]": lose_id,
            "select[]": ["ID", "RQ_INN"],
        }).get("result") or []
        for rq in reqs:
            rqid = rq["ID"]
            r = bx("crm.requisite.delete", {"id": rqid})
            ok = bool(r.get("result"))
            print(f"  DELETE_REQUISITE {rqid} (INN={rq.get('RQ_INN')}): {'OK' if ok else r.get('error_description')}")
            log.append({"op": "DELETE_REQUISITE", "req_id": rqid, "company": lose_id, "ok": ok})

        # 3. Удалить компанию
        r = bx("crm.company.delete", {"id": lose_id})
        ok = bool(r.get("result"))
        print(f"  DELETE_COMPANY {lose_id}: {'OK' if ok else r.get('error_description')}")
        log.append({"op": "DELETE_COMPANY", "company_id": lose_id, "ok": ok})

    # Финальная проверка
    print(f"\n{'='*70}\nПРОВЕРКА ИТОГА\n{'='*70}")
    final = find_companies_by_inn(inn)
    print(f"Компаний с ИНН {inn} после merge: {len(final)} → {final}")
    if len(final) == 1 and final[0] == winner:
        print("✓ Объединение прошло корректно — осталась одна карточка WINNER")
    else:
        print("⚠ Что-то не сходится — проверь вручную")

    # Свежие метрики winner
    print(f"\nWINNER ({winner}) после merge:")
    c = bx("crm.company.get", {"id": winner}).get("result") or {}
    d = bx("crm.deal.list", {"filter[COMPANY_ID]": winner, "select[]": "ID", "start": -1}).get("result") or []
    ct = bx("crm.contact.list", {"filter[COMPANY_ID]": winner, "select[]": "ID", "start": -1}).get("result") or []
    print(f"  title:    {c.get('TITLE')}")
    print(f"  deals:    {len(d)}  (было {metrics[winner]['deals']})")
    print(f"  contacts: {len(ct)} (было {metrics[winner]['contacts']})")

    # Запись бэкапа и лога в Sheets
    svc = gs()
    backup_sheet = f"Backup merge {datetime.now().strftime('%Y-%m-%d %H-%M')}"
    log_sheet = "Лог merge"
    # ensure sheets
    meta = svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    existing = {s["properties"]["title"] for s in meta.get("sheets", [])}
    for sh in [backup_sheet, log_sheet]:
        if sh not in existing:
            svc.spreadsheets().batchUpdate(
                spreadsheetId=SHEET_ID,
                body={"requests": [{"addSheet": {"properties": {"title": sh}}}]},
            ).execute()
    # backup
    bk_rows = [["ts", "ИНН", "company_id", "title", "raw_json"]]
    for b in backup:
        bk_rows.append([b["ts"], b["inn"], b["company_id"], b["title"], b["raw"][:5000]])
    svc.spreadsheets().values().append(
        spreadsheetId=SHEET_ID, range=f"{backup_sheet}!A1",
        valueInputOption="RAW", body={"values": bk_rows},
    ).execute()
    # log append
    log_rows = []
    for e in log:
        log_rows.append([
            datetime.now().isoformat(timespec="seconds"),
            e["op"],
            json.dumps(e, ensure_ascii=False),
        ])
    if log_rows:
        # если лист пустой — добавим шапку
        existing_log = svc.spreadsheets().values().get(
            spreadsheetId=SHEET_ID, range=f"{log_sheet}!A1:C1",
        ).execute().get("values", [])
        if not existing_log:
            log_rows = [["Время", "Действие", "Детали (JSON)"]] + log_rows
        svc.spreadsheets().values().append(
            spreadsheetId=SHEET_ID, range=f"{log_sheet}!A1",
            valueInputOption="RAW", body={"values": log_rows},
        ).execute()
    print(f"\nБэкап → лист «{backup_sheet}»")
    print(f"Лог → лист «{log_sheet}»")


if __name__ == "__main__":
    main()
