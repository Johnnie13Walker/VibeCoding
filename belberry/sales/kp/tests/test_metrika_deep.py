"""Тесты пороговых функций глубокого аудита Метрики (без сети).

Каждая функция получает готовые числа и возвращает проблему/None —
проверяем оба исхода: пороги превышены и не превышены.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from metrika_audit import (  # noqa: E402
    problem_from_devices,
    problem_from_geo,
    problem_from_organic_trend,
    problem_from_search_engines,
    problem_from_source_conversion,
    problems_from_pages,
    render_problems_html,
    trend_stats,
)


# ── trend_stats ───────────────────────────────────────────────────────────────

def _months(values, first_partial=False, last_partial=True):
    out = [{"month": f"2026-{i + 1:02d}", "visits": v, "partial": False}
           for i, v in enumerate(values)]
    if out and first_partial:
        out[0]["partial"] = True
    if out and last_partial:
        out[-1]["partial"] = True
    return out


def test_trend_stats_peak_current_direction_fall():
    t = trend_stats(_months([1000, 900, 700, 500, 100]))  # последний partial
    assert t["peak"] == 1000 and t["peak_month"] == "2026-01"
    assert t["current"] == 500 and t["current_month"] == "2026-04"
    assert t["change_pct"] == -50.0
    assert t["direction"] == "падение"


def test_trend_stats_growth_and_flat():
    assert trend_stats(_months([100, 150, 200, 10]))["direction"] == "рост"
    assert trend_stats(_months([200, 205, 198, 10]))["direction"] == "стабильно"


def test_trend_stats_ignores_partial_months():
    t = trend_stats(_months([9999, 500, 600, 9999], first_partial=True))
    assert t["peak"] == 600  # края-обрезки не считаются пиком/текущим
    assert t["current"] == 600


def test_trend_stats_empty():
    t = trend_stats([])
    assert t["peak"] is None and t["direction"] is None


# ── органика: падение тренда ─────────────────────────────────────────────────

def test_organic_trend_drop_detected():
    p = problem_from_organic_trend({"peak": 1500, "peak_month": "2026-02",
                                    "current": 600, "current_month": "2026-05"})
    assert p is not None
    assert p["evidence"]["drop_pct"] == 60
    assert "1500" in p["fact"] and "600" in p["fact"]


def test_organic_trend_no_drop():
    assert problem_from_organic_trend({"peak": 1500, "peak_month": "2026-02",
                                       "current": 1400, "current_month": "2026-05"}) is None


def test_organic_trend_too_little_data():
    # пик ниже минимума визитов — вывод не делаем
    assert problem_from_organic_trend({"peak": 50, "peak_month": "2026-02",
                                       "current": 10, "current_month": "2026-05"}) is None


def test_organic_trend_peak_is_current_month():
    assert problem_from_organic_trend({"peak": 1000, "peak_month": "2026-05",
                                       "current": 1000, "current_month": "2026-05"}) is None


# ── страницы-дыры ────────────────────────────────────────────────────────────

def test_pages_flagged_above_thresholds():
    pages = [
        {"page": "/", "visits": 500, "bounce_rate": 15.0},
        {"page": "/rent", "visits": 200, "bounce_rate": 40.0},   # дыра: >20×1.4 и 20%
        {"page": "/tiny", "visits": 10, "bounce_rate": 90.0},    # доля 1% — не считается
    ]
    probs = problems_from_pages(pages, site_bounce=20.0, total_visits=1000)
    assert len(probs) == 1
    assert probs[0]["evidence"]["page"] == "/rent"
    assert pages[1]["problem"] is True
    assert pages[0]["problem"] is False and pages[2]["problem"] is False


def test_pages_none_flagged_when_bounce_normal():
    pages = [{"page": "/", "visits": 500, "bounce_rate": 22.0}]
    assert problems_from_pages(pages, site_bounce=20.0, total_visits=1000) == []


def test_pages_capped_at_three():
    pages = [{"page": f"/p{i}", "visits": 100, "bounce_rate": 80.0 + i}
             for i in range(5)]
    probs = problems_from_pages(pages, site_bounce=20.0, total_visits=1000)
    assert len(probs) == 3
    assert probs[0]["evidence"]["page"] == "/p4"  # худшая первой


# ── мобильные против десктопа ────────────────────────────────────────────────

def test_devices_problem_detected():
    p = problem_from_devices(580, 31.0, 400, 12.0, 1000)
    assert p is not None
    assert p["evidence"] == {"mobile_share": 58, "mobile_bounce": 31.0,
                             "desktop_bounce": 12.0}


def test_devices_ok_when_share_small():
    # отказы выше, но мобильных всего 20% — не проблема
    assert problem_from_devices(200, 31.0, 700, 12.0, 1000) is None


def test_devices_ok_when_bounce_close():
    # доля большая, но отказы в пределах ×1.4
    assert problem_from_devices(580, 15.0, 400, 12.0, 1000) is None


# ── Яндекс против Google ─────────────────────────────────────────────────────

def test_search_engines_skew_detected():
    p = problem_from_search_engines(yandex_visits=150, google_visits=850,
                                    organic_visits=1000)
    assert p is not None
    assert p["evidence"]["yandex_share"] == 15
    assert "Яндекс" in p["fact"]


def test_search_engines_balanced_ok():
    assert problem_from_search_engines(400, 600, 1000) is None


def test_search_engines_low_traffic_skipped():
    assert problem_from_search_engines(5, 90, 95) is None


# ── конверсия по источникам ──────────────────────────────────────────────────

def test_source_conversion_problem_detected():
    p = problem_from_source_conversion(organic_conv=0.4, ad_conv=2.0,
                                       organic_visits=2000, ad_visits=3000,
                                       goal_name="Отправка формы")
    assert p is not None
    assert p["evidence"]["organic_conversion"] == 0.4
    assert "Отправка формы" in p["fact"]


def test_source_conversion_ok_when_comparable():
    assert problem_from_source_conversion(1.5, 2.0, 2000, 3000, "Цель") is None


def test_source_conversion_skipped_on_low_traffic():
    assert problem_from_source_conversion(0.1, 2.0, 50, 3000, "Цель") is None
    assert problem_from_source_conversion(0.1, 2.0, 2000, 50, "Цель") is None


# ── география ────────────────────────────────────────────────────────────────

GEO = [
    {"region": "Санкт-Петербург и Ленинградская область", "visits": 300},
    {"region": "Москва и Московская область", "visits": 500},
    {"region": "Not specified", "visits": 999},  # не учитывается
    {"region": "Калининградская область", "visits": 200},
]


def test_geo_nontarget_detected():
    p = problem_from_geo(GEO, "Санкт-Петербург")
    assert p is not None
    assert p["evidence"]["nontarget_share"] == 70  # (500+200)/1000
    assert p["evidence"]["known_region_visits"] == 1000


def test_geo_ok_when_mostly_target():
    p = problem_from_geo([{"region": "Москва и Московская область", "visits": 900},
                          {"region": "Тверская область", "visits": 100}], "Москва")
    assert p is None


def test_geo_skipped_without_target_region():
    assert problem_from_geo(GEO, None) is None


def test_geo_skipped_when_target_matches_no_visits():
    """biospaclinic 17.06: битый/плейсхолдерный таргет даёт share=100% → не вывод
    для клиента (реальный целевой регион всегда даёт часть своего трафика)."""
    assert problem_from_geo(GEO, "Пришлют информацию") is None


# ── render_problems_html ─────────────────────────────────────────────────────

def test_render_problems_html_format():
    html = render_problems_html([
        {"fact": "Факт с цифрой 58%", "evidence": {"x": 58},
         "so_what": "Половина трафика уходит", "action": "Чиним вёрстку"},
    ])
    assert html.startswith('        <tr><td class="metric">')
    assert "Факт с цифрой 58% — половина трафика уходит" in html
    assert "<td>Чиним вёрстку</td></tr>" in html


def test_render_problems_html_empty():
    assert render_problems_html([]) == ""
