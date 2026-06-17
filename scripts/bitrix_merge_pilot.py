#!/usr/bin/env python3
"""
Пилотный merge дублей компаний — DRY-RUN ПО УМОЛЧАНИЮ.

Параметры из обсуждения:
  - сделки: переносим все (открытые + закрытые) с пометкой в COMMENTS
  - контакты: переносим все, дубли разберём отдельно
  - LOSER-карточка: удаляется через crm.company.delete после переноса
  - Пилот: 10 «холодных» групп (0 сделок и 0 контактов у всех карточек)

Запуск:
  python3 bitrix_merge_pilot.py              # DRY-RUN (план в лист "План merge")
  python3 bitrix_merge_pilot.py --execute    # РЕАЛЬНЫЙ merge + лог в "Лог merge"

Перед --execute обязательно проверить лист "План merge" вручную.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

BX_STATE = Path("/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json")
GS_KEY = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json"
SHEET_ID = "1WaCtF2BeBorGXkZa0a53Bi6T_lKHeZZwQPEO8qIzmFU"
ANALYSIS_SHEET = "Анализ дублей"
PLAN_SHEET = "План merge"
LOG_SHEET = "Лог merge"
BACKUP_SHEET_PREFIX = "Backup merge"
PILOT_COUNT = 10


def bx_auth() -> tuple[str, str]:
    s = json.loads(BX_STATE.read_text())["payload"]
    return s["auth[client_endpoint]"].rstrip("/"), s["auth[access_token]"]


def bx_call(method: str, params: dict | None = None, retries: int = 3) -> dict:
    endpoint, token = bx_auth()
    flat: list[tuple[str, str]] = [("auth", token)]
    for k, v in (params or {}).items():
        if isinstance(v, list):
            for item in v:
                flat.append((k, str(item)))
        else:
            flat.append((k, str(v)))
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                f"{endpoint}/{method}",
                data=urllib.parse.urlencode(flat).encode(),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                body = json.loads(r.read().decode())
            if body.get("error") == "QUERY_LIMIT_EXCEEDED":
                time.sleep(2 ** attempt)
                continue
            return body
        except (urllib.error.HTTPError, urllib.error.URLError):
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    return {}


def gs_client():
    creds = Credentials.from_service_account_file(
        GS_KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return build("sheets", "v4", credentials=creds)


def gs_ensure_sheet(svc, title: str) -> None:
    meta = svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    for s in meta.get("sheets", []):
        if s["properties"]["title"] == title:
            svc.spreadsheets().values().clear(
                spreadsheetId=SHEET_ID, range=title,
            ).execute()
            return
    svc.spreadsheets().batchUpdate(
        spreadsheetId=SHEET_ID,
        body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
    ).execute()


def gs_write(svc, sheet: str, rows: list[list]) -> None:
    svc.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=f"{sheet}!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()


def load_analysis(svc) -> list[dict]:
    r = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=f"{ANALYSIS_SHEET}!A1:N10000",
    ).execute()
    vals = r.get("values", [])
    if not vals:
        return []
    headers = vals[0]
    rows = []
    for row in vals[1:]:
        rec = {headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers))}
        rows.append(rec)
    return rows


def select_pilot(rows: list[dict], n: int) -> list[dict]:
    """Группируем по ИНН, берём первые N групп где: все WINNER/LOSER, sum(deals+contacts)=0, нет partial/not_found."""
    by_inn: dict[str, list[dict]] = {}
    for r in rows:
        inn = r.get("ИНН", "").strip()
        if inn:
            by_inn.setdefault(inn, []).append(r)
    selected: list[dict] = []
    for inn, items in by_inn.items():
        if any(it.get("Роль") == "NOT_FOUND" for it in items):
            continue
        if any(it.get("Примечание") for it in items):
            continue
        # "Холодный" пилот: у LOSER-карточек нет сделок и контактов.
        # Winner может иметь активность — её мы не трогаем.
        losers_only = [it for it in items if it.get("Роль") == "LOSER"]
        loser_activity = 0
        for it in losers_only:
            try:
                loser_activity += int(it.get("Сделок всего") or 0)
                loser_activity += int(it.get("Контактов") or 0)
            except (TypeError, ValueError):
                pass
        if loser_activity != 0:
            continue
        if not any(it.get("Роль") == "WINNER" for it in items):
            continue
        selected.append({"inn": inn, "items": items})
        if len(selected) >= n:
            break
    return selected


# ---------- Перенос ----------

def get_deals_for(company_id: str) -> list[dict]:
    """Все сделки (любого статуса) с filter[COMPANY_ID]=company_id."""
    deals: list[dict] = []
    last_id = 0
    while True:
        r = bx_call("crm.deal.list", {
            "filter[COMPANY_ID]": company_id,
            "filter[>ID]": last_id,
            "order[ID]": "ASC",
            "select[]": ["ID", "TITLE", "STAGE_ID", "CATEGORY_ID", "COMMENTS", "CLOSED"],
            "start": -1,
        })
        chunk = r.get("result") or []
        if not chunk:
            break
        deals.extend(chunk)
        last_id = int(chunk[-1]["ID"])
    return deals


def get_contacts_for(company_id: str) -> list[dict]:
    contacts: list[dict] = []
    last_id = 0
    while True:
        r = bx_call("crm.contact.list", {
            "filter[COMPANY_ID]": company_id,
            "filter[>ID]": last_id,
            "order[ID]": "ASC",
            "select[]": ["ID", "NAME", "LAST_NAME"],
            "start": -1,
        })
        chunk = r.get("result") or []
        if not chunk:
            break
        contacts.extend(chunk)
        last_id = int(chunk[-1]["ID"])
    return contacts


def get_loser_requisites(company_id: str) -> list[dict]:
    r = bx_call("crm.requisite.list", {
        "filter[ENTITY_TYPE_ID]": 4,
        "filter[ENTITY_ID]": company_id,
        "select[]": ["ID", "RQ_INN", "RQ_KPP"],
    })
    return r.get("result") or []


def merge_log_entry(action: str, **fields) -> list:
    return [
        datetime.now().isoformat(timespec="seconds"),
        action,
        json.dumps(fields, ensure_ascii=False),
    ]


def plan_or_execute(svc, pilot: list[dict], execute: bool) -> None:
    """Главная логика."""
    mode = "EXECUTE" if execute else "DRY-RUN"
    print(f"\n=== РЕЖИМ: {mode} ===")
    print(f"Групп в пилоте: {len(pilot)}\n")

    plan_rows = [[
        "ИНН", "WINNER id", "LOSER id", "Действие", "Объект", "Объект ID", "Детали",
    ]]
    log_rows = [[
        "Время", "Действие", "Детали (JSON)",
    ]]

    # Бэкап перед execute
    backup_rows: list[list] = [["ИНН", "company_id", "TITLE", "ASSIGNED_BY_ID",
                                "DATE_CREATE", "RAW_JSON"]]

    for group in pilot:
        inn = group["inn"]
        winner = next(it for it in group["items"] if it.get("Роль") == "WINNER")
        losers = [it for it in group["items"] if it.get("Роль") == "LOSER"]
        win_id = winner["company_id"]

        for loser in losers:
            lose_id = loser["company_id"]
            print(f"\n— ИНН {inn}  winner={win_id}  loser={lose_id}")

            # 1) Получить сделки и контакты loser (живая проверка)
            deals = get_deals_for(lose_id)
            contacts = get_contacts_for(lose_id)
            reqs = get_loser_requisites(lose_id)
            print(f"   на LOSER: deals={len(deals)}, contacts={len(contacts)}, "
                  f"requisites={len(reqs)}")

            # Бэкап карточки loser
            full = bx_call("crm.company.get", {"id": lose_id}).get("result") or {}
            backup_rows.append([
                inn, lose_id, full.get("TITLE", ""), full.get("ASSIGNED_BY_ID", ""),
                full.get("DATE_CREATE", ""), json.dumps(full, ensure_ascii=False)[:5000],
            ])

            # 2) Перенос сделок
            for d in deals:
                deal_id = d["ID"]
                old_comments = d.get("COMMENTS") or ""
                note = (
                    f"[Перенесено с дубля company_id={lose_id} "
                    f"({datetime.now().date()})]"
                )
                new_comments = (old_comments + "\n\n" + note).strip()
                plan_rows.append([
                    inn, win_id, lose_id, "MOVE_DEAL", "Deal", deal_id,
                    f"COMPANY_ID {lose_id} → {win_id}, +note",
                ])
                if execute:
                    bx_call("crm.deal.update", {
                        "id": deal_id,
                        "fields[COMPANY_ID]": win_id,
                        "fields[COMMENTS]": new_comments,
                    })
                    log_rows.append(merge_log_entry(
                        "MOVE_DEAL", deal_id=deal_id, from_=lose_id, to=win_id,
                    ))

            # 3) Перенос контактов
            for c in contacts:
                contact_id = c["ID"]
                plan_rows.append([
                    inn, win_id, lose_id, "MOVE_CONTACT", "Contact", contact_id,
                    f"COMPANY_ID {lose_id} → {win_id}",
                ])
                if execute:
                    bx_call("crm.contact.update", {
                        "id": contact_id,
                        "fields[COMPANY_ID]": win_id,
                    })
                    log_rows.append(merge_log_entry(
                        "MOVE_CONTACT", contact_id=contact_id,
                        from_=lose_id, to=win_id,
                    ))

            # 4) Удалить реквизиты loser
            for rq in reqs:
                plan_rows.append([
                    inn, win_id, lose_id, "DELETE_REQUISITE", "Requisite", rq["ID"],
                    f"INN={rq.get('RQ_INN')} KPP={rq.get('RQ_KPP')}",
                ])
                if execute:
                    bx_call("crm.requisite.delete", {"id": rq["ID"]})
                    log_rows.append(merge_log_entry(
                        "DELETE_REQUISITE", req_id=rq["ID"], company=lose_id,
                    ))

            # 5) Удалить саму карточку loser
            plan_rows.append([
                inn, win_id, lose_id, "DELETE_COMPANY", "Company", lose_id,
                f"TITLE={full.get('TITLE', '')}",
            ])
            if execute:
                r = bx_call("crm.company.delete", {"id": lose_id})
                ok = bool(r.get("result"))
                err = r.get("error_description") or r.get("error") or ""
                log_rows.append(merge_log_entry(
                    "DELETE_COMPANY", company_id=lose_id, ok=ok, error=err,
                ))
                if not ok:
                    print(f"   ⚠ DELETE_COMPANY failed: {err}")

    # Запись плана / лога / бэкапа
    gs_ensure_sheet(svc, PLAN_SHEET)
    gs_write(svc, PLAN_SHEET, plan_rows)
    print(f"\nПлан записан в лист «{PLAN_SHEET}» ({len(plan_rows)-1} действий)")

    if execute:
        backup_name = f"{BACKUP_SHEET_PREFIX} {datetime.now().strftime('%Y-%m-%d %H-%M')}"
        gs_ensure_sheet(svc, backup_name)
        gs_write(svc, backup_name, backup_rows)
        print(f"Бэкап LOSER-карточек: лист «{backup_name}» ({len(backup_rows)-1} записей)")
        gs_ensure_sheet(svc, LOG_SHEET)
        gs_write(svc, LOG_SHEET, log_rows)
        print(f"Лог записан в «{LOG_SHEET}» ({len(log_rows)-1} операций)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true",
                    help="Реальный merge (по умолчанию dry-run)")
    ap.add_argument("--n", type=int, default=PILOT_COUNT,
                    help="Сколько групп в пилоте")
    args = ap.parse_args()

    svc = gs_client()
    rows = load_analysis(svc)
    print(f"Прочитано из «{ANALYSIS_SHEET}»: {len(rows)} строк")

    pilot = select_pilot(rows, args.n)
    print(f"Выбрано «холодных» групп: {len(pilot)}")
    for g in pilot:
        winner = next((it for it in g["items"] if it.get("Роль") == "WINNER"), {})
        losers = [it["company_id"] for it in g["items"] if it.get("Роль") == "LOSER"]
        print(f"  ИНН {g['inn']}  winner={winner.get('company_id')}  losers={losers}")

    if not pilot:
        print("Пилот пуст — нечего делать.")
        return

    plan_or_execute(svc, pilot, execute=args.execute)


if __name__ == "__main__":
    main()
