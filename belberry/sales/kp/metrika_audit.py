#!/usr/bin/env python3
"""metrika_audit.py — РЕАЛЬНЫЕ факты из Яндекс.Метрики для прогноза в КП.

Превращает «оценку» (PR-CY) в «факт»: настоящий органический трафик, источники,
поисковые фразы, цели/конверсии — если счётчик клиента доступен в агентском
аккаунте Belberry (или выдан гостевой доступ).

Токен — в ~/.config/vibecoding/assistant/secrets/metrika-belberry.env (METRIKA_OAUTH_TOKEN).

Использование:
    python3 metrika_audit.py <counter_id | домен> [дней=90]
    python3 metrika_audit.py 100600199
    python3 metrika_audit.py panaceadoc.ru 30

Выход: metrika.json + краткий отчёт. Если счётчика нет в аккаунте — честно сообщает
(значит нужен гостевой доступ от клиента).
"""
from __future__ import annotations

import os
import sys
import json
import datetime
import urllib.request
import urllib.parse

# два агентских аккаунта: Belberry (медицина) и Acoola (остальные ниши)
ENV_PATHS = [
    ("belberry", os.path.expanduser("~/.config/vibecoding/assistant/secrets/metrika-belberry.env")),
    ("acoola", os.path.expanduser("~/.config/vibecoding/assistant/secrets/metrika-acoola.env")),
]
BASE = "https://api-metrika.yandex.net"


def _tokens() -> list[tuple[str, str]]:
    tok = os.environ.get("METRIKA_OAUTH_TOKEN")
    if tok:
        return [("env", tok)]
    out = []
    for name, path in ENV_PATHS:
        try:
            for line in open(path, encoding="utf-8"):
                if line.strip().startswith("METRIKA_OAUTH_TOKEN="):
                    out.append((name, line.split("=", 1)[1].strip()))
                    break
        except FileNotFoundError:
            continue
    if not out:
        sys.exit(f"❌ Нет токена Метрики ни в одном из: {[p for _, p in ENV_PATHS]}")
    return out


TOKENS = _tokens()
ACTIVE_TOKEN = TOKENS[0][1]  # find_counter переключает на аккаунт, где нашёлся счётчик


def call(path: str, params: dict, token: str | None = None) -> dict:
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "OAuth " + (token or ACTIVE_TOKEN)})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def find_counter(needle: str):
    """По id (число) или по домену — перебираем ОБА агентских аккаунта."""
    global ACTIVE_TOKEN
    if needle.isdigit():
        return int(needle), needle
    needle = needle.lower().replace("https://", "").replace("http://", "").strip("/")
    for acc_name, tok in TOKENS:
        offset = 1
        while True:
            r = call("/management/v1/counters", {"per_page": 200, "offset": offset}, token=tok)
            cs = r.get("counters", [])
            for c in cs:
                if needle in (c.get("site") or "").lower():
                    ACTIVE_TOKEN = tok
                    print(f"  счётчик найден в аккаунте «{acc_name}»")
                    return c["id"], c.get("site")
            if len(cs) < 200:
                break
            offset += 200
    return None, None


def stat(counter_id: int, d1: str, d2: str, metrics: str, dimensions: str = "",
         filters: str = "", limit: int = 10):
    p = {"ids": counter_id, "date1": d1, "date2": d2, "metrics": metrics,
         "accuracy": "full", "limit": limit}
    if dimensions:
        p["dimensions"] = dimensions
    if filters:
        p["filters"] = filters
    return call("/stat/v1/data", p)


def audit(counter_id: int, days: int) -> dict:
    today = datetime.date.today()
    d2 = today.isoformat()
    d1 = (today - datetime.timedelta(days=days)).isoformat()
    out = {"counter_id": counter_id, "period": f"{d1}..{d2}", "days": days}

    # суммарно: визиты, посетители, отказы, длительность
    tot = stat(counter_id, d1, d2,
               "ym:s:visits,ym:s:users,ym:s:bounceRate,ym:s:avgVisitDurationSeconds")
    m = (tot.get("data") or [{}])
    totals = tot.get("totals", [None] * 4)
    out["visits"], out["users"], out["bounce_rate"], out["avg_duration_s"] = \
        (round(totals[0]) if totals[0] else 0, round(totals[1]) if totals[1] else 0,
         round(totals[2], 1) if totals[2] else None,
         round(totals[3]) if totals[3] else None)

    # источники трафика → доля органики
    src = stat(counter_id, d1, d2, "ym:s:visits", "ym:s:lastsignTrafficSource", limit=20)
    out["sources"] = [{"source": r["dimensions"][0]["name"],
                       "visits": round(r["metrics"][0])} for r in src.get("data", [])]
    organic = next((s["visits"] for s in out["sources"]
                    if any(k in s["source"].lower()
                           for k in ("поиск", "organic", "search"))), 0)
    out["organic_visits"] = organic
    out["organic_pct"] = round(organic / out["visits"] * 100) if out["visits"] else 0

    # топ органических поисковых фраз
    phr = stat(counter_id, d1, d2, "ym:s:visits", "ym:s:searchPhrase",
               "ym:s:lastsignTrafficSource=='organic'", limit=10)
    out["top_phrases"] = [{"phrase": r["dimensions"][0]["name"],
                           "visits": round(r["metrics"][0])} for r in phr.get("data", [])]

    # цели и конверсии
    goals = call(f"/management/v1/counter/{counter_id}/goals", {}).get("goals", [])
    out["goals"] = []
    for g in goals[:8]:
        gid = g["id"]
        gr = stat(counter_id, d1, d2, f"ym:s:goal{gid}reaches,ym:s:goal{gid}conversionRate")
        gt = gr.get("totals", [0, 0])
        out["goals"].append({"name": g.get("name"), "reaches": round(gt[0] or 0),
                             "conversion": round(gt[1] or 0, 2)})
    return out


def main():
    if len(sys.argv) < 2:
        print("usage: metrika_audit.py <counter_id | домен> [дней=90]")
        sys.exit(1)
    needle = sys.argv[1]
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 90

    cid, site = find_counter(needle)
    if not cid:
        print(f"⚠ Счётчик для «{needle}» НЕ найден в агентских аккаунтах (Belberry + Acoola).")
        print("  → нужен гостевой доступ к Метрике от клиента (или счётчик не наш).")
        sys.exit(2)

    data = audit(cid, days)
    data["site"] = site
    json.dump(data, open("metrika.json", "w"), ensure_ascii=False, indent=2)

    print(f"# Метрика-факты — {site} (счётчик {cid}, {data['period']})")
    print(f"  визиты={data['visits']}  посетители={data['users']}  "
          f"отказы={data['bounce_rate']}%  ср.время={data['avg_duration_s']}с")
    print(f"  органика={data['organic_visits']} ({data['organic_pct']}% трафика)")
    if data["top_phrases"]:
        print("  топ органических фраз:")
        for p in data["top_phrases"][:5]:
            print(f"    {p['visits']:>5}  {p['phrase']}")
    if data["goals"]:
        print("  цели:")
        for g in data["goals"]:
            print(f"    {g['reaches']:>5} достижений · {g['conversion']}%  {g['name']}")
    print("→ metrika.json")


if __name__ == "__main__":
    main()
