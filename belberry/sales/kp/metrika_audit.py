#!/usr/bin/env python3
"""metrika_audit.py — РЕАЛЬНЫЕ факты из Яндекс.Метрики для прогноза в КП.

Превращает «оценку» (PR-CY) в «факт»: настоящий органический трафик, источники,
поисковые фразы, цели/конверсии — если счётчик клиента доступен в агентском
аккаунте Belberry (или выдан гостевой доступ).

Токен — в ~/.config/vibecoding/assistant/secrets/metrika-belberry.env (METRIKA_OAUTH_TOKEN).

Использование:
    python3 metrika_audit.py <counter_id | домен> [дней=90] [целевой_регион]
    python3 metrika_audit.py 100600199
    python3 metrika_audit.py panaceadoc.ru 30
    python3 metrika_audit.py crystal-sound.com 180 "Санкт-Петербург"

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

# ── Пороги детекта проблем ───────────────────────────────────────────────────
# Проблема создаётся ТОЛЬКО когда реальные числа из API превышают порог.
MIN_VISITS_FOR_VERDICT = 100   # меньше визитов в срезе — статистика шумная, вывод не делаем
PAGE_BOUNCE_FACTOR = 1.4       # отказы страницы выше среднего по сайту в 1.4 раза = «дыра»
PAGE_SHARE_MIN = 5.0           # …и страница даёт ≥5% трафика (иначе это мелочь, а не проблема)
MOBILE_SHARE_MIN = 40.0        # мобильные ≥40% визитов — сломанная мобильная версия критична
MOBILE_BOUNCE_FACTOR = 1.4     # отказы на мобильных выше десктопных в 1.4 раза
SE_MIN_SHARE = 25.0            # норма по РФ ~40/60 Яндекс/Google; доля ПС <25% = просадка
SE_NORM_HINT = "40/60"         # ориентир распределения Яндекс/Google по стране
ORGANIC_CONV_FACTOR = 0.6      # конверсия органики <60% от платного трафика = нецелевые запросы
GEO_NONTARGET_MAX = 30.0       # >30% визитов вне целевого региона = продвижение работает мимо
TREND_DROP_FACTOR = 0.7        # текущий полный месяц <70% от пика = заметное падение трафика
TREND_FLAT_TOLERANCE = 10.0    # изменение в пределах ±10% за 3 месяца считаем «стабильно»


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
         "accuracy": "full", "limit": limit, "lang": "ru"}  # lang=ru: имена измерений по-русски
    if dimensions:
        p["dimensions"] = dimensions
    if filters:
        p["filters"] = filters
    return call("/stat/v1/data", p)


def stat_bytime(counter_id: int, d1: str, d2: str, metrics: str,
                filters: str = "", group: str = "month") -> list[dict]:
    """Помесячный ряд: [{"month": "YYYY-MM", "visits": int, "partial": bool}].
    partial — интервал не покрывает календарный месяц целиком (края периода)."""
    p = {"ids": counter_id, "date1": d1, "date2": d2, "metrics": metrics,
         "accuracy": "full", "group": group}
    if filters:
        p["filters"] = filters
    r = call("/stat/v1/data/bytime", p)
    data = r.get("data") or [{}]
    values = (data[0].get("metrics") or [[]])[0]
    months = []
    for (i1, i2), v in zip(r.get("time_intervals", []), values):
        a = datetime.date.fromisoformat(i1)
        b = datetime.date.fromisoformat(i2)
        # полный месяц: с 1-го числа по последний день месяца
        next_month = (b.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
        full = a.day == 1 and (next_month - b).days == 1
        months.append({"month": i1[:7], "visits": round(v or 0), "partial": not full})
    return months


# ── Чистые функции анализа (числа → вердикт), тестируются без сети ───────────

def trend_stats(months: list[dict]) -> dict:
    """Пик, текущий полный месяц, % изменения, направление последних 3 месяцев."""
    full = [m for m in months if not m.get("partial")]
    out = {"months": months, "peak": None, "peak_month": None,
           "current": None, "current_month": None, "change_pct": None,
           "direction": None}
    if not full:
        return out
    peak = max(full, key=lambda m: m["visits"])
    cur = full[-1]
    out.update(peak=peak["visits"], peak_month=peak["month"],
               current=cur["visits"], current_month=cur["month"])
    if peak["visits"]:
        out["change_pct"] = round((cur["visits"] - peak["visits"]) / peak["visits"] * 100, 1)
    last3 = full[-3:]
    if len(last3) >= 2 and last3[0]["visits"]:
        delta = (last3[-1]["visits"] - last3[0]["visits"]) / last3[0]["visits"] * 100
        out["direction"] = ("рост" if delta > TREND_FLAT_TOLERANCE
                            else "падение" if delta < -TREND_FLAT_TOLERANCE
                            else "стабильно")
    return out


def problem_from_organic_trend(organic_trend: dict) -> dict | None:
    """Органика упала: текущий полный месяц < TREND_DROP_FACTOR от пика."""
    peak, cur = organic_trend.get("peak"), organic_trend.get("current")
    if not peak or cur is None or peak < MIN_VISITS_FOR_VERDICT:
        return None
    if cur >= peak * TREND_DROP_FACTOR or organic_trend["peak_month"] == organic_trend["current_month"]:
        return None
    drop = round((peak - cur) / peak * 100)
    return {
        "fact": (f"Поисковый трафик упал с {peak} визитов в месяц "
                 f"({organic_trend['peak_month']}) до {cur} "
                 f"({organic_trend['current_month']}) — минус {drop}%"),
        "evidence": {"organic_peak": peak, "organic_peak_month": organic_trend["peak_month"],
                     "organic_current": cur, "organic_current_month": organic_trend["current_month"],
                     "drop_pct": drop},
        "so_what": "Сайт теряет бесплатный трафик из поиска — позиции проседают, обращений всё меньше",
        "action": "Технический аудит, проверка фильтров поисковых систем, восстановление просевших страниц и запросов",
    }


def problems_from_pages(pages: list[dict], site_bounce: float | None,
                        total_visits: int) -> list[dict]:
    """Страницы-дыры: отказы > среднего×PAGE_BOUNCE_FACTOR при доле ≥ PAGE_SHARE_MIN%.
    Помечает строки ключом problem=True, возвращает до 3 проблем (худшие по отказам)."""
    if not site_bounce or not total_visits or total_visits < MIN_VISITS_FOR_VERDICT:
        return []
    flagged = []
    for p in pages:
        share = round(p["visits"] / total_visits * 100, 1)
        p["traffic_share_pct"] = share
        bad = (p.get("bounce_rate") is not None
               and p["bounce_rate"] > site_bounce * PAGE_BOUNCE_FACTOR
               and share >= PAGE_SHARE_MIN)
        p["problem"] = bad
        if bad:
            flagged.append(p)
    flagged.sort(key=lambda p: p["bounce_rate"], reverse=True)
    out = []
    for p in flagged[:3]:
        out.append({
            "fact": (f"Страница {p['page']} собирает {p['traffic_share_pct']}% трафика, "
                     f"но отказы {p['bounce_rate']}% против {site_bounce}% в среднем по сайту"),
            "evidence": {"page": p["page"], "traffic_share_pct": p["traffic_share_pct"],
                         "page_bounce": p["bounce_rate"], "site_bounce": site_bounce},
            "so_what": "Заметная часть посетителей уходит с этой страницы, не сделав ни одного действия",
            "action": "Переработка страницы: первый экран, скорость загрузки, содержание под запрос, призыв к действию",
        })
    return out


def problem_from_devices(mobile_visits: int, mobile_bounce: float | None,
                         desktop_visits: int, desktop_bounce: float | None,
                         total_visits: int) -> dict | None:
    """Мобильные отказы > десктопных×MOBILE_BOUNCE_FACTOR при доле мобильных ≥ MOBILE_SHARE_MIN%."""
    if (not total_visits or total_visits < MIN_VISITS_FOR_VERDICT
            or mobile_bounce is None or not desktop_bounce):
        return None
    share = round(mobile_visits / total_visits * 100)
    if share < MOBILE_SHARE_MIN or mobile_bounce <= desktop_bounce * MOBILE_BOUNCE_FACTOR:
        return None
    return {
        "fact": (f"Мобильные дают {share}% визитов, но отказы {mobile_bounce}% "
                 f"против {desktop_bounce}% на десктопе"),
        "evidence": {"mobile_share": share, "mobile_bounce": mobile_bounce,
                     "desktop_bounce": desktop_bounce},
        "so_what": "Больше всего трафика приходит с телефонов — и уходит, не увидев предложение",
        "action": "Аудит мобильной вёрстки ключевых страниц, ускорение загрузки, упрощение форм",
    }


def problem_from_search_engines(yandex_visits: int, google_visits: int,
                                organic_visits: int) -> dict | None:
    """Перекос Яндекс/Google: доля одной ПС < SE_MIN_SHARE% (норма по стране ~40/60)."""
    if not organic_visits or organic_visits < MIN_VISITS_FOR_VERDICT:
        return None
    y = round(yandex_visits / organic_visits * 100)
    g = round(google_visits / organic_visits * 100)
    if y >= SE_MIN_SHARE and g >= SE_MIN_SHARE:
        return None
    weak, weak_share, strong, strong_share = (
        ("Яндекс", y, "Google", g) if y < g else ("Google", g, "Яндекс", y))
    return {
        "fact": (f"{weak} даёт лишь {weak_share}% поискового трафика против "
                 f"{strong_share}% у {strong} (норма по стране ~{SE_NORM_HINT})"),
        "evidence": {"yandex_share": y, "google_share": g,
                     "organic_visits": organic_visits, "norm_hint": SE_NORM_HINT},
        "so_what": f"Сайт почти не виден в {weak} — теряется примерно половина возможного поискового трафика",
        "action": f"Отдельная проработка под {weak}: индексация, требования этой поисковой системы, недостающие страницы",
    }


def problem_from_source_conversion(organic_conv: float | None, ad_conv: float | None,
                                   organic_visits: int, ad_visits: int,
                                   goal_name: str) -> dict | None:
    """Органика конвертит < ORGANIC_CONV_FACTOR от платного → нецелевые запросы в SEO."""
    if (organic_conv is None or not ad_conv
            or organic_visits < MIN_VISITS_FOR_VERDICT
            or ad_visits < MIN_VISITS_FOR_VERDICT):
        return None
    if organic_conv >= ad_conv * ORGANIC_CONV_FACTOR:
        return None
    return {
        "fact": (f"Конверсия из поиска {organic_conv}% против {ad_conv}% "
                 f"с рекламы (цель «{goal_name}»)"),
        "evidence": {"organic_conversion": organic_conv, "ad_conversion": ad_conv,
                     "organic_visits": organic_visits, "ad_visits": ad_visits,
                     "goal": goal_name},
        "so_what": "Поисковый трафик приходит по нецелевым запросам — посетители не те, кто готов обратиться",
        "action": "Пересборка семантики под коммерческие запросы, посадочные страницы под намерение «купить/записаться»",
    }


def problem_from_geo(regions: list[dict], target_region: str | None) -> dict | None:
    """Доля визитов вне целевого региона > GEO_NONTARGET_MAX% (регион из брифа)."""
    if not target_region or not regions:
        return None
    known = [r for r in regions if r.get("region") and "не определено" not in r["region"].lower()
             and "not specified" not in r["region"].lower()]
    total = sum(r["visits"] for r in known)
    if total < MIN_VISITS_FOR_VERDICT:
        return None
    needle = target_region.lower()
    nontarget = sum(r["visits"] for r in known if needle not in r["region"].lower())
    share = round(nontarget / total * 100)
    if share <= GEO_NONTARGET_MAX:
        return None
    # Реальный целевой регион всегда даёт часть собственного трафика; ~100% «мимо»
    # означает не гео-проблему, а битый/плейсхолдерный таргет — не выводим клиенту.
    if share >= 99:
        return None
    return {
        "fact": f"{share}% визитов приходят не из целевого региона ({target_region})",
        "evidence": {"nontarget_share": share, "target_region": target_region,
                     "nontarget_visits": nontarget, "known_region_visits": total},
        "so_what": "Продвижение работает на аудиторию, которая не станет клиентом",
        "action": "Региональная привязка: регион в Вебмастере, локальная семантика, страницы с топонимами",
    }


def render_problems_html(problems: list[dict]) -> str:
    """<tr>-строки для слайда «проблема → решение» (формат problem_solution.html)."""
    rows = []
    for p in problems:
        sw = p["so_what"]
        sw = sw[:1].lower() + sw[1:]  # внутри предложения — со строчной
        rows.append(f'        <tr><td class="metric">{p["fact"]} — {sw}</td>'
                    f'<td>{p["action"]}</td></tr>')
    return "\n".join(rows)


def audit(counter_id: int, days: int, target_region: str | None = None) -> dict:
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
        out["goals"].append({"id": gid, "name": g.get("name"), "reaches": round(gt[0] or 0),
                             "conversion": round(gt[1] or 0, 2)})

    problems: list[dict] = []

    # 1. тренд помесячно: общий и органика
    out["trend"] = {
        "total": trend_stats(stat_bytime(counter_id, d1, d2, "ym:s:visits")),
        "organic": trend_stats(stat_bytime(counter_id, d1, d2, "ym:s:visits",
                                           "ym:s:lastsignTrafficSource=='organic'")),
    }
    p = problem_from_organic_trend(out["trend"]["organic"])
    if p:
        problems.append(p)

    # 2. страницы входа с отказами → «дыры»
    pg = stat(counter_id, d1, d2, "ym:s:visits,ym:s:bounceRate", "ym:s:startURLPath", limit=10)
    out["entry_pages"] = [{"page": r["dimensions"][0].get("name") or "/",
                           "visits": round(r["metrics"][0]),
                           "bounce_rate": round(r["metrics"][1], 1)}
                          for r in pg.get("data", [])]
    problems += problems_from_pages(out["entry_pages"], out["bounce_rate"], out["visits"])

    # главная цель — для срезов конверсии (по максимуму достижений)
    main_goal = max(out["goals"], key=lambda g: g["reaches"], default=None) \
        if out["goals"] else None
    out["main_goal"] = ({"id": main_goal["id"], "name": main_goal["name"]}
                        if main_goal and main_goal["reaches"] else None)
    conv_metric = f",ym:s:goal{out['main_goal']['id']}conversionRate" if out["main_goal"] else ""

    # 3. мобильные против десктопа
    dv = stat(counter_id, d1, d2, "ym:s:visits,ym:s:bounceRate" + conv_metric,
              "ym:s:deviceCategory", limit=10)
    out["devices"] = {}
    for r in dv.get("data", []):
        did = r["dimensions"][0].get("id")
        row = {"visits": round(r["metrics"][0]), "bounce_rate": round(r["metrics"][1], 1)}
        if conv_metric:
            row["conversion"] = round(r["metrics"][2] or 0, 2)
        out["devices"][did] = row
    mob = out["devices"].get("mobile") or {}
    dsk = out["devices"].get("desktop") or {}
    p = problem_from_devices(mob.get("visits", 0), mob.get("bounce_rate"),
                             dsk.get("visits", 0), dsk.get("bounce_rate"),
                             out["visits"])
    if p:
        problems.append(p)

    # 4. Яндекс против Google в органике
    se = stat(counter_id, d1, d2, "ym:s:visits", "ym:s:lastsignSearchEngineRoot",
              "ym:s:lastsignTrafficSource=='organic'", limit=10)
    se_rows = {r["dimensions"][0].get("id"): round(r["metrics"][0])
               for r in se.get("data", [])}
    se_total = sum(se_rows.values())
    out["search_engines"] = {
        "yandex": se_rows.get("yandex", 0), "google": se_rows.get("google", 0),
        "other": se_total - se_rows.get("yandex", 0) - se_rows.get("google", 0),
        "yandex_pct": round(se_rows.get("yandex", 0) / se_total * 100) if se_total else 0,
        "google_pct": round(se_rows.get("google", 0) / se_total * 100) if se_total else 0,
    }
    p = problem_from_search_engines(se_rows.get("yandex", 0), se_rows.get("google", 0), se_total)
    if p:
        problems.append(p)

    # 5. конверсия главной цели по источникам трафика
    out["source_conversion"] = []
    if out["main_goal"]:
        sc = stat(counter_id, d1, d2, "ym:s:visits" + conv_metric,
                  "ym:s:lastsignTrafficSource", limit=15)
        rows = {}
        for r in sc.get("data", []):
            sid = r["dimensions"][0].get("id")
            rows[sid] = {"source": r["dimensions"][0].get("name"),
                         "visits": round(r["metrics"][0]),
                         "conversion": round(r["metrics"][1] or 0, 2)}
        out["source_conversion"] = list(rows.values())
        org, ad = rows.get("organic"), rows.get("ad")
        if org and ad:
            p = problem_from_source_conversion(
                org["conversion"], ad["conversion"],
                org["visits"], ad["visits"], out["main_goal"]["name"])
            if p:
                problems.append(p)

    # 6. география (топ-5; проблема только если задан целевой регион)
    geo = stat(counter_id, d1, d2, "ym:s:visits", "ym:s:regionArea", limit=20)
    geo_rows = [{"region": r["dimensions"][0].get("name"),
                 "visits": round(r["metrics"][0])} for r in geo.get("data", [])]
    out["geo"] = geo_rows[:5]
    out["target_region"] = target_region
    p = problem_from_geo(geo_rows, target_region)
    if p:
        problems.append(p)

    out["problems"] = problems
    return out


def main():
    if len(sys.argv) < 2:
        print("usage: metrika_audit.py <counter_id | домен> [дней=90] [целевой_регион]")
        sys.exit(1)
    needle = sys.argv[1]
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    target_region = sys.argv[3] if len(sys.argv) > 3 else None

    cid, site = find_counter(needle)
    if not cid:
        print(f"⚠ Счётчик для «{needle}» НЕ найден в агентских аккаунтах (Belberry + Acoola).")
        print("  → нужен гостевой доступ к Метрике от клиента (или счётчик не наш).")
        sys.exit(2)

    data = audit(cid, days, target_region)
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
    tr = data.get("trend", {}).get("organic", {})
    if tr.get("peak"):
        print(f"  органика помесячно: пик {tr['peak']} ({tr['peak_month']}), "
              f"текущий {tr['current']} ({tr['current_month']}), "
              f"направление 3 мес: {tr['direction']}")
    probs = data.get("problems", [])
    if probs:
        print(f"  ПРОБЛЕМЫ ({len(probs)}):")
        for p in probs:
            print(f"    • {p['fact']}")
            print(f"      → {p['action']}")
    else:
        print("  Проблем по порогам не найдено (честный результат).")
    print("→ metrika.json")


if __name__ == "__main__":
    main()
