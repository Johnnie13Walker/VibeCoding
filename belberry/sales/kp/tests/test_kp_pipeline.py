"""Тесты pure-функций KP-пайплайна (без сети и подпроцессов)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kp_pipeline import (  # noqa: E402
    MARK_BENCH,
    MARK_PROBLEMS,
    STAGES,
    assemble_kp_data,
    competitors_from_brief,
    domain_from_bitrix,
    inject_auto_blocks,
    plan_stages,
    traffic_dynamics,
)


# ── domain_from_bitrix ────────────────────────────────────────────────────────

def test_domain_from_site_url():
    assert domain_from_bitrix({"site": "https://med-shushary.ru/"}) == "med-shushary.ru"


def test_domain_strips_www_and_path():
    assert domain_from_bitrix({"site": "http://www.clinic.ru/about"}) == "clinic.ru"


def test_domain_falls_back_to_brief_then_title():
    bx = {"site": "", "brief": {"Адрес вашего сайта (SEO)": "brief-site.ru"}, "title": "x.ru"}
    assert domain_from_bitrix(bx) == "brief-site.ru"
    assert domain_from_bitrix({"title": "title-dom.ru"}) == "title-dom.ru"


def test_domain_ignores_non_domain_title():
    assert domain_from_bitrix({"title": "Абаев Алан LP"}) == ""


# ── competitors_from_brief ────────────────────────────────────────────────────

BRIEF_BX = {
    "site": "med-shushary.ru",
    "brief": {"Укажите список ваших основных конкурентов, ссылки на их web-сайты":
              "medi-center.ru, мир семьи, веда и feniksmed.ru; ещё www.cl-veda.ru"},
}


def test_competitors_extracts_only_domains():
    assert competitors_from_brief(BRIEF_BX) == ["medi-center.ru", "feniksmed.ru", "cl-veda.ru"]


def test_competitors_excludes_own_domain_and_dedupes():
    bx = {"site": "a.ru", "brief": {"конкуренты": "a.ru b.ru b.ru"}}
    assert competitors_from_brief(bx) == ["b.ru"]


def test_competitors_empty_brief():
    assert competitors_from_brief({"brief": {}}) == []


# ── plan_stages ───────────────────────────────────────────────────────────────

def test_plan_all_for_new_job():
    assert plan_stages({}) == STAGES


def test_plan_skips_done():
    job = {"stages": {"bitrix": {"status": "done"}, "audit": {"status": "done"}}}
    assert plan_stages(job)[0] == "metrika"


def test_plan_force_one_and_all():
    job = {"stages": {s: {"status": "done"} for s in STAGES}}
    assert plan_stages(job) == []
    assert plan_stages(job, force="audit") == ["audit"]
    assert plan_stages(job, force="all") == STAGES


def test_plan_respects_skip():
    assert "metrika" not in plan_stages({}, skip={"metrika", "prodoctorov"})


def test_plan_failed_stage_retried():
    job = {"stages": {"bitrix": {"status": "error"}}}
    assert plan_stages(job)[0] == "bitrix"


def test_plan_skipped_stage_not_rerun():
    """Стадия skipped (Метрика недоступна) не должна перезапускаться при повторе."""
    job = {"stages": {"metrika": {"status": "skipped"}}}
    assert "metrika" not in plan_stages(job)


# ── traffic_dynamics ──────────────────────────────────────────────────────────

def test_traffic_drop_real_case():
    """Кейс evromedika: пик 52500 (08.2018) → 2500 = −95%."""
    hist = {"201808": 52500, "202206": 11100, "202212": 0}
    d = traffic_dynamics(hist, current=2500)
    assert d == {"peak": 52500, "peak_month": "08.2018", "current": 2500, "drop_pct": -95}


def test_traffic_drop_ignores_zero_months_and_growth():
    assert traffic_dynamics({"202401": 0}) is None
    assert traffic_dynamics({"202401": 100}, current=200) is None  # рост — не просадка
    assert traffic_dynamics({}) is None


# ── assemble_kp_data ──────────────────────────────────────────────────────────

def test_assemble_facts_have_sources():
    data = assemble_kp_data({"deal_id": 1, "title": "x.ru", "site": "x.ru",
                             "company_revenue": 5_000_000, "brief": {}},
                            {"client": {"iks": 80}}, None, None)
    assert data["facts"], "должны быть факты"
    assert all(f["source"] for f in data["facts"]), "факт без источника недопустим"


def test_assemble_no_metrika_yields_hypothesis():
    data = assemble_kp_data({"deal_id": 1, "brief": {}}, None, None, None)
    assert any("Метрика" in h["note"] for h in data["hypotheses"])


def test_assemble_checklist_has_price_guard():
    data = assemble_kp_data(None, None, None, None)
    assert any("смет" in item.lower() for item in data["manual_checklist"])


# ── inject_auto_blocks ────────────────────────────────────────────────────────

def test_inject_replaces_markers():
    html = f"<table>{MARK_BENCH}</table><tbody>{MARK_PROBLEMS}</tbody>"
    out, missing = inject_auto_blocks(html, "<tr>B</tr>", "<tr>P</tr>")
    assert "<tr>B</tr>" in out and "<tr>P</tr>" in out and missing == []


def test_inject_reports_missing_markers():
    out, missing = inject_auto_blocks("<html></html>", "<tr>B</tr>", "<tr>P</tr>")
    assert out == "<html></html>"
    assert missing == ["seo_benchmark", "problem_solution"]


def test_inject_no_fragments_noop():
    out, missing = inject_auto_blocks("x", None, None)
    assert out == "x" and missing == []
