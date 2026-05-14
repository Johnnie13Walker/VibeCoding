"""
dup_sheet_sync.py — синхронизация вкладки "Дубли компаний" с реальным состоянием Bitrix.

Логика:
  1. Полный скан crm.requisite.list (ENTITY_TYPE_ID=4) → группировка по ИНН.
  2. Группы с >=2 компаниями = "живые дубли".
  3. Для каждой компании дублей подтягивается: TITLE, DATE_CREATE, UF (бренд/город/сайт/оборот),
     ASSIGNED_BY_ID, CREATED_BY_ID, кол-во deals/contacts/leads.
  4. WINNER = карточка с наибольшим "data-score" (deals + contacts + leads + UF-fullness),
     остальные = loser.
  5. Перезапись Sheet (gid=235411137) полностью. Колонка "Статус merge" сохраняется для
     company_id, переживших прогон между запусками.

Запуск:
  bash shared/scripts/bitrix-sync-state.sh   # обновить OAuth
  python belberry/bitrix24/dup_sheet_sync.py [--dry-run] [--limit N]

Cron (на VPS):
  15 * * * * cd /opt/vibecoding && /usr/bin/python3 belberry/bitrix24/dup_sheet_sync.py >> /var/log/dup_sheet_sync.log 2>&1
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ────────────────────────────────────────────────────────────────
# Config
# ────────────────────────────────────────────────────────────────
BITRIX_STATE = Path(
    os.environ.get(
        "BITRIX_STATE_PATH",
        "/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json",
    )
)
SA_KEY = os.environ.get(
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json",
)
SHEET_ID = "13L0gqwkNzrWacYeI5TzkOxZuRuXn5bBCtfxx-uzHH_4"
TARGET_GID = 235411137
TARGET_TAB = "Дубли компаний"
PORTAL_BASE = "https://belberrycrm.bitrix24.ru/crm/company/details"

# UF-поля компании belberrycrm (см. project_belberry_company_enrich)
UF_BRAND = "UF_CRM_1737098476975"
UF_CITY = "UF_CRM_1584876724"
UF_SITE = "UF_CRM_5DEF838D882A2"
UF_REVENUE = "UF_CRM_1737098549301"

# Колонки таблицы (17): A..Q
COLUMNS = [
    "ИНН (ключ группы)",  # A
    "Тип группы",  # B
    "Роль",  # C
    "Компания (Б24)",  # D — hyperlink
    "ИНН компании",  # E
    "Создана",  # F
    "Сделок",  # G
    "Контактов",  # H
    "Лидов",  # I
    "Бренд (UF)",  # J
    "Город (UF)",  # K
    "Сайт (UF)",  # L
    "Оборот (UF)",  # M
    "Ответственный",  # N
    "Создал",  # O
    "company_id",  # P
    "Статус merge",  # Q
]


# ────────────────────────────────────────────────────────────────
# Bitrix REST
# ────────────────────────────────────────────────────────────────
def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def b_call(method: str, params, max_tries: int = 6):
    """Однократный вызов Bitrix REST с ретраями на 429/5xx."""
    s = json.loads(BITRIX_STATE.read_text())["payload"]
    endpoint = s["auth[client_endpoint]"].rstrip("/")
    token = s["auth[access_token]"]
    url = f"{endpoint}/{method}"
    data = urllib.parse.urlencode([("auth", token), *params]).encode()
    for attempt in range(max_tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < max_tries - 1:
                time.sleep(min(30, 2 ** attempt))
                continue
            raise
        except Exception:
            if attempt < max_tries - 1:
                time.sleep(min(20, 2 ** attempt))
                continue
            raise


def normalize_inn(s) -> str:
    if not s:
        return ""
    return "".join(ch for ch in str(s) if ch.isdigit())


def stream_requisites():
    """filter[>ID] + order ASC — надёжная пагинация Bitrix REST."""
    last = 0
    while True:
        r = b_call(
            "crm.requisite.list",
            [
                ("filter[ENTITY_TYPE_ID]", "4"),
                ("filter[>ID]", str(last)),
                ("order[ID]", "ASC"),
                ("select[]", "ID"),
                ("select[]", "ENTITY_ID"),
                ("select[]", "RQ_INN"),
                ("start", "-1"),
            ],
        )
        batch = r.get("result", []) or []
        if not batch:
            break
        for x in batch:
            yield x
        last = int(batch[-1]["ID"])
        if len(batch) < 50:
            break


def find_inn_groups():
    """Возвращает {inn: [company_id, ...]} только для групп размером >=2."""
    by_inn = defaultdict(set)
    seen = 0
    for req in stream_requisites():
        seen += 1
        inn = normalize_inn(req.get("RQ_INN"))
        if not inn:
            continue
        by_inn[inn].add(str(req["ENTITY_ID"]))
        if seen % 1000 == 0:
            log(f"  ...streamed {seen} requisites")
    groups = {inn: sorted(cids, key=int) for inn, cids in by_inn.items() if len(cids) >= 2}
    log(f"requisites scanned: {seen}; INN groups (>=2): {len(groups)}; companies in groups: {sum(len(v) for v in groups.values())}")
    return groups


def fetch_company(cid: str) -> dict:
    r = b_call(
        "crm.company.get",
        [
            ("ID", str(cid)),
        ],
    )
    return r.get("result") or {}


def count_relation(method: str, filter_key: str, cid: str) -> int:
    """Считает связанные сущности через response.total (без выгрузки строк)."""
    r = b_call(
        method,
        [
            (f"filter[{filter_key}]", str(cid)),
            ("select[]", "ID"),
        ],
    )
    return int(r.get("total") or 0)


# user.get — кешируем
_user_cache: dict = {}


def user_name(uid) -> str:
    if not uid:
        return ""
    uid = str(uid)
    if uid in _user_cache:
        return _user_cache[uid]
    try:
        r = b_call("user.get", [("ID", uid)])
        u = (r.get("result") or [{}])[0]
        name = " ".join(filter(None, [u.get("NAME"), u.get("LAST_NAME")])).strip() or f"user {uid}"
    except Exception:
        name = f"user {uid}"
    _user_cache[uid] = name
    return name


# ────────────────────────────────────────────────────────────────
# Group/role classification
# ────────────────────────────────────────────────────────────────
def data_score(c: dict) -> tuple:
    """Сортировочный ключ: выше score → WINNER. Tuple: (deals, contacts, leads, uf_fill, -id)."""
    def _filled(v):
        if v is None:
            return False
        if isinstance(v, str):
            return bool(v.strip())
        return bool(v)
    uf_fill = sum(1 for k in (UF_BRAND, UF_CITY, UF_SITE, UF_REVENUE) if _filled(c.get(k)))
    return (c["_deals"], c["_contacts"], c["_leads"], uf_fill, -int(c["ID"]))


def classify_group(companies: list) -> str:
    """'один ИНН + пустые' если все loser имеют 0/0/0/нет-UF, иначе 'одинаковый ИНН'."""
    winner, *losers = companies
    for l in losers:
        rich = (
            l["_deals"] > 0
            or l["_contacts"] > 0
            or l["_leads"] > 0
            or any((l.get(k) or "").strip() for k in (UF_BRAND, UF_CITY, UF_SITE, UF_REVENUE) if isinstance(l.get(k), str))
        )
        if rich:
            return "одинаковый ИНН"
    return "один ИНН + пустые"


# ────────────────────────────────────────────────────────────────
# Sheets API
# ────────────────────────────────────────────────────────────────
def sheets_service():
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_service_account_file(
        SA_KEY,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def read_status_map(svc) -> dict:
    """Карта company_id → текущий 'Статус merge' (колонка Q)."""
    r = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=SHEET_ID, range=f"'{TARGET_TAB}'!P2:Q")
        .execute()
    )
    vals = r.get("values", [])
    out = {}
    for row in vals:
        if not row:
            continue
        cid = (row[0] or "").strip() if len(row) >= 1 else ""
        status = (row[1] or "").strip() if len(row) >= 2 else ""
        if cid and status:
            out[cid] = status
    return out


def cell_string(value: str) -> dict:
    return {"userEnteredValue": {"stringValue": str(value or "")}}


def cell_number(value) -> dict:
    try:
        n = float(value)
    except Exception:
        return cell_string(value)
    return {"userEnteredValue": {"numberValue": n}}


def cell_hyperlink(text: str, uri: str) -> dict:
    """richText-гиперссылка (ru_RU локаль не ломает)."""
    text = str(text or "")
    return {
        "userEnteredValue": {"stringValue": text},
        "textFormatRuns": [
            {
                "startIndex": 0,
                "format": {"link": {"uri": uri}, "foregroundColor": {"red": 0.067, "green": 0.467, "blue": 0.733}, "underline": True},
            }
        ],
    }


def build_row(group_inn, group_type, role, c, status):
    cid = str(c["ID"])
    title = (c.get("TITLE") or "").strip() or f"#{cid}"
    created = (c.get("DATE_CREATE") or "")[:10]
    deals = c["_deals"]
    contacts = c["_contacts"]
    leads = c["_leads"]
    inn_local = (c.get("_inn") or "").strip()
    brand = c.get(UF_BRAND) or ""
    city = c.get(UF_CITY) or ""
    site = c.get(UF_SITE) or ""
    revenue = c.get(UF_REVENUE)
    assigned = user_name(c.get("ASSIGNED_BY_ID"))
    created_by = user_name(c.get("CREATED_BY_ID"))

    values = [
        cell_string(group_inn),  # A
        cell_string(group_type),  # B
        cell_string(role),  # C
        cell_hyperlink(title, f"{PORTAL_BASE}/{cid}/"),  # D
        cell_string(inn_local),  # E
        cell_string(created),  # F
        cell_number(deals),  # G
        cell_number(contacts),  # H
        cell_number(leads),  # I
        cell_string(brand),  # J
        cell_string(city),  # K
        cell_string(site),  # L
        cell_number(revenue) if revenue not in (None, "") else cell_string(""),  # M
        cell_string(assigned),  # N
        cell_string(created_by),  # O
        cell_string(cid),  # P
        cell_string(status),  # Q
    ]
    return {"values": values}


# ────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="ограничить N групп для отладки")
    args = ap.parse_args()

    t0 = time.time()
    log("dup_sheet_sync: start")

    groups = find_inn_groups()
    if args.limit:
        groups = dict(list(groups.items())[: args.limit])
        log(f"limit applied → {len(groups)} groups")

    # Enrich: один проход по всем уникальным company_id
    all_cids = sorted({cid for cids in groups.values() for cid in cids}, key=int)
    log(f"enriching {len(all_cids)} companies...")
    by_cid: dict = {}
    for i, cid in enumerate(all_cids, 1):
        c = fetch_company(cid)
        if not c:
            log(f"  WARN company {cid} not found (deleted?) — skipping")
            continue
        c["_deals"] = count_relation("crm.deal.list", "COMPANY_ID", cid)
        c["_contacts"] = count_relation("crm.contact.list", "COMPANY_ID", cid)
        try:
            c["_leads"] = count_relation("crm.lead.list", "COMPANY_ID", cid)
        except Exception:
            c["_leads"] = 0
        # Реальный ИНН из реквизитов (на случай несовпадения)
        reqs = (
            b_call(
                "crm.requisite.list",
                [
                    ("filter[ENTITY_TYPE_ID]", "4"),
                    ("filter[ENTITY_ID]", cid),
                    ("select[]", "RQ_INN"),
                    ("start", "-1"),
                ],
            ).get("result", [])
            or []
        )
        c["_inn"] = next((r.get("RQ_INN") for r in reqs if (r.get("RQ_INN") or "").strip()), "")
        by_cid[cid] = c
        if i % 10 == 0 or i == len(all_cids):
            log(f"  enriched {i}/{len(all_cids)}")

    # Группа → список companies с сохранением WINNER первым
    rows_out = []
    summary = []
    for inn, cids in sorted(groups.items()):
        comps = [by_cid[c] for c in cids if c in by_cid]
        if len(comps) < 2:
            log(f"  group {inn} skipped: <2 valid companies after enrich")
            continue
        comps.sort(key=data_score, reverse=True)  # WINNER first
        gtype = classify_group(comps)
        winner = comps[0]
        summary.append(
            f"  ИНН {inn} ({gtype}, {len(comps)} компаний) → WINNER #{winner['ID']} {winner.get('TITLE','')[:40]!r}"
        )
        for idx, c in enumerate(comps):
            role = "WINNER" if idx == 0 else "loser"
            rows_out.append((inn, gtype, role, c))

    log(f"prepared {len(rows_out)} rows across {len(groups)} groups")
    for line in summary:
        log(line)

    # Подключаем Sheets
    svc = sheets_service()
    status_map = read_status_map(svc)
    log(f"existing 'Статус merge' annotations: {len(status_map)} rows")

    # Header + data rows
    target_sheet_id = TARGET_GID
    request_rows = [{"values": [cell_string(h) for h in COLUMNS]}]
    for inn, gtype, role, c in rows_out:
        status = status_map.get(str(c["ID"]), "")
        request_rows.append(build_row(inn, gtype, role, c, status))

    if args.dry_run:
        log("DRY-RUN — sheet NOT modified. Sample of first 5 rows:")
        for r in request_rows[:6]:
            preview = []
            for cell in r["values"][:6]:
                v = cell.get("userEnteredValue", {})
                preview.append(v.get("stringValue") or v.get("numberValue") or "")
            print("   ", preview)
        log(f"DONE dry-run in {time.time()-t0:.1f}s")
        return

    # Очистка + запись
    log("clearing existing data range A2:Q...")
    svc.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID, range=f"'{TARGET_TAB}'!A2:Q"
    ).execute()

    log(f"writing {len(request_rows)} rows (incl. header)...")
    svc.spreadsheets().batchUpdate(
        spreadsheetId=SHEET_ID,
        body={
            "requests": [
                {
                    "updateCells": {
                        "rows": request_rows,
                        "fields": "userEnteredValue,textFormatRuns",
                        "start": {"sheetId": target_sheet_id, "rowIndex": 0, "columnIndex": 0},
                    }
                }
            ]
        },
    ).execute()

    log(f"DONE in {time.time()-t0:.1f}s — wrote {len(request_rows)-1} data rows")


if __name__ == "__main__":
    main()
