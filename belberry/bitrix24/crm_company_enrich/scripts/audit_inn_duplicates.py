#!/usr/bin/env python3
"""Ежедневный аудит дублей компаний по ИНН → запись в Sheet «Дубли компаний».

Логика:
1. Загружает все реквизиты компаний (crm.requisite.list, ENTITY_TYPE_ID=4).
2. Группирует по нормализованному ИНН (10 или 12 цифр).
3. Каждая группа из 2+ компаний — кандидат на разбор.
4. В каждой группе WINNER выбирается по эвристике:
   - больше активных сделок (CLOSED=N)
   - больше всех сделок
   - больше контактов
   - самая поздняя DATE_MODIFY
   - самая ранняя дата создания (меньший ID)
5. Полный перезапис таба «Дубли компаний» (gid=235411137) с новыми данными.

Запускается из cron 3 раза в сутки. Если дублей нет — таб становится пустым
(остаётся только header). Уведомление в Telegram отправляется только если
обнаружены новые группы дублей.

Использование:
  python -m scripts.audit_inn_duplicates [--tg]

Аргументы:
  --tg    — отправить уведомление в Telegram (использует переменные окружения
            LARISA_TG_TOKEN и LARISA_TG_CHAT_ID; если переменные не заданы,
            уведомление не отправляется молча).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Добавим корень проекта в sys.path чтобы импортировать crm_company_enrich
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from crm_company_enrich.bitrix_client import BitrixClient
from crm_company_enrich.config import LOG_PATH, STATE_PATH, SERVICE_ACCOUNT_JSON

# ---- Конфигурация ----
SHEET_ID = "13L0gqwkNzrWacYeI5TzkOxZuRuXn5bBCtfxx-uzHH_4"
TAB_TITLE = "Дубли компаний"
TAB_GID = 235411137
BITRIX_HOST = "https://belberrycrm.bitrix24.ru"
MSK = ZoneInfo("Europe/Moscow")
LINK_FORMAT = {
    "foregroundColor": {"red": 0.07, "green": 0.36, "blue": 0.84},
    "underline": True,
}
BRAND_ENUM_MAP = {"2444": "Belberry", "2442": "Acoola Team"}
HEADERS = [
    "ИНН (ключ группы)", "Тип группы", "Роль", "Компания (Б24)",
    "ИНН компании", "Создана", "Сделок", "Контактов", "Лидов",
    "Бренд (UF)", "Город (UF)", "Сайт (UF)", "Оборот (UF)",
    "Ответственный", "Создал", "company_id", "Статус merge",
]

# UF поля компании
UF_SITE = "UF_CRM_5DEF838D882A2"
UF_CITY = "UF_CRM_1584876724"
UF_REVENUE = "UF_CRM_1737098549301"
UF_BRAND_ENUM = "UF_CRM_684FE59BA3C8C"
UF_BRAND_TEXT = "UF_CRM_1737098476975"


def load_requisites(bx: BitrixClient) -> dict[str, list[str]]:
    """Вернуть mapping ИНН → список company_id (с дубликатами если на одной компании 2 реквизита)."""
    inn_to_companies: dict[str, list[str]] = defaultdict(list)
    start = 0
    while True:
        resp = bx.call("crm.requisite.list", {
            "filter": {"ENTITY_TYPE_ID": 4},
            "select": ["ID", "ENTITY_ID", "RQ_INN"],
            "start": start,
            "order": {"ID": "ASC"},
        })
        items = resp.get("result") or []
        if not items:
            break
        for req in items:
            inn = str(req.get("RQ_INN") or "").strip()
            if inn and inn.isdigit() and len(inn) in (10, 12):
                inn_to_companies[inn].append(str(req.get("ENTITY_ID")))
        total = resp.get("total") or 0
        if start + 50 >= total:
            break
        start += 50
    return dict(inn_to_companies)


def filter_dup_groups(inn_to_companies: dict[str, list[str]]) -> list[dict]:
    """Оставить только группы с 2+ уникальными company_id."""
    out = []
    for inn, cids in inn_to_companies.items():
        uniq = sorted(set(cids), key=lambda x: int(x) if x.isdigit() else 0)
        if len(uniq) >= 2:
            out.append({"inn": inn, "company_ids": uniq})
    return out


def fetch_company_full(bx: BitrixClient, company_ids: list[str]) -> dict:
    """Получить полные данные по компаниям (включая UF, сделки, контакты, лиды)."""
    data: dict[str, dict] = {}
    for cid in company_ids:
        try:
            r = bx.call("crm.company.get", {"id": cid})
            data[cid] = r.get("result") or {}
        except Exception:
            data[cid] = {}

    deals: dict[str, list] = {}
    contacts: dict[str, list] = {}
    leads: dict[str, list] = {}
    for cid in company_ids:
        try:
            deals[cid] = bx.call("crm.deal.list", {
                "filter": {"COMPANY_ID": cid},
                "select": ["ID", "CLOSED"],
                "start": 0,
            }).get("result") or []
        except Exception:
            deals[cid] = []
        try:
            contacts[cid] = bx.call("crm.company.contact.items.get", {"id": cid}).get("result") or []
        except Exception:
            contacts[cid] = []
        try:
            leads[cid] = bx.call("crm.lead.list", {
                "filter": {"COMPANY_ID": cid},
                "select": ["ID"],
                "start": 0,
            }).get("result") or []
        except Exception:
            leads[cid] = []

    user_ids = set()
    for cd in data.values():
        for key in ("ASSIGNED_BY_ID", "CREATED_BY_ID"):
            v = cd.get(key)
            if v:
                user_ids.add(str(v))
    users: dict[str, str] = {}
    for uid in user_ids:
        try:
            u = bx.call("user.get", {"ID": uid}).get("result") or []
            if isinstance(u, list) and u:
                users[uid] = f"{u[0].get('LAST_NAME', '')} {u[0].get('NAME', '')}".strip()
            else:
                users[uid] = uid
        except Exception:
            users[uid] = uid

    return {"data": data, "deals": deals, "contacts": contacts, "leads": leads, "users": users}


def winner_score(cid: str, ctx: dict) -> tuple:
    """Tuple для сортировки. Больше — лучше (WINNER)."""
    deals = ctx["deals"].get(cid, [])
    active = sum(1 for d in deals if d.get("CLOSED") != "Y")
    total_deals = len(deals)
    contacts_cnt = len(ctx["contacts"].get(cid, []))
    modified = ctx["data"].get(cid, {}).get("DATE_MODIFY", "") or ""
    # Старшая компания (меньший ID) — приоритетнее → возьмём отрицательный ID
    id_neg = -1 * (int(cid) if cid.isdigit() else 0)
    return (active, total_deals, contacts_cnt, modified, id_neg)


def build_rows(groups: list[dict], ctx: dict) -> list[list]:
    """Подготовить таблицу для записи в Sheet."""
    rows = []
    for g in groups:
        inn = g["inn"]
        cids = g["company_ids"]
        ordered = sorted(cids, key=lambda c: winner_score(c, ctx), reverse=True)
        winner = ordered[0]
        losers = ordered[1:]
        for role, cid in [("WINNER", winner)] + [("LOSER", l) for l in losers]:
            cd = ctx["data"].get(cid, {})
            deals = ctx["deals"].get(cid, [])
            active_deals = sum(1 for d in deals if d.get("CLOSED") != "Y")
            brand_enum_id = str(cd.get(UF_BRAND_ENUM) or "")
            brand_text = str(cd.get(UF_BRAND_TEXT) or "")
            brand = BRAND_ENUM_MAP.get(brand_enum_id, "") or brand_text
            rows.append([
                inn,
                "ИНН duplicate",
                role,
                cd.get("TITLE", ""),
                inn,
                (cd.get("DATE_CREATE", "") or "")[:10],
                f"{active_deals}/{len(deals)}",
                len(ctx["contacts"].get(cid, [])),
                len(ctx["leads"].get(cid, [])),
                brand,
                cd.get(UF_CITY, ""),
                cd.get(UF_SITE, ""),
                cd.get(UF_REVENUE, ""),
                ctx["users"].get(str(cd.get("ASSIGNED_BY_ID", "")), ""),
                ctx["users"].get(str(cd.get("CREATED_BY_ID", "")), ""),
                cid,
                "к разбору",
            ])
    return rows


def write_sheet(rows: list[list], summary_note: str) -> None:
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_JSON,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

    # Очистка таба + перезапись header + строки
    svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={
        "requests": [{
            "updateCells": {
                "range": {"sheetId": TAB_GID},
                "fields": "userEnteredValue,textFormatRuns,note",
            }
        }]
    }).execute()

    body_values = [HEADERS] + rows
    svc.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=f"'{TAB_TITLE}'!A1",
        valueInputOption="RAW",
        body={"values": body_values},
    ).execute()

    # Гиперссылки + условное форматирование
    requests = []
    for i, r in enumerate(rows, start=2):
        cid = str(r[15])
        title = str(r[3])
        co_url = f"{BITRIX_HOST}/crm/company/details/{cid}/"
        requests.append({
            "updateCells": {
                "range": {"sheetId": TAB_GID, "startRowIndex": i - 1, "endRowIndex": i,
                          "startColumnIndex": 3, "endColumnIndex": 4},
                "rows": [{"values": [{
                    "userEnteredValue": {"stringValue": title or f"#{cid}"},
                    "textFormatRuns": [{"startIndex": 0,
                        "format": {**LINK_FORMAT, "link": {"uri": co_url}}}],
                }]}],
                "fields": "userEnteredValue,textFormatRuns",
            }
        })

    # Подсветка WINNER/LOSER (если уже есть правила — добавятся в начало; дубли не страшны)
    requests.append({"addConditionalFormatRule": {"rule": {
        "ranges": [{"sheetId": TAB_GID, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 17}],
        "booleanRule": {
            "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": '=$C2="WINNER"'}]},
            "format": {"backgroundColor": {"red": 0.85, "green": 0.95, "blue": 0.85}}}},
        "index": 0}})
    requests.append({"addConditionalFormatRule": {"rule": {
        "ranges": [{"sheetId": TAB_GID, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 17}],
        "booleanRule": {
            "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": '=$C2="LOSER"'}]},
            "format": {"backgroundColor": {"red": 1.00, "green": 0.90, "blue": 0.90}}}},
        "index": 0}})

    # Заметка с временем последнего обновления
    requests.append({
        "updateCells": {
            "range": {"sheetId": TAB_GID, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": 1},
            "rows": [{"values": [{"note": summary_note}]}],
            "fields": "note",
        }
    })

    CHUNK = 200
    for i in range(0, len(requests), CHUNK):
        svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID,
            body={"requests": requests[i:i + CHUNK]}).execute()


def send_telegram(text: str) -> None:
    """Опциональное TG-уведомление от «Ларисы Помогатор»."""
    token = os.environ.get("LARISA_TG_TOKEN") or os.environ.get("TG_BOT_TOKEN")
    chat_id = os.environ.get("LARISA_TG_CHAT_ID") or os.environ.get("TG_CHAT_ID")
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": "true",
    }).encode()
    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tg", action="store_true", help="Отправить TG-уведомление если найдены дубли")
    args = ap.parse_args()

    started = datetime.now(MSK)
    print(f"[inn-dup-audit] старт {started.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    bx = BitrixClient(state_path=STATE_PATH, log_path=LOG_PATH)
    inn_map = load_requisites(bx)
    print(f"[inn-dup-audit] реквизитов с валидным ИНН: {sum(len(v) for v in inn_map.values())} | уникальных ИНН: {len(inn_map)}")

    groups = filter_dup_groups(inn_map)
    print(f"[inn-dup-audit] групп дублей (>=2 компании на ИНН): {len(groups)}")

    if not groups:
        # Просто очищаем таб (оставляя header)
        note = f"Аудит {started.strftime('%d.%m.%Y %H:%M МСК')}. Дублей по ИНН не найдено."
        write_sheet([], note)
        print(note)
        return 0

    all_ids = sorted({cid for g in groups for cid in g["company_ids"]}, key=int)
    print(f"[inn-dup-audit] подгрузка данных по {len(all_ids)} компаниям...")
    ctx = fetch_company_full(bx, all_ids)

    rows = build_rows(groups, ctx)
    finished = datetime.now(MSK)
    note = (
        f"Аудит {started.strftime('%d.%m.%Y %H:%M МСК')} — {finished.strftime('%H:%M')}. "
        f"Найдено групп: {len(groups)} | компаний-кандидатов: {len(all_ids)}."
    )
    write_sheet(rows, note)
    print(f"[inn-dup-audit] записано строк: {len(rows)}")

    if args.tg:
        tg_text = (
            f"*Аудит дублей по ИНН*\n"
            f"_{started.strftime('%d.%m.%Y %H:%M МСК')}_\n\n"
            f"Найдено групп: *{len(groups)}*\n"
            f"Компаний-кандидатов: *{len(all_ids)}*\n\n"
            f"[Открыть таблицу](https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid={TAB_GID})"
        )
        send_telegram(tg_text)
        print("[inn-dup-audit] TG-уведомление отправлено")

    return 0


if __name__ == "__main__":
    sys.exit(main())
