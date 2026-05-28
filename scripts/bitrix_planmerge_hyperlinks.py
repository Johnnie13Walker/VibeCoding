#!/usr/bin/env python3
"""
В листе "План merge" заменяет ID-колонки на гиперссылки по названию:
  B (WINNER id)  → название компании → /crm/company/details/{id}/
  C (LOSER id)   → название компании → /crm/company/details/{id}/
  F (Объект ID)  → название по типу из E (Company/Contact/Requisite)
"""
from __future__ import annotations
import json
import urllib.parse
import urllib.request
import time
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

BX_STATE = Path("/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json")
GS_KEY = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json"
SHEET_ID = "1WaCtF2BeBorGXkZa0a53Bi6T_lKHeZZwQPEO8qIzmFU"
PLAN_SHEET = "План merge"
PORTAL = "https://belberrycrm.bitrix24.ru"


def bx_auth():
    s = json.loads(BX_STATE.read_text())["payload"]
    return s["auth[client_endpoint]"].rstrip("/"), s["auth[access_token]"]


def bx_batch(commands: dict[str, tuple[str, dict]]) -> dict:
    """commands = {name: (method, params)}. Max 50."""
    endpoint, token = bx_auth()
    params = {"auth": token, "halt": "0"}
    for name, (method, mparams) in commands.items():
        qs = urllib.parse.urlencode(
            [(k, str(it)) for k, v in (mparams or {}).items()
             for it in (v if isinstance(v, list) else [v])]
        )
        params[f"cmd[{name}]"] = f"{method}?{qs}" if qs else method
    flat = []
    for k, v in params.items():
        flat.append((k, v))
    req = urllib.request.Request(
        f"{endpoint}/batch",
        data=urllib.parse.urlencode(flat).encode(),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.loads(r.read().decode())
    return (body.get("result") or {}).get("result") or {}


def fetch_titles(company_ids: set[str], contact_ids: set[str]) -> dict:
    """Возвращает {company_id → title, contact_id → fullname}."""
    out = {"company": {}, "contact": {}}
    cids = sorted(company_ids - {""})
    for i in range(0, len(cids), 40):
        chunk = cids[i:i+40]
        cmds = {f"c_{c}": ("crm.company.get", {"id": c}) for c in chunk}
        res = bx_batch(cmds)
        for c in chunk:
            r = res.get(f"c_{c}") or {}
            title = (r.get("TITLE") if isinstance(r, dict) else None)
            if not title and isinstance(r, dict) and r.get("result"):
                title = r["result"].get("TITLE")
            out["company"][c] = title or f"company {c}"
        time.sleep(0.3)
    ctids = sorted(contact_ids - {""})
    for i in range(0, len(ctids), 40):
        chunk = ctids[i:i+40]
        cmds = {f"ct_{c}": ("crm.contact.get", {"id": c}) for c in chunk}
        res = bx_batch(cmds)
        for c in chunk:
            r = res.get(f"ct_{c}") or {}
            if isinstance(r, dict):
                name = " ".join(
                    str(r.get(k) or "") for k in ("LAST_NAME", "NAME", "SECOND_NAME")
                ).strip() or r.get("TITLE") or f"contact {c}"
            else:
                name = f"contact {c}"
            out["contact"][c] = name
        time.sleep(0.3)
    return out


def gs():
    creds = Credentials.from_service_account_file(
        GS_KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return build("sheets", "v4", credentials=creds)


def main():
    svc = gs()
    r = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=f"{PLAN_SHEET}!A1:Z10000",
    ).execute()
    rows = r.get("values", [])
    if not rows:
        print("План пуст")
        return
    headers = rows[0]
    print(f"Прочитано: {len(rows)} строк, заголовки: {headers}")

    # B=WINNER id (1), C=LOSER id (2), E=Объект (4), F=Объект ID (5)
    iWIN, iLOSE, iOBJ, iOID = 1, 2, 4, 5

    company_ids: set[str] = set()
    contact_ids: set[str] = set()
    for row in rows[1:]:
        padded = list(row) + [""] * (len(headers) - len(row))
        company_ids.add(str(padded[iWIN]))
        company_ids.add(str(padded[iLOSE]))
        obj_type = padded[iOBJ]
        obj_id = str(padded[iOID])
        if obj_type == "Company":
            company_ids.add(obj_id)
        elif obj_type == "Contact":
            contact_ids.add(obj_id)
        # Requisite — отдельной страницы нет

    print(f"Уникальных компаний для запроса: {len(company_ids)}")
    print(f"Уникальных контактов для запроса: {len(contact_ids)}")
    titles = fetch_titles(company_ids, contact_ids)

    def hlink(url, text):
        safe = (text or "").replace('"', '""')
        return f'=HYPERLINK("{url}";"{safe}")'

    # Перестраиваем
    new_rows = [headers]
    for row in rows[1:]:
        padded = list(row) + [""] * (len(headers) - len(row))
        win_id = str(padded[iWIN])
        lose_id = str(padded[iLOSE])
        win_title = titles["company"].get(win_id, win_id)
        lose_title = titles["company"].get(lose_id, lose_id)
        padded[iWIN] = hlink(
            f"{PORTAL}/crm/company/details/{win_id}/", win_title,
        ) if win_id else padded[iWIN]
        padded[iLOSE] = hlink(
            f"{PORTAL}/crm/company/details/{lose_id}/", lose_title,
        ) if lose_id else padded[iLOSE]
        obj_type = padded[iOBJ]
        obj_id = str(padded[iOID])
        if obj_type == "Company" and obj_id:
            title = titles["company"].get(obj_id, obj_id)
            padded[iOID] = hlink(f"{PORTAL}/crm/company/details/{obj_id}/", title)
        elif obj_type == "Contact" and obj_id:
            name = titles["contact"].get(obj_id, obj_id)
            padded[iOID] = hlink(f"{PORTAL}/crm/contact/details/{obj_id}/", name)
        elif obj_type == "Requisite":
            # Реквизит не имеет своей страницы — оставляем ID + (Реквизит)
            padded[iOID] = f"Реквизит {obj_id}"
        new_rows.append(padded)

    svc.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID, range=PLAN_SHEET,
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=f"{PLAN_SHEET}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": new_rows},
    ).execute()
    print(f"✓ Записано {len(new_rows)} строк с гиперссылками")


if __name__ == "__main__":
    main()
