#!/usr/bin/env python3
"""
Read-only инвентаризация Bitrix24:
  - все воронки сделок + стадии + объёмы
  - все смарт-процессы + их воронки/стадии + объёмы
  - lead pipelines (если включены)

Никаких write-вызовов. Refresh токена не делает.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

STATE_PATH = Path(
    os.environ.get(
        "BITRIX_APP_STATE_DIR",
        "/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state",
    )
) / "install.latest.json"


def load_auth() -> tuple[str, str]:
    s = json.loads(STATE_PATH.read_text())["payload"]
    return s["auth[client_endpoint]"].rstrip("/"), s["auth[access_token]"]


def call(method: str, params: dict | None = None) -> dict:
    endpoint, token = load_auth()
    url = f"{endpoint}/{method}"
    flat: list[tuple[str, str]] = [("auth", token)]
    for k, v in (params or {}).items():
        if isinstance(v, list):
            for item in v:
                flat.append((k, str(item)))
        else:
            flat.append((k, str(v)))
    data = urllib.parse.urlencode(flat).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode())
    if "error" in body:
        if body.get("error") == "expired_token":
            sys.exit("⚠ access_token истёк — не делаем refresh, ресинкни с VPS")
        # некоторые методы дают error по правам — не убиваем весь прогон
        return body
    return body


def hr(title: str) -> None:
    print(f"\n{'='*72}\n{title}\n{'='*72}")


# ---------- DEALS ----------

def deal_pipelines() -> list[dict]:
    """Воронки сделок (категории)."""
    r = call("crm.dealcategory.list", {"order[SORT]": "ASC"})
    cats = r.get("result") or []
    # Default-воронка (ID=0) не возвращается этим методом — добавим вручную
    r0 = call("crm.dealcategory.default.get")
    default = r0.get("result")
    if default:
        cats.insert(0, {"ID": 0, "NAME": default.get("name", "Общая"), "SORT": 0})
    return cats


def deal_stages(category_id: int) -> list[dict]:
    r = call("crm.dealcategory.stage.list", {"id": category_id})
    return r.get("result") or []


def deal_count(category_id: int) -> tuple[int, int]:
    """returns (total, open)."""
    r_total = call(
        "crm.deal.list",
        {"filter[CATEGORY_ID]": category_id, "select[]": ["ID"], "start": 0},
    )
    r_open = call(
        "crm.deal.list",
        {
            "filter[CATEGORY_ID]": category_id,
            "filter[CLOSED]": "N",
            "select[]": ["ID"],
            "start": 0,
        },
    )
    return r_total.get("total", 0), r_open.get("total", 0)


def report_deals() -> None:
    hr("ВОРОНКИ СДЕЛОК")
    for cat in deal_pipelines():
        cid = int(cat["ID"])
        name = cat.get("NAME") or "<без имени>"
        total, open_ = deal_count(cid)
        print(f"\n▶ [{cid}] {name}  — всего {total}, открытых {open_}")
        for s in deal_stages(cid):
            print(f"     {s.get('STATUS_ID'):28} {s.get('NAME')}")


# ---------- SMART PROCESSES ----------

def smart_types() -> list[dict]:
    r = call("crm.type.list")
    return r.get("result", {}).get("types") or []


def smart_categories(entity_type_id: int) -> list[dict]:
    r = call("crm.category.list", {"entityTypeId": entity_type_id})
    return r.get("result", {}).get("categories") or []


def smart_stages(entity_type_id: int, category_id: int | None) -> list[dict]:
    """Стадии смарт-процесса. STATUS ENTITY_ID = DYNAMIC_<typeId>_STAGE_<catId>."""
    status_entity = f"DYNAMIC_{entity_type_id}"
    if category_id is not None:
        status_entity = f"DYNAMIC_{entity_type_id}_STAGE_{category_id}"
    r = call(
        "crm.status.list",
        {"filter[ENTITY_ID]": status_entity, "order[SORT]": "ASC"},
    )
    return r.get("result") or []


def smart_count(entity_type_id: int) -> int:
    r = call(
        "crm.item.list",
        {"entityTypeId": entity_type_id, "select[]": ["id"], "start": 0},
    )
    return r.get("total", 0)


def report_smart_processes() -> None:
    hr("СМАРТ-ПРОЦЕССЫ")
    types = smart_types()
    for t in types:
        tid = int(t["entityTypeId"])
        title = t.get("title")
        total = smart_count(tid)
        print(f"\n▶ entityTypeId={tid}  «{title}»  — всего элементов {total}")
        cats = smart_categories(tid)
        if cats:
            for cat in cats:
                cid = int(cat["id"])
                cname = cat.get("name")
                stages = smart_stages(tid, cid)
                print(f"   • воронка [{cid}] «{cname}» — {len(stages)} стадий")
                for s in stages:
                    print(f"        {s.get('STATUS_ID'):40} {s.get('NAME')}")
        else:
            stages = smart_stages(tid, None)
            print(f"   • (без множественных воронок) — {len(stages)} стадий")
            for s in stages[:30]:
                print(f"        {s.get('STATUS_ID'):40} {s.get('NAME')}")


# ---------- LEADS ----------

def report_leads() -> None:
    hr("ЛИДЫ (если включены)")
    r = call("crm.lead.list", {"select[]": ["ID"], "start": 0})
    if "error" in r:
        print("  лиды недоступны:", r.get("error_description"))
        return
    total = r.get("total", 0)
    r_open = call(
        "crm.lead.list",
        {"filter[CLOSED]": "N", "select[]": ["ID"], "start": 0},
    )
    print(f"  всего лидов: {total}, открытых: {r_open.get('total', 0)}")
    rs = call("crm.status.list", {"filter[ENTITY_ID]": "STATUS"})
    for s in rs.get("result") or []:
        print(f"     {s.get('STATUS_ID'):20} {s.get('NAME')}")


if __name__ == "__main__":
    endpoint, _ = load_auth()
    print(f"endpoint: {endpoint}")
    report_deals()
    report_smart_processes()
    report_leads()
