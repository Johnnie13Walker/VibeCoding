#!/usr/bin/env python3
"""
Подготовить план на СЛЕДУЮЩУЮ пачку безопасных групп (20 штук).
Исключает уже обработанные в пилоте (читаем "Лог merge" — какие LOSER удалены).
Записывает план в лист "План merge" (предварительно очищая его).

Никакого write в Bitrix — только read + запись в Sheets.
"""
from __future__ import annotations
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

BX_STATE = Path("/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json")
GS_KEY = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json"
SHEET_ID = "1WaCtF2BeBorGXkZa0a53Bi6T_lKHeZZwQPEO8qIzmFU"
ANALYSIS_SHEET = "Анализ дублей"
PLAN_SHEET = "План merge"
LOG_SHEET = "Лог merge"
BATCH_SIZE = 20


def bx_auth():
    s = json.loads(BX_STATE.read_text())["payload"]
    return s["auth[client_endpoint]"].rstrip("/"), s["auth[access_token]"]


def bx_call(method, params=None):
    endpoint, token = bx_auth()
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


def read_sheet(svc, name):
    r = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=f"{name}!A1:Z10000",
    ).execute()
    return r.get("values", [])


def main():
    svc = gs()

    # 1. Известный список удалённых в пилоте (fallback если "Лог merge" утерян)
    PILOT_DELETED_LOSERS = {"6528", "23468", "17274", "17286", "20278",
                             "17388", "1964", "8338", "4952"}
    done_loser_ids: set[str] = set(PILOT_DELETED_LOSERS)
    # Попытка прочитать "Лог merge" если есть
    try:
        log_rows = read_sheet(svc, LOG_SHEET)
        for row in log_rows[1:]:
            if len(row) < 3: continue
            if row[1] == "DELETE_COMPANY":
                try:
                    details = json.loads(row[2])
                    if details.get("ok"):
                        done_loser_ids.add(str(details.get("company_id")))
                except Exception: pass
    except Exception:
        print(f"  («Лог merge» отсутствует, использую hardcoded список пилота)")
    print(f"Уже удалено LOSER в Bitrix: {len(done_loser_ids)} → {sorted(done_loser_ids)}")

    # 2. Читаем "Анализ дублей", группируем по ИНН
    rows = read_sheet(svc, ANALYSIS_SHEET)
    headers = rows[0]

    def col(name): return headers.index(name)

    idx = {h: col(h) for h in [
        "ИНН", "Роль", "company_id", "Title в Bitrix",
        "Сделок всего", "Сделок открытых", "Контактов", "Примечание",
    ]}

    groups: dict[str, list[dict]] = {}
    n_cols = len(headers)
    for row in rows[1:]:
        # Sheets обрезает trailing empty — добиваем до полной длины
        padded = list(row) + [""] * (n_cols - len(row))
        inn = str(padded[idx["ИНН"]]).strip()
        if not inn: continue
        groups.setdefault(inn, []).append({
            "role": padded[idx["Роль"]],
            "cid": str(padded[idx["company_id"]]),
            "title": padded[idx["Title в Bitrix"]],
            "deals_total": str(padded[idx["Сделок всего"]] or "0"),
            "deals_open": str(padded[idx["Сделок открытых"]] or "0"),
            "contacts": str(padded[idx["Контактов"]] or "0"),
            "note": padded[idx["Примечание"]],
        })

    # 3. Отбираем мягко-холодные группы: у каждого LOSER 0 сделок и ≤1 контакта.
    #    Контакты переедут на winner.
    selected = []
    for inn, items in groups.items():
        if any(it["role"] == "NOT_FOUND" for it in items): continue
        if any(it["note"] for it in items): continue
        losers = [it for it in items if it["role"] == "LOSER"]
        if not losers: continue
        if any(it["cid"] in done_loser_ids for it in losers): continue
        ok = True
        for l in losers:
            try:
                if int(l["deals_total"]) != 0:
                    ok = False; break
                if int(l["contacts"]) > 1:
                    ok = False; break
            except (TypeError, ValueError):
                ok = False; break
        if not ok: continue
        selected.append({"inn": inn, "items": items})
        if len(selected) >= BATCH_SIZE: break

    print(f"\nВыбрано следующих холодных групп: {len(selected)}")
    for g in selected:
        winner = next(it for it in g["items"] if it["role"] == "WINNER")
        losers = [it["cid"] for it in g["items"] if it["role"] == "LOSER"]
        print(f"  ИНН {g['inn']:14} winner={winner['cid']:>6}  losers={losers}")

    # 4. Для каждой пары — живая проверка Bitrix: реально 0 сделок/контактов?
    print(f"\nЖивая проверка LOSER в Bitrix...")
    plan_rows = [[
        "ИНН", "WINNER id", "LOSER id", "Действие", "Объект", "Объект ID", "Детали",
    ]]
    for g in selected:
        inn = g["inn"]
        winner = next(it for it in g["items"] if it["role"] == "WINNER")
        for loser in [it for it in g["items"] if it["role"] == "LOSER"]:
            lose_id = loser["cid"]
            # подтверждаем, что LOSER ещё жива и пустая
            c = bx_call("crm.company.get", {"id": lose_id})
            if c.get("error_description") == "Not found":
                plan_rows.append([
                    inn, winner["cid"], lose_id, "SKIP", "Company", lose_id,
                    "карточка уже не существует (NOT_FOUND)",
                ])
                continue
            # быстрый счёт сделок/контактов
            dt = bx_call("crm.deal.list", {
                "filter[COMPANY_ID]": lose_id, "select[]": "ID", "start": -1,
            }).get("result") or []
            ct = bx_call("crm.contact.list", {
                "filter[COMPANY_ID]": lose_id, "select[]": "ID", "start": -1,
            }).get("result") or []
            rq = bx_call("crm.requisite.list", {
                "filter[ENTITY_TYPE_ID]": 4,
                "filter[ENTITY_ID]": lose_id,
                "select[]": ["ID", "RQ_INN"],
            }).get("result") or []

            if len(dt) > 0:
                plan_rows.append([
                    inn, winner["cid"], lose_id, "SKIP", "Company", lose_id,
                    f"NOT eligible: deals={len(dt)} — переехало в группу с активностью",
                ])
                continue
            if len(ct) > 1:
                plan_rows.append([
                    inn, winner["cid"], lose_id, "SKIP", "Company", lose_id,
                    f"NOT eligible: contacts={len(ct)} — слишком много контактов для batch 2",
                ])
                continue

            # план: перенести контакт(ы) → удалить реквизит → удалить компанию
            for contact in ct:
                plan_rows.append([
                    inn, winner["cid"], lose_id, "MOVE_CONTACT", "Contact",
                    contact["ID"],
                    f"COMPANY_ID {lose_id} → {winner['cid']}",
                ])
            for r in rq:
                plan_rows.append([
                    inn, winner["cid"], lose_id, "DELETE_REQUISITE", "Requisite",
                    r["ID"], f"INN={r.get('RQ_INN')}",
                ])
            plan_rows.append([
                inn, winner["cid"], lose_id, "DELETE_COMPANY", "Company", lose_id,
                f"TITLE={c.get('result', {}).get('TITLE', '')[:40]}",
            ])

    # 5. Очистка + запись в "План merge"
    svc.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID, range=PLAN_SHEET,
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=f"{PLAN_SHEET}!A1",
        valueInputOption="RAW",
        body={"values": plan_rows},
    ).execute()
    print(f"\n✓ План записан в «{PLAN_SHEET}» ({len(plan_rows)-1} действий)")


if __name__ == "__main__":
    main()
