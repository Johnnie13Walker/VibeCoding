#!/usr/bin/env python3
"""
Read-only выгрузка для анализа воронки продаж Belberry.
Дампит JSON в /tmp/funnel_analysis/.
Никаких write-вызовов.
"""
from __future__ import annotations
import json, os, sys, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

STATE_PATH = Path(os.environ.get(
    "BITRIX_APP_STATE_DIR",
    "/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state",
)) / "install.latest.json"

OUT = Path("/tmp/funnel_analysis")
OUT.mkdir(exist_ok=True)


def load_auth():
    s = json.loads(STATE_PATH.read_text())["payload"]
    return s["auth[client_endpoint]"].rstrip("/"), s["auth[access_token]"]


def call(method, params=None):
    endpoint, token = load_auth()
    url = f"{endpoint}/{method}"
    flat = [("auth", token)]
    for k, v in (params or {}).items():
        if isinstance(v, list):
            for item in v:
                flat.append((k, str(item)))
        else:
            flat.append((k, str(v)))
    data = urllib.parse.urlencode(flat).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = json.loads(e.read().decode())
            return body
        except Exception as e:
            time.sleep(1 + attempt)
    return {"error": "retry_failed"}


def list_all(method, params, max_pages=2000):
    """Пагинация через filter[>ID]+order ASC."""
    out = []
    last_id = 0
    p = dict(params)
    p["order[ID]"] = "ASC"
    p["start"] = -1
    for _ in range(max_pages):
        pp = dict(p)
        pp["filter[>ID]"] = last_id
        r = call(method, pp)
        rows = r.get("result") or []
        if not rows:
            break
        out.extend(rows)
        last_id = int(rows[-1]["ID"])
        if len(rows) < 50:
            break
    return out


def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    print(f"  wrote {name}: {len(obj) if hasattr(obj,'__len__') else '?'}")


# 1. Справочники
print("== справочники ==")
dump("deal_fields.json", call("crm.deal.fields").get("result", {}))
dump("deal_userfields.json", call("crm.deal.userfield.list", {"order[ID]": "ASC"}).get("result", []))
dump("sources.json", call("crm.status.list", {"filter[ENTITY_ID]": "SOURCE", "order[SORT]": "ASC"}).get("result", []))
dump("deal_types.json", call("crm.status.list", {"filter[ENTITY_ID]": "DEAL_TYPE", "order[SORT]": "ASC"}).get("result", []))
users = list_all("user.get", {})
dump("users.json", [{k: u.get(k) for k in ("ID","NAME","LAST_NAME","ACTIVE","WORK_POSITION","UF_DEPARTMENT")} for u in users])

# 2. Сделки воронки [10] Продажи за 12 мес
DEAL_SELECT = ["ID","TITLE","CATEGORY_ID","STAGE_ID","STAGE_SEMANTIC_ID","OPPORTUNITY","CURRENCY_ID",
    "ASSIGNED_BY_ID","SOURCE_ID","TYPE_ID","CLOSED","DATE_CREATE","DATE_MODIFY","BEGINDATE","CLOSEDATE",
    "LAST_ACTIVITY_TIME","LAST_ACTIVITY_BY","COMPANY_ID","CONTACT_ID",
    "UF_CRM_1771495464","UF_CRM_1771324790"]

def pull_deals(cat, since, tag):
    rows = list_all("crm.deal.list", {
        "filter[CATEGORY_ID]": cat,
        "filter[>=DATE_CREATE]": since,
        **{f"select[{i}]": f for i, f in enumerate(DEAL_SELECT)},
    })
    dump(f"deals_cat{cat}_{tag}.json", rows)
    return rows

print("== сделки ==")
pull_deals(10, "2025-06-17", "12m")
# Открытые сделкам [10] вне 12м окна тоже важны — добавим все открытые
open10 = list_all("crm.deal.list", {
    "filter[CATEGORY_ID]": 10, "filter[CLOSED]": "N",
    **{f"select[{i}]": f for i, f in enumerate(DEAL_SELECT)},
})
dump("deals_cat10_open.json", open10)

# Телемаркетинг [50] — только агрегаты по 12м (объём, источники, причины)
TM_SELECT = ["ID","STAGE_ID","STAGE_SEMANTIC_ID","OPPORTUNITY","ASSIGNED_BY_ID","SOURCE_ID","CLOSED",
    "DATE_CREATE","CLOSEDATE","UF_CRM_1771324790"]
tm = list_all("crm.deal.list", {
    "filter[CATEGORY_ID]": 50, "filter[>=DATE_CREATE]": "2025-06-17",
    **{f"select[{i}]": f for i, f in enumerate(TM_SELECT)},
})
dump("deals_cat50_12m.json", tm)

# 3. История стадий воронки [10]
print("== история стадий ==")
sh = list_all("crm.stagehistory.list", {
    "entityTypeId": 2,
    "filter[CATEGORY_ID]": 10,
    "filter[>=CREATED_TIME]": "2025-06-17T00:00:00",
    "select[0]": "ID","select[1]": "OWNER_ID","select[2]": "CREATED_TIME",
    "select[3]": "STAGE_SEMANTIC_ID","select[4]": "STAGE_ID",
})
dump("stagehistory_cat10.json", sh)

print("DONE ->", OUT)
