#!/usr/bin/env python3
"""Яндекс.Вебмастер: подтверждённые данные поиска (клиент делегирует на нашу почту).

Те же OAuth-токены, что у Метрики (metrika-belberry.env / metrika-acoola.env),
НО приложению нужно право «Яндекс.Вебмастер» (webmaster:read) — без него API
отвечает ACCESS_FORBIDDEN, и стадия честно пропускается.

Что забираем: страницы в поиске / исключённые, ИКС, топ-запросы с позициями
и кликами → «быстрые победы» (запросы на 4–15 позиции с показами: до топ-3
рукой подать). Это ФАКТ Яндекса, не оценка.

    python3 webmaster_audit.py <домен>   # → webmaster.json
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from metrika_audit import TOKENS  # те же агентские аккаунты: belberry + acoola

BASE = "https://api.webmaster.yandex.net/v4"
QUICK_WIN_POS_MIN, QUICK_WIN_POS_MAX = 4, 15   # «почти в топе»
QUICK_WIN_MIN_SHOWS = 30                        # показов за неделю — есть спрос


class ScopeError(RuntimeError):
    """У OAuth-приложения нет права webmaster:read."""


def call(path: str, token: str, params: dict | None = None) -> dict:
    url = BASE + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": "OAuth " + token})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        if e.code == 403 and "ACCESS_FORBIDDEN" in body:
            raise ScopeError("у OAuth-приложения нет права webmaster:read") from e
        raise


def find_host(domain: str) -> tuple[str, str, str] | None:
    """(host_id, токен, имя_аккаунта) — перебираем оба агентских аккаунта.

    Аккаунт со старым токеном (без webmaster:verify) пропускаем молча:
    ScopeError всплывает только если НИ ОДИН аккаунт не имеет права.
    """
    needle = domain.lower().lstrip("www.")
    scope_errors = 0
    for acc, token in TOKENS:
        try:
            uid = call("/user/", token).get("user_id")
            for h in call(f"/user/{uid}/hosts", token).get("hosts", []):
                if needle in h.get("ascii_host_url", "") or needle in h.get("unicode_host_url", ""):
                    if h.get("verified"):
                        print(f"  хост найден в Вебмастере аккаунта «{acc}»")
                        return f"/user/{uid}/hosts/{h['host_id']}", token, acc
        except ScopeError:
            print(f"  аккаунт «{acc}»: токен без права Вебмастера — пропускаю")
            scope_errors += 1
    if scope_errors == len(TOKENS):
        raise ScopeError("ни один токен не имеет права webmaster:verify")
    return None


def quick_wins(queries: list[dict]) -> list[dict]:
    """Запросы на 4–15 позиции с показами — быстрые победы (pure, под тестами)."""
    out = []
    for q in queries:
        ind = q.get("indicators") or {}
        pos = ind.get("AVG_SHOW_POSITION")
        shows = ind.get("TOTAL_SHOWS") or 0
        if pos and QUICK_WIN_POS_MIN <= pos <= QUICK_WIN_POS_MAX and shows >= QUICK_WIN_MIN_SHOWS:
            out.append({"query": q.get("query_text"), "position": round(pos, 1),
                        "shows": shows, "clicks": ind.get("TOTAL_CLICKS", 0)})
    return sorted(out, key=lambda x: -x["shows"])[:10]


def render_webmaster_rows(wm: dict) -> str | None:
    """Быстрые победы → строки слайда «проблема → решение»."""
    wins = wm.get("quick_wins") or []
    if not wins:
        return None
    import html as _h
    top = wins[:3]
    qs = ", ".join(f"«{_h.escape(w['query'])}» ({w['position']})" for w in top)
    return (f'        <tr><td class="metric">Запросы у порога топа (позиции 4–15 '
            f'по Вебмастеру): {qs} — спрос есть, кликов почти нет</td>'
            f'<td>Дожимаем до топ-3: контент и перелинковка под эти запросы — '
            f'самый быстрый прирост</td></tr>')


def audit(domain: str) -> dict:
    found = find_host(domain)
    if not found:
        return {"found": False, "note": "хост не делегирован на агентские почты"}
    host_path, token, acc = found
    out: dict = {"found": True, "account": acc}
    s = call(host_path + "/summary", token)
    out["sqi"] = s.get("sqi")
    out["searchable_pages"] = s.get("searchable_pages_count")
    out["excluded_pages"] = s.get("excluded_pages_count")
    q = call(host_path + "/search-queries/popular", token, {
        "order_by": "TOTAL_SHOWS",
        "query_indicator": ["TOTAL_SHOWS", "TOTAL_CLICKS", "AVG_SHOW_POSITION"]})
    out["top_queries"] = q.get("queries", [])[:20]
    out["quick_wins"] = quick_wins(out["top_queries"])
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: webmaster_audit.py <домен>")
        return 1
    try:
        data = audit(sys.argv[1])
    except ScopeError as e:
        print(f"⚠ {e} — добавь «Яндекс.Вебмастер» в права приложения и перевыпусти токены")
        return 2
    json.dump(data, open("webmaster.json", "w"), ensure_ascii=False, indent=2)
    if data.get("found"):
        print(f"  страниц в поиске: {data.get('searchable_pages')}, "
              f"исключено: {data.get('excluded_pages')}, "
              f"быстрых побед: {len(data.get('quick_wins') or [])}")
    else:
        print(f"  {data.get('note')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
