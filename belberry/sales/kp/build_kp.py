#!/usr/bin/env python3
"""build_kp.py — авто-сбор ПРОВЕРЯЕМЫХ SEO-данных для шаблона КП Belberry.

Источник — официальный API PR-CY (тот же сервис, что за analitics.belberry-dev.ru),
один GET-вызов на домен отдаёт всё: ИКС, индексацию, техаудит, органику, конкурентов.

    GET https://pr-cy.ru/api/v1.1.0/analysis/base/<домен>?key=<KEY>

Ключ — в ~/.config/vibecoding/assistant/secrets/prcy.env (PRCY_API_KEY) или env-переменной.
Лимит API: 2 запроса/сек (между вызовами пауза 0.6с).

Использование:
    python3 build_kp.py <домен> [конкурент1 конкурент2 ...]
    python3 build_kp.py med-shushary.ru flmed.ru feniksmed.ru cl-veda.ru

Выход (в текущей папке):
    audit.json          — полный аудит клиента + конкурентов
    seo_benchmark.html  — готовый <tbody> для слайда «SEO-показатели: вы и соседи»
    + краткий отчёт в stdout

Контроль достоверности: на med-shushary.ru ИКС=80, Я=354, G=130 — совпадает с пресейл-аудитом.
"""
import os
import re
import sys
import json
import time
import urllib.request
import urllib.parse
import urllib.error

API = "https://pr-cy.ru/api/v1.1.0/analysis/base/"
ENV_PATH = os.path.expanduser("~/.config/vibecoding/assistant/secrets/prcy.env")


def _load_key() -> str:
    key = os.environ.get("PRCY_API_KEY")
    if key:
        return key
    try:
        for line in open(ENV_PATH, encoding="utf-8"):
            line = line.strip()
            if line.startswith("PRCY_API_KEY="):
                return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    sys.exit(f"❌ Нет ключа PR-CY. Положи PRCY_API_KEY в {ENV_PATH} или env-переменную.")


KEY = _load_key()


def _g(d: dict, *path):
    """Безопасно достать вложенное значение d[a][b]... → None при отсутствии."""
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def analyze(domain: str) -> dict:
    """Один вызов PR-CY API → плоский аудит домена. error при сбое/лимите."""
    out = {"domain": domain}
    url = API + urllib.parse.quote(domain) + "?" + urllib.parse.urlencode({"key": KEY})
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=60) as r:
            d = json.loads(r.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        out["error"] = "rate_limited (503)" if e.code == 503 else f"http {e.code}"
        return out
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)
        return out

    out.update({
        # авторитет и индексация
        "sqi": _g(d, "yandexSqi", "yandexSqi"),
        "yandex_index": _g(d, "yandexIndex", "yandexIndex"),
        "google_index": _g(d, "googleIndex", "googleIndex"),
        "donors": _g(d, "mainPageExternalLinks", "externalIndexCount"),
        "prcy_rank": _g(d, "prcyRank", "prcyRankTotal"),
        "links_factor": _g(d, "prcyRank", "prcyRankLinksFactor"),
        "trust_factor": _g(d, "prcyRank", "prcyRankTrustFactor"),
        # трафик/поведение (доля органики — реальная, не оценка трафика)
        "organic_pct": _g(d, "trafficSources", "trafficSourcesOrganicSearch"),
        "bounce_rate": _g(d, "bounceRate", "bounceRate"),
        "avg_duration": _g(d, "avgVisitDuration", "avgVisitDuration"),
        # техаудит
        "https": _g(d, "ssl", "sslAccess"),
        "robots": _g(d, "robotsTxt", "robotsFileExists"),
        "sitemap": bool(_g(d, "sitemap", "sitemapUrl")),
        "schema_org": _g(d, "microdataSchemaOrg", "microdataSchemaOrgExists"),
        "load_time": _g(d, "loadTime", "loadTime"),
        "status_code": _g(d, "indexing", "statusCode"),
        "title": _g(d, "mainPageTitle", "title"),
        # динамика трафика (помесячно) — для слайда «остановить просадку»
        "visits_monthly": _g(d, "publicStatistics", "publicStatisticsVisitsMonthly"),
        "visits_history": _g(d, "publicStatistics",
                             "publicStatisticsPrcyVisitsMonthlyHistory", "months") or {},
        "visits_source": _g(d, "publicStatistics", "publicStatisticsSourceType"),
    })
    return out


_MONTHS_RU = ["янв", "фев", "мар", "апр", "май", "июн",
              "июл", "авг", "сен", "окт", "ноя", "дек"]


def _ym_ru(ym: str) -> str:
    """'202511' → 'ноя 25'."""
    return f"{_MONTHS_RU[int(ym[4:6]) - 1]} {ym[2:4]}"


def trend_summary(client: dict):
    """Пик/текущее/изменение по помесячной истории визитов. None, если нет данных."""
    hist = client.get("visits_history") or {}
    months = sorted(hist.items())
    if len(months) < 2:
        return None
    peak_ym, peak = max(months, key=lambda x: x[1])
    cur_ym, cur = months[-1]
    change = round((cur - peak) / peak * 100) if peak else 0
    return {
        "peak": peak, "peak_month": _ym_ru(peak_ym),
        "current": cur, "current_month": _ym_ru(cur_ym),
        "change_pct": change,
        "source": client.get("visits_source"),
    }


def _fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def crawl_commercial(domain: str) -> dict:
    """Коммерческий / E-E-A-T чек главной: запись, цены, отзывы, врачи, телефон, Schema."""
    url = domain if domain.startswith("http") else "https://" + domain
    try:
        h = _fetch(url, 25).lower()
    except Exception:  # noqa: BLE001
        return {}
    return {
        "online_booking": any(k in h for k in ("онлайн-запис", "записаться", "запись на при", "online-zapis")),
        "prices": ("₽" in h) or ("руб" in h) or ("прайс" in h),
        "reviews": "отзыв" in h,
        "doctors": any(k in h for k in ("врач", "доктор", "специалист")),
        "phone": bool(re.search(r"\+7[\s(]?\d{3}", h)),
        "schema": "schema.org" in h,
    }


def collect(domain: str, competitors: list) -> dict:
    client = analyze(domain)
    client["commercial"] = crawl_commercial(domain)
    comps = []
    for c in competitors:
        time.sleep(0.6)  # лимит API 2 req/sec
        comps.append(analyze(c))
    return {"client": client, "competitors": comps}


def render_benchmark(data: dict) -> str:
    """<tbody>-строки для слайда сравнения: по ИКС убыв., клиент — .totalrow,
    слабый Google клиента — красным."""
    client = data["client"]
    rows = data["competitors"] + [client]
    rows.sort(key=lambda c: (c.get("sqi") or 0), reverse=True)
    g_vals = [c.get("google_index") for c in rows if c.get("google_index")]
    worst_g = bool(g_vals) and client.get("google_index") == min(g_vals)
    html = []
    for c in rows:
        me = c["domain"] == client["domain"]
        cls = ' class="totalrow"' if me else ""
        name = (f'{c["domain"]} <span class="pill">вы</span>'
                if me else f'<strong>{c["domain"]}</strong>')
        sqi = c.get("sqi") or "—"
        yi = c.get("yandex_index") or "—"
        gi = c.get("google_index") or "—"
        gs = ' style="color:#a13442;"' if (me and worst_g) else ""
        html.append(
            f'          <tr{cls}><td>{name}</td>'
            f'<td class="right num">{sqi}</td>'
            f'<td class="right num">{yi}</td>'
            f'<td class="right num"{gs}>{gi}</td></tr>'
        )
    return "\n".join(html)


def render_problem_solution(data: dict) -> str:
    """<tr>-строки «Проблема → Что делаем» из РЕАЛЬНЫХ флагов аудита.
    Только то, что детектируется по API; контентные строки (врачи, услуги)
    добавляются вручную из брифа/транскрипта."""
    c = data["client"]
    comps = data["competitors"]
    rows = []

    def add(problem, solution):
        rows.append((problem, solution))

    yi, gi = c.get("yandex_index"), c.get("google_index")
    if yi and gi and gi < yi * 0.7:
        add(f"В Google проиндексировано {gi} страниц против {yi} в Яндексе — под Google почти не работали",
            "Открываем сайт для Google: robots, карта сайта, ускоряем индексацию")
    comp_sqi = [x["sqi"] for x in comps if x.get("sqi")]
    if c.get("sqi") and comp_sqi and c["sqi"] < max(comp_sqi):
        add(f"Авторитет сайта (ИКС {c['sqi']}) ниже соседей-лидеров ({max(comp_sqi)})",
            "Наращиваем ИКС: проработка страниц, ссылки, поведенческие факторы")
    if c.get("donors") is not None and c["donors"] < 10:
        add(f"Мало внешних ссылок на сайт (доноров: {c['donors']}) — низкий авторитет",
            "Расширяем ссылочную массу качественными тематическими донорами")
    if c.get("schema_org") is False:
        add("Нет микроразметки Schema.org — поисковики хуже понимают страницы",
            "Внедряем микроразметку услуг, врачей и организации")
    if c.get("robots") is False:
        add("Нет robots.txt — индексация неуправляема",
            "Настраиваем robots.txt и директивы индексации")
    if c.get("sitemap") is False:
        add("Нет карты сайта (sitemap) — часть страниц не индексируется",
            "Генерируем sitemap для полной индексации")
    if c.get("load_time") and c["load_time"] > 1.5:
        add(f"Сайт грузится медленно ({round(c['load_time'], 1)} с)",
            "Ускоряем по чек-листу Core Web Vitals (PageSpeed)")
    if c.get("bounce_rate") and c["bounce_rate"] > 50:
        add(f"Высокий процент отказов ({c['bounce_rate']}%)",
            "Дорабатываем юзабилити и коммерческие блоки страниц")
    if c.get("https") is False:
        add("Нет HTTPS — поисковики понижают незащищённые сайты",
            "Подключаем SSL-сертификат")
    # коммерческий / E-E-A-T чек главной
    com = c.get("commercial") or {}
    if com.get("online_booking") is False:
        add("На сайте не видно онлайн-записи",
            "Добавляем заметный блок онлайн-записи и CTA")
    if com.get("prices") is False:
        add("Не нашли цены на услуги — снижает доверие и конверсию",
            "Выводим цены/прайс на страницы услуг")
    if com.get("reviews") is False:
        add("Нет блока отзывов пациентов",
            "Добавляем отзывы и работу с репутацией (E-E-A-T)")

    if not rows:
        rows = [("Критичных технических проблем не найдено",
                 "Фокус на семантике, контенте и ссылочной массе")]
    return "\n".join(
        f'        <tr><td class="metric">{p}</td><td>{s}</td></tr>' for p, s in rows
    )


def main():
    if len(sys.argv) < 2:
        print("usage: build_kp.py <домен> [конкуренты...]")
        sys.exit(1)
    domain, comps = sys.argv[1], sys.argv[2:]
    data = collect(domain, comps)

    data["trend"] = trend_summary(data["client"])
    json.dump(data, open("audit.json", "w"), ensure_ascii=False, indent=2)
    open("seo_benchmark.html", "w").write(render_benchmark(data))
    open("problem_solution.html", "w").write(render_problem_solution(data))

    c = data["client"]
    print(f"# SEO-аудит (PR-CY API) — {domain}")
    if c.get("error"):
        print("  ⚠ ", c["error"])
    else:
        print(f"  ИКС={c['sqi']}  Яндекс={c['yandex_index']}  Google={c['google_index']}  "
              f"доноры={c['donors']}  PR-CY Rank={c['prcy_rank']}")
        print(f"  органика={c['organic_pct']}%  отказы={c['bounce_rate']}%  "
              f"HTTPS={c['https']}  robots={c['robots']}  sitemap={c['sitemap']}  "
              f"Schema={c['schema_org']}  загрузка={c['load_time'] and round(c['load_time'],2)}с")
        t = trend_summary(c)
        if t:
            arrow = "↓" if t["change_pct"] < 0 else "↑"
            print(f"  трафик: пик {t['peak']} ({t['peak_month']}) {arrow} сейчас "
                  f"{t['current']} ({t['current_month']}) = {t['change_pct']:+d}%  [{t['source']}]")
        com = c.get("commercial") or {}
        flags = " ".join(f"{k}={'✓' if v else '✗'}" for k, v in com.items())
        print(f"  коммерч (главная): {flags}")
    if comps:
        print("  Конкуренты (по ИКС):")
        for x in sorted(data["competitors"], key=lambda z: (z.get("sqi") or 0), reverse=True):
            err = f" ⚠ {x['error']}" if x.get("error") else ""
            print(f"    {x['domain']:18} ИКС={x.get('sqi')}  Я={x.get('yandex_index')}  G={x.get('google_index')}{err}")
    print("→ audit.json, seo_benchmark.html, problem_solution.html")


if __name__ == "__main__":
    main()
