#!/usr/bin/env python3
"""
Сбор отчёта по дублям компаний и запись в Google Sheets.

Источник: лист "Дубли компаний ИНН" из таблицы
1WaCtF2BeBorGXkZa0a53Bi6T_lKHeZZwQPEO8qIzmFU
Цель:     создать/обновить лист "Анализ дублей" с разметкой WINNER/LOSER
          и метриками по каждой карточке.

Эвристика выбора winner (предварительная):
  1. Максимум активных сделок
  2. При равенстве — максимум всех сделок
  3. При равенстве — максимум контактов
  4. При равенстве — самая поздняя дата изменения
  5. При равенстве — самая ранняя дата создания (старшая)

Никаких write-вызовов в Bitrix. Только read.
В Sheets — добавление нового листа и заполнение.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from datetime import datetime

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ---------- Конфиг ----------
BX_STATE = Path("/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json")
GS_KEY = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json"
SHEET_ID = "1WaCtF2BeBorGXkZa0a53Bi6T_lKHeZZwQPEO8qIzmFU"
SRC_SHEET = "Дубли компаний ИНН"
DST_SHEET = "Анализ дублей"


# ---------- Bitrix ----------

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
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    return {}


def bx_batch(commands: dict[str, tuple[str, dict]]) -> dict:
    """commands = {name: (method, params)}. Максимум 50."""
    params = {}
    for name, (method, mparams) in commands.items():
        cmd = method
        if mparams:
            qs = urllib.parse.urlencode(
                [(k, str(it)) for k, v in mparams.items()
                 for it in (v if isinstance(v, list) else [v])]
            )
            cmd = f"{method}?{qs}"
        params[f"cmd[{name}]"] = cmd
    params["halt"] = "0"
    r = bx_call("batch", params)
    return (r.get("result") or {}).get("result") or {}


# ---------- Sheets ----------

def gs_client():
    creds = Credentials.from_service_account_file(
        GS_KEY,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return build("sheets", "v4", credentials=creds)


def gs_ensure_sheet(svc, title: str) -> int:
    meta = svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    for s in meta.get("sheets", []):
        if s["properties"]["title"] == title:
            sid = s["properties"]["sheetId"]
            # очистим
            svc.spreadsheets().values().clear(
                spreadsheetId=SHEET_ID, range=title,
            ).execute()
            return sid
    res = svc.spreadsheets().batchUpdate(
        spreadsheetId=SHEET_ID,
        body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
    ).execute()
    return res["replies"][0]["addSheet"]["properties"]["sheetId"]


# ---------- Логика ----------

def load_groups(svc) -> dict[str, list[dict]]:
    """ИНН -> [{title, responsible, date_create}, ...]"""
    r = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=f"{SRC_SHEET}!A2:E1000",
    ).execute()
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in r.get("values", []):
        if len(row) < 4:
            continue
        inn = row[0].strip()
        if not inn:
            continue
        groups[inn].append(
            {
                "title": row[1],
                "responsible": row[2] if len(row) > 2 else "",
                "date_create": row[3] if len(row) > 3 else "",
            }
        )
    return groups


def find_company_ids_by_inn(inns: list[str]) -> dict[str, list[str]]:
    """ИНН -> [company_id, ...]. Пакетно через batch."""
    out: dict[str, list[str]] = {}
    # 50 ИНН за один batch
    for i in range(0, len(inns), 50):
        chunk = inns[i:i + 50]
        cmds = {
            f"q_{inn}": (
                "crm.requisite.list",
                {
                    "filter[RQ_INN]": inn,
                    "filter[ENTITY_TYPE_ID]": 4,
                    "select[]": ["ENTITY_ID"],
                },
            )
            for inn in chunk
        }
        res = bx_batch(cmds)
        for inn in chunk:
            data = res.get(f"q_{inn}") or []
            cids = sorted({str(d["ENTITY_ID"]) for d in data})
            out[inn] = cids
        time.sleep(0.5)
    return out


def fetch_company_metrics(company_ids: list[str]) -> dict[str, dict]:
    """company_id -> {title, date_create, date_modify, assigned, deals_total, deals_open, contacts}."""
    out: dict[str, dict] = {}
    for i in range(0, len(company_ids), 12):  # 4 команды на компанию -> 12*4=48
        chunk = company_ids[i:i + 12]
        cmds = {}
        for cid in chunk:
            cmds[f"c_{cid}"] = ("crm.company.get", {"id": cid})
            cmds[f"dt_{cid}"] = (
                "crm.deal.list",
                {"filter[COMPANY_ID]": cid, "select[]": ["ID"], "start": -1},
            )
            cmds[f"do_{cid}"] = (
                "crm.deal.list",
                {
                    "filter[COMPANY_ID]": cid,
                    "filter[CLOSED]": "N",
                    "select[]": ["ID"],
                    "start": -1,
                },
            )
            cmds[f"ct_{cid}"] = (
                "crm.contact.list",
                {"filter[COMPANY_ID]": cid, "select[]": ["ID"], "start": -1},
            )
        res = bx_batch(cmds)
        for cid in chunk:
            c = res.get(f"c_{cid}") or {}
            dt = res.get(f"dt_{cid}")
            do = res.get(f"do_{cid}")
            ct = res.get(f"ct_{cid}")
            # total приходит как поле, не отдельным значением — в batch его нет.
            # Используем длину массива result.
            deals_total = len(dt) if isinstance(dt, list) else 0
            deals_open = len(do) if isinstance(do, list) else 0
            contacts = len(ct) if isinstance(ct, list) else 0
            out[cid] = {
                "title": c.get("TITLE") or "",
                "date_create": (c.get("DATE_CREATE") or "")[:10],
                "date_modify": (c.get("DATE_MODIFY") or "")[:10],
                "assigned": c.get("ASSIGNED_BY_ID") or "",
                "deals_total": deals_total,
                "deals_open": deals_open,
                "contacts": contacts,
            }
        time.sleep(0.5)
    return out


def fetch_users(user_ids: set[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    ids = [u for u in user_ids if u]
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        cmds = {f"u_{u}": ("user.get", {"ID": u}) for u in chunk}
        res = bx_batch(cmds)
        for u in chunk:
            arr = res.get(f"u_{u}") or []
            if arr:
                p = arr[0]
                name = f"{p.get('NAME','')} {p.get('LAST_NAME','')}".strip()
                out[u] = name or u
        time.sleep(0.3)
    return out


def pick_winner(rows: list[dict]) -> str:
    """rows: [{company_id, metrics...}]. Возвращает company_id победителя."""
    def sort_key(r):
        # Меньше = лучше для sorted
        return (
            -r["deals_open"],
            -r["deals_total"],
            -r["contacts"],
            # date_modify: позже = лучше → инвертируем строку через "негатив" по сортировке
            "" if not r["date_modify"] else r["date_modify"],
            r["date_create"] or "",
        )
    # Сортируем: max deals_open/total/contacts → min "потом" дата_изменения (то есть max date_modify)
    # Двухэтапная сортировка для корректной обработки строковых дат:
    candidates = sorted(rows, key=lambda r: r.get("date_modify") or "", reverse=True)
    candidates = sorted(
        candidates,
        key=lambda r: (
            -r["deals_open"],
            -r["deals_total"],
            -r["contacts"],
        ),
    )
    return candidates[0]["company_id"]


# ---------- Main ----------

HEADER = [
    "ИНН",
    "Название (из источника)",
    "Размер группы",
    "Роль",
    "company_id",
    "Title в Bitrix",
    "Дата создания",
    "Дата изменения",
    "Ответственный",
    "Сделок всего",
    "Сделок открытых",
    "Контактов",
    "Победитель (рекомендация)",
    "Примечание",
]


def main():
    svc = gs_client()
    print("Читаю исходный лист…")
    groups = load_groups(svc)
    print(f"  групп ИНН: {len(groups)}")
    inns = sorted(groups.keys())

    print("Ищу company_id по ИНН (batch)…")
    inn_to_cids = find_company_ids_by_inn(inns)
    all_cids = sorted({cid for cids in inn_to_cids.values() for cid in cids})
    print(f"  уникальных company_id: {len(all_cids)}")

    print("Получаю метрики компаний (batch)…")
    metrics = fetch_company_metrics(all_cids)

    print("Резолвлю имена ответственных…")
    user_ids = {m.get("assigned") for m in metrics.values()}
    user_names = fetch_users(user_ids)

    print("Собираю отчёт…")
    rows_out = [HEADER]
    sheet_inns_set = set(inns)
    summary = {
        "groups_total": len(groups),
        "groups_resolved": 0,
        "groups_partially": 0,
        "groups_missing": 0,
        "extra_cards_found": 0,
    }
    for inn in inns:
        cids = inn_to_cids.get(inn, [])
        source_count = len(groups[inn])
        src_title = groups[inn][0]["title"]
        if not cids:
            summary["groups_missing"] += 1
            rows_out.append([
                inn, src_title, source_count, "NOT_FOUND",
                "", "", "", "", "", "", "", "", "", "не найдено в Bitrix по ИНН",
            ])
            continue
        # построим рядки
        group_rows = []
        for cid in cids:
            m = metrics.get(cid, {})
            group_rows.append({
                "company_id": cid,
                "title": m.get("title", ""),
                "date_create": m.get("date_create", ""),
                "date_modify": m.get("date_modify", ""),
                "assigned": user_names.get(m.get("assigned", ""), m.get("assigned", "")),
                "deals_total": m.get("deals_total", 0),
                "deals_open": m.get("deals_open", 0),
                "contacts": m.get("contacts", 0),
            })
        winner = pick_winner(group_rows)
        if len(cids) == source_count:
            summary["groups_resolved"] += 1
        else:
            summary["groups_partially"] += 1
            summary["extra_cards_found"] += abs(len(cids) - source_count)
        for r in group_rows:
            role = "WINNER" if r["company_id"] == winner else "LOSER"
            note = ""
            if len(cids) != source_count:
                note = f"в источнике {source_count}, в Bitrix {len(cids)}"
            rows_out.append([
                inn, src_title, len(cids), role,
                r["company_id"], r["title"], r["date_create"], r["date_modify"],
                r["assigned"], r["deals_total"], r["deals_open"], r["contacts"],
                winner if role == "WINNER" else "",
                note,
            ])

    # Запись в Sheets
    print(f"Пишу в Sheets лист «{DST_SHEET}» ({len(rows_out)} строк)…")
    gs_ensure_sheet(svc, DST_SHEET)
    svc.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=f"{DST_SHEET}!A1",
        valueInputOption="RAW",
        body={"values": rows_out},
    ).execute()

    # Сводка
    print("\n=== СВОДКА ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    # Активные дубли — у кого есть сделки/контакты
    active_groups = 0
    cold_groups = 0
    for inn in inns:
        cids = inn_to_cids.get(inn, [])
        total_deals = sum(metrics.get(c, {}).get("deals_total", 0) for c in cids)
        total_contacts = sum(metrics.get(c, {}).get("contacts", 0) for c in cids)
        if total_deals > 0 or total_contacts > 0:
            active_groups += 1
        else:
            cold_groups += 1
    print(f"  групп с активностью (есть сделки/контакты): {active_groups}")
    print(f"  «холодные» группы (без сделок и контактов): {cold_groups}")


if __name__ == "__main__":
    main()
