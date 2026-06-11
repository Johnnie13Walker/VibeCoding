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


# ── pick_brief (bitrix_audit) ─────────────────────────────────────────────────

from bitrix_audit import SVC_SEO, pick_brief  # noqa: E402


def test_pick_brief_prefers_seo_service():
    """zn48-кейс: контекст(2726) + два SEO(2730) → свежий SEO-бриф."""
    briefs = [{"id": 1388, "ufCrm20_1753290430": [2726]},
              {"id": 1390, "ufCrm20_1753290430": [2730]},
              {"id": 1484, "ufCrm20_1753290430": [2730]}]
    assert pick_brief(briefs)["id"] == 1484


def test_pick_brief_falls_back_to_latest_any():
    briefs = [{"id": 10, "ufCrm20_1753290430": [2726]},
              {"id": 20, "ufCrm20_1753290430": 2734}]
    assert pick_brief(briefs)["id"] == 20


def test_pick_brief_scalar_service_value():
    briefs = [{"id": 5, "ufCrm20_1753290430": SVC_SEO}, {"id": 9, "ufCrm20_1753290430": [2726]}]
    assert pick_brief(briefs)["id"] == 5


# ── золотой шаблон ────────────────────────────────────────────────────────────

def test_golden_template_has_markers():
    tpl = Path(__file__).resolve().parents[1] / "templates" / "seo-belberry" / "kp.html"
    html = tpl.read_text(encoding="utf-8")
    assert MARK_BENCH in html and MARK_PROBLEMS in html


def test_acoola_template_has_markers_and_no_med():
    tpl = Path(__file__).resolve().parents[1] / "templates" / "seo-acoola" / "kp.html"
    html = tpl.read_text(encoding="utf-8")
    assert MARK_BENCH in html and MARK_PROBLEMS in html
    for word in ("пациент", "клиник", "ПроДокторов", "5b50d6"):
        assert word not in html, f"мед-след в acoola-шаблоне: {word}"


def test_no_kpi_guarantee_in_templates():
    """Решение заказчика 10.06: KPI с клиентами НЕТ — в шаблонах не обещаем."""
    base = Path(__file__).resolve().parents[1] / "templates"
    for tpl in ("seo-belberry", "seo-acoola", "program-belberry"):
        html = (base / tpl / "kp.html").read_text(encoding="utf-8")
        assert "KPI и гарантия результата" not in html, tpl
        assert "ответственность за результат" not in html, tpl


def test_pick_template_by_brand():
    from kp_pipeline import pick_template
    assert pick_template("belberry").name == "seo-belberry"
    assert pick_template("acoola").name == "seo-acoola"
    assert pick_template("несуществующий").name == "med-shushary"


# ── автозаполнение деки и смета по брифу ─────────────────────────────────────

from kp_pipeline import (  # noqa: E402
    MARK_TRAFFIC,
    deck_substitutions,
    preset_for_brief,
    render_traffic_drop,
)


def test_preset_for_brief_maps_services():
    assert preset_for_brief([2730]) == "seo"
    assert preset_for_brief([2722, 2738]) == "program"  # Дзен незнаком → техподдержка
    assert preset_for_brief([2726]) == "ppc"
    assert preset_for_brief([]) == "seo"
    assert preset_for_brief(None) == "seo"


def test_deck_substitutions_only_known_facts():
    data = {"domain": "x.ru", "facts": [
        {"key": "deal_title", "value": "x.ru", "source": "s", "status": "факт"},
        {"key": "brief:Регион продвижения", "value": "СПб", "source": "s", "status": "факт"},
    ]}
    subs = deck_substitutions(data, "11.06.2026")
    assert subs["{{ДОМЕН}}"] == "x.ru" and subs["{{ГОРОД}}"] == "СПб"
    assert subs["{{ДАТА}}"] == "11.06.2026"
    assert "{{ПРИОРИТЕТНЫЕ_УСЛУГИ}}" not in subs  # неизвестное не подставляем


def test_render_traffic_drop_builds_banner():
    data = {"facts": [{"key": "traffic_drop", "source": "s", "status": "факт",
                       "value": "пик 66500 (05.2024) → сейчас 16500 = -75%"}]}
    html = render_traffic_drop(data)
    assert "-75%" in html and "66500" in html
    assert render_traffic_drop({"facts": []}) is None


def test_templates_have_traffic_marker():
    base = Path(__file__).resolve().parents[1] / "templates"
    for tpl in ("seo-belberry", "seo-acoola"):
        assert MARK_TRAFFIC in (base / tpl / "kp.html").read_text(encoding="utf-8"), tpl


# ── интеграция: ниша для кейсов и объединение проблем ────────────────────────

from kp_pipeline import combine_problem_rows, niche_text_from_bitrix  # noqa: E402


def test_niche_text_from_bitrix():
    bx = {"sfera": "Производство",
          "brief": {"Приоритетные товары/услуги, которые нужно продвигать": "аудиогиды",
                    "Что представляет собой продукт (товар, услуга или компания)?": "радиогиды"}}
    assert niche_text_from_bitrix(bx) == "Производство аудиогиды радиогиды"
    assert niche_text_from_bitrix({}) == ""


def test_combine_problem_rows():
    assert combine_problem_rows("<tr>a</tr>", "<tr>b</tr>") == "<tr>a</tr>\n<tr>b</tr>"
    assert combine_problem_rows(None, "<tr>b</tr>") == "<tr>b</tr>"
    assert combine_problem_rows("", None) is None


# ── подписи брифа гуляют + зачистка плейсхолдеров (баг crystal-sound 11.06) ──

from kp_pipeline import brief_pick, scrub_placeholders  # noqa: E402


def test_brief_pick_by_prefix():
    """crystal-sound: поле называлось «Приоритетные услуги или направления»."""
    facts = {"brief:Приоритетные услуги или направления": "радиогиды",
             "brief:Регион продвижения": "СПб"}
    assert brief_pick(facts, "Приоритетные") == "радиогиды"
    assert brief_pick(facts, "Регион") == "СПб"
    assert brief_pick(facts, "Несуществующий") is None


def test_deck_substitutions_handles_label_variants():
    data = {"domain": "x.ru", "facts": [
        {"key": "brief:Приоритетные услуги или направления", "value": "радиогиды",
         "source": "s", "status": "факт"}]}
    assert deck_substitutions(data, "11.06.2026")["{{ПРИОРИТЕТНЫЕ_УСЛУГИ}}"] == "радиогиды"


def test_scrub_placeholders_cleans_with_separator():
    html = "<p>заявок из поиска: {{ПРИОРИТЕТНЫЕ_УСЛУГИ}}.</p><b>{{ГЕО}}</b>"
    out, left = scrub_placeholders(html)
    assert left == 2
    assert "{{" not in out
    assert "заявок из поиска</p>" in out


def test_scrub_noop_when_clean():
    out, left = scrub_placeholders("<p>чисто</p>")
    assert left == 0 and out == "<p>чисто</p>"


# ── слайд «Что мешает» из реальных данных (баг: med-shushary-цифры) ──────────

from kp_pipeline import MARK_BLOCKERS, render_blockers_html  # noqa: E402

AUDIT_FX = {"client": {"sqi": 270, "yandex_index": 309, "google_index": 301,
                       "donors": 12, "schema_org": True, "load_time": 0.5,
                       "robots": True, "sitemap": True},
            "competitors": [{"domain": "cromi.ru", "sqi": 170}]}


def test_blockers_only_real_facts():
    html = render_blockers_html(AUDIT_FX, None, None)
    assert "12" in html and "Внешних ссылок" in html
    # ИКС 270 ВЫШЕ конкурента — пункта про отставание быть не должно
    assert "ИКС 270" not in html
    # индексация 309/301 сбалансирована — пункта нет
    assert "дисбаланс" not in html
    # med-shushary-чисел нет по построению
    for ghost in ("ИКС 80", "130", "354", "−45%"):
        assert ghost not in html


def test_blockers_metrika_and_pains():
    mt = {"problems": [{"fact": "Страница /rent собирает 10% трафика, отказы 40.8%"}],
          "source_conversion": [
              {"source": "Переходы по рекламе", "visits": 8598, "conversion": 0.65},
              {"source": "Переходы из поисковых систем", "visits": 4745, "conversion": 1.41}]}
    ins = {"pains": [{"pain": "SEO занимались минимально"}], "site_issues": [
        {"issue": "УТП не на главной", "evidence": "нет блока отличий"}]}
    html = render_blockers_html(AUDIT_FX, mt, ins)
    assert "/rent" in html and "0.65%" in html and "1.41%" in html
    assert "УТП не на главной" in html and "из разбора встречи" in html


def test_blockers_empty_data_none():
    assert render_blockers_html(None, None, None) is None


def test_templates_have_blockers_marker():
    base = Path(__file__).resolve().parents[1] / "templates"
    for tpl in ("seo-belberry", "seo-acoola"):
        s = (base / tpl / "kp.html").read_text(encoding="utf-8")
        assert MARK_BLOCKERS in s, tpl
        # шаблонных цифр-образцов в слайде «Что мешает» больше нет
        i = s.find("Что сейчас мешает")
        chunk = s[i:s.find("</section>", i)]
        assert "ИКС 80" not in chunk and "354" not in chunk
