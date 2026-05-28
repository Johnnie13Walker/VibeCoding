#!/usr/bin/env python3
"""
Детальный read-only аудит:
  1) По каждой воронке сделок: распределение по стадиям, по ответственным,
     по давности (last_modify_date).
  2) По "Данные для дашборда": кто создаёт, частота, связи.
  3) Dry-run чистки: сколько Реанимация/Retention/Лиды попадает под
     правила автозакрытия (без записи).

Никаких write-вызовов. Refresh не делаем.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

STATE = Path(
    os.environ.get(
        "BITRIX_APP_STATE_DIR",
        "/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state",
    )
) / "install.latest.json"


def auth() -> tuple[str, str]:
    s = json.loads(STATE.read_text())["payload"]
    return s["auth[client_endpoint]"].rstrip("/"), s["auth[access_token]"]


def call(method: str, params: dict | None = None) -> dict:
    endpoint, token = auth()
    flat: list[tuple[str, str]] = [("auth", token)]
    for k, v in (params or {}).items():
        if isinstance(v, list):
            for item in v:
                flat.append((k, str(item)))
        else:
            flat.append((k, str(v)))
    req = urllib.request.Request(
        f"{endpoint}/{method}",
        data=urllib.parse.urlencode(flat).encode(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode())
    if body.get("error") == "expired_token":
        sys.exit("⚠ access_token истёк, ресинкни state с VPS")
    return body


def page_all(method: str, params: dict, key: str = "result",
              id_field: str = "ID") -> list[dict]:
    """Постраничная выгрузка через filter[>ID]. На больших объёмах
    надёжнее, чем start/next (Bitrix кеширует total и теряет страницы)."""
    items: list[dict] = []
    last_id = 0
    while True:
        p = dict(params)
        p[f"filter[>{id_field}]"] = last_id
        p[f"order[{id_field}]"] = "ASC"
        # уберём конфликтующий order по ID DESC, если был
        p.pop("order[ID]", None)
        p["start"] = -1  # не считать total, ускоряет
        r = call(method, p)
        chunk = r.get(key) or []
        if not chunk:
            break
        items.extend(chunk)
        try:
            last_id = int(chunk[-1].get(id_field) or chunk[-1].get("id") or 0)
        except Exception:
            break
        if last_id == 0 or len(items) > 100000:
            break
    return items


def hr(t: str) -> None:
    print(f"\n{'='*72}\n{t}\n{'='*72}")


def fmt_age(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        d = datetime.fromisoformat(iso)
        now = datetime.now(d.tzinfo)
        days = (now - d).days
        return f"{days}d"
    except Exception:
        return iso


def get_users(ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    out: dict[str, str] = {}
    # batch через user.get
    for chunk_start in range(0, len(ids), 50):
        sub = list(ids)[chunk_start:chunk_start + 50]
        for uid in sub:
            r = call("user.get", {"ID": uid})
            res = r.get("result") or []
            if res:
                u = res[0]
                name = f"{u.get('NAME','')} {u.get('LAST_NAME','')}".strip() or uid
                out[uid] = name
    return out


# ============== AUDIT 1: воронки сделок ==============

PIPELINES = {
    10: "Продажи",
    22: "Аккаунтинг NEW",
    16: "Аккаунтинг OLD",
    28: "Проекты",
    38: "Реанимация",
    40: "Retention — Отвалы",
    44: "Retention — Оплачено",
    50: "Телемаркетинг",
}


def audit_pipeline(cat_id: int, name: str) -> None:
    print(f"\n── [{cat_id}] {name} ──")
    deals = page_all(
        "crm.deal.list",
        {
            "filter[CATEGORY_ID]": cat_id,
            "filter[CLOSED]": "N",
            "select[]": ["ID", "STAGE_ID", "ASSIGNED_BY_ID", "DATE_MODIFY",
                          "DATE_CREATE"],
            "order[ID]": "DESC",
        },
    )
    if not deals:
        print("  (открытых сделок нет)")
        return

    # по стадиям
    stages = Counter(d.get("STAGE_ID") for d in deals)
    print(f"  ОТКРЫТЫХ: {len(deals)}")
    print(f"  по стадиям:")
    for st, cnt in stages.most_common():
        print(f"     {st:28} {cnt:>5}")

    # по ответственным
    assignees = Counter(d.get("ASSIGNED_BY_ID") for d in deals)
    user_ids = {a for a in assignees.keys() if a}
    users = get_users(user_ids)
    print(f"  по ответственным:")
    for uid, cnt in assignees.most_common(10):
        print(f"     {users.get(uid, uid):30} {cnt:>5}")

    # по давности
    now = datetime.now(timezone.utc)
    buckets = {"<7d": 0, "7-30d": 0, "30-90d": 0, "90-180d": 0,
               "180-365d": 0, ">365d": 0, "no_modify": 0}
    for d in deals:
        m = d.get("DATE_MODIFY")
        if not m:
            buckets["no_modify"] += 1
            continue
        try:
            dt = datetime.fromisoformat(m)
            age = (now - dt.astimezone(timezone.utc)).days
        except Exception:
            buckets["no_modify"] += 1
            continue
        if age < 7:
            buckets["<7d"] += 1
        elif age < 30:
            buckets["7-30d"] += 1
        elif age < 90:
            buckets["30-90d"] += 1
        elif age < 180:
            buckets["90-180d"] += 1
        elif age < 365:
            buckets["180-365d"] += 1
        else:
            buckets[">365d"] += 1
    print(f"  по давности (last_modify):")
    for k, v in buckets.items():
        print(f"     {k:12} {v:>5}")


# ============== AUDIT 2: «Данные для дашборда» ==============

def audit_dashboard_data(entity_type_id: int, title: str) -> None:
    print(f"\n── entityTypeId={entity_type_id} «{title}» ──")
    # последние 200 элементов
    r = call(
        "crm.item.list",
        {
            "entityTypeId": entity_type_id,
            "order[id]": "DESC",
            "select[]": ["id", "title", "createdBy", "createdTime",
                          "updatedTime"],
            "start": 0,
        },
    )
    total = r.get("total", 0)
    items = (r.get("result") or {}).get("items") or []
    print(f"  total в портале: {total}")
    print(f"  выборка последних: {len(items)}")
    if not items:
        return

    # кем создаётся
    creators = Counter(i.get("createdBy") for i in items)
    user_ids = {str(c) for c in creators.keys() if c}
    users = get_users(user_ids)
    print(f"  createdBy (top 5):")
    for uid, cnt in creators.most_common(5):
        print(f"     {users.get(str(uid), str(uid)):30} {cnt:>5}")

    # частота создания за последние 7 / 30 дней (по выборке)
    now = datetime.now(timezone.utc)
    last_7 = 0
    last_30 = 0
    oldest = None
    for i in items:
        ct = i.get("createdTime")
        if not ct:
            continue
        try:
            dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
            age = (now - dt.astimezone(timezone.utc)).days
        except Exception:
            continue
        if age <= 7:
            last_7 += 1
        if age <= 30:
            last_30 += 1
        oldest = dt if oldest is None or dt < oldest else oldest
    print(f"  создано за <=7 дней: {last_7}")
    print(f"  создано за <=30 дней: {last_30}")
    print(f"  oldest в выборке:    {oldest}")

    # один элемент целиком для понимания полей
    sample = items[0]
    sample_id = sample.get("id")
    full = call("crm.item.get",
                {"entityTypeId": entity_type_id, "id": sample_id})
    item = (full.get("result") or {}).get("item") or {}
    print(f"  поля одного элемента (id={sample_id}):")
    for k, v in sorted(item.items())[:25]:
        s = str(v)
        if len(s) > 60:
            s = s[:60] + "…"
        print(f"     {k:35} {s}")


# ============== AUDIT 3: dry-run чистки ==============

def dryrun_cleanup() -> None:
    """Считаем, сколько закроем по правилам — НИЧЕГО НЕ ПИШЕМ."""
    hr("DRY-RUN ЧИСТКИ (никаких write)")
    rules = [
        ("Реанимация [38]", {"filter[CATEGORY_ID]": 38, "filter[CLOSED]": "N"}, 90),
        ("Retention — Отвалы [40]",
         {"filter[CATEGORY_ID]": 40, "filter[CLOSED]": "N"}, 90),
        ("Телемаркетинг [50]",
         {"filter[CATEGORY_ID]": 50, "filter[CLOSED]": "N"}, 90),
        ("Лиды (не JUNK / не CONVERTED)", None, 60),
    ]
    now = datetime.now(timezone.utc)
    for name, flt, days in rules:
        print(f"\n▶ {name}: правило 'не модифицировались >{days}d'")
        if flt is None:
            items = page_all(
                "crm.lead.list",
                {
                    "filter[!STATUS_ID]": ["CONVERTED", "JUNK"],
                    "select[]": ["ID", "DATE_MODIFY", "STATUS_ID",
                                  "ASSIGNED_BY_ID"],
                },
            )
        else:
            items = page_all(
                "crm.deal.list",
                {
                    **flt,
                    "select[]": ["ID", "DATE_MODIFY", "STAGE_ID",
                                  "ASSIGNED_BY_ID"],
                    "order[ID]": "DESC",
                },
            )
        total = len(items)
        match = []
        for it in items:
            m = it.get("DATE_MODIFY")
            if not m:
                continue
            try:
                dt = datetime.fromisoformat(m)
                age = (now - dt.astimezone(timezone.utc)).days
            except Exception:
                continue
            if age > days:
                match.append(it)
        print(f"  всего открытых:        {total}")
        print(f"  попадает под правило:  {len(match)}")
        if match:
            # распределение по стадиям/статусам матчей
            field = "STAGE_ID" if flt else "STATUS_ID"
            c = Counter(x.get(field) for x in match)
            for st, cnt in c.most_common(8):
                print(f"     {st:28} {cnt:>5}")
            # самые старые
            match.sort(key=lambda x: x.get("DATE_MODIFY") or "")
            print(f"  3 самых старых:")
            for x in match[:3]:
                print(f"     ID={x.get('ID')}  modify={x.get('DATE_MODIFY')}")


if __name__ == "__main__":
    hr("AUDIT 1: ВОРОНКИ ПО СТАДИЯМ / ОТВЕТСТВЕННЫМ / ДАВНОСТИ")
    for cid, nm in PIPELINES.items():
        audit_pipeline(cid, nm)

    hr("AUDIT 2: «ДАННЫЕ ДЛЯ ДАШБОРДА»")
    audit_dashboard_data(1040, "Данные для дашборда")
    audit_dashboard_data(1044, "Данные для дашборда (стадии сделки)")

    dryrun_cleanup()
