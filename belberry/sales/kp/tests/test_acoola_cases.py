"""Тесты модуля кейсов acoola.team (pure, без сети)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acoola_cases import (  # noqa: E402
    MARK_CASES_BEGIN,
    MARK_CASES_END,
    inject_cases,
    parse_cases,
    pick,
    render_cases_html,
)

KP_DIR = Path(__file__).resolve().parents[1]


def _case(title, niche="", services=(), metrics=(), summary="", url="https://acoola.team/projects/x/"):
    return {"title": title, "client": title, "url": url, "niche": niche,
            "services": list(services), "summary": summary, "metrics": list(metrics)}


CASES = [
    _case("Кофейня у дома", niche="Общепит, кофейни", services=["SMM"]),
    _case("Завод Титан", niche="Производство фурнитуры для стекла", services=["SEO"],
          metrics=[{"label": "Конверсия 8,64%", "text": "после запуска сайта"}]),
    _case("Магазин линз", niche="Розничная торговля", services=["Контекстная реклама"],
          metrics=[{"label": "ДРР", "text": "снизился с 7,3% до 3,7%"}]),
    _case("Студия дизайна", niche="Дизайн интерьеров", services=["Дизайн"]),
    _case("Музей звука", niche="Музеи и выставки", services=["SEO"],
          summary="Аудиогиды и экскурсии для музеев"),
]


# ── pick: скоринг ─────────────────────────────────────────────────────────────

def test_pick_niche_match_wins():
    top = pick("производство фурнитуры", cases=CASES)
    assert top[0]["title"] == "Завод Титан"
    assert top[0]["score"] >= 3 + 2  # ниша + цифры


def test_pick_word_forms_match():
    # «музеи» в запросе должно найти «Музеи и выставки» через нормализацию форм
    top = pick("аудиогиды экскурсии музеи", cases=CASES)
    assert top[0]["title"] == "Музей звука"


def test_pick_metrics_bonus_breaks_tie():
    a = _case("Без цифр", niche="Логистика", services=["SEO"])
    b = _case("С цифрами", niche="Логистика", services=["SEO"],
              metrics=[{"label": "ROI 140%", "text": "за год"}])
    top = pick("логистика", cases=[a, b])
    assert top[0]["title"] == "С цифрами"


def test_pick_service_weight():
    a = _case("СММ-кейс", niche="Стоматология", services=["SMM"])
    b = _case("Контекст-кейс", niche="Стоматология", services=["Контекстная реклама"])
    top = pick("стоматология", services=["smm"], cases=[a, b])
    assert top[0]["title"] == "СММ-кейс"


def test_pick_seo_priority_by_default():
    a = _case("Дизайн-кейс", niche="Недвижимость", services=["Дизайн"])
    b = _case("SEO-кейс", niche="Недвижимость", services=["SEO"])
    top = pick("недвижимость", cases=[a, b])
    assert top[0]["title"] == "SEO-кейс"


def test_pick_returns_top_three():
    assert len(pick("ниша", cases=CASES)) == 3


# ── render: HTML-фрагмент ─────────────────────────────────────────────────────

def test_render_three_tiles_with_links():
    html = render_cases_html(CASES[:3])
    assert html.count('<a class="tile') == 3
    assert 'href="https://acoola.team/projects/x/"' in html
    assert 'target="_blank"' in html
    for cls in ("tt", "tn", "tnum", "tm", "tcap"):
        assert f'class="{cls}"' in html


def test_render_no_metrics_keeps_empty_number():
    html = render_cases_html([_case("Без цифр", niche="Ниша", services=["SEO"])])
    assert '<div class="tnum"></div>' in html  # цифры не выдумываем


def test_render_escapes_html():
    bad = _case("Клиент <b>жирный</b> & co", niche='Ниша "кавычки"')
    assert "<b>" not in render_cases_html([bad]).replace('<div class="', "")


# ── parse_cases: разбор HTML индекса ─────────────────────────────────────────

SAMPLE_HTML = """
<div class="case-item --cursor"><div class="case-item__name link">
<a href="/projects/demo/" class="link">Кейс Demo: рост продаж мебели</a></div>
<div class="case-item__tag p --l">SEO</div>
<div class="case-item__info-props grid">
<div class="case-item__info-prop"><div class="case-item__info-prop-label p --xl">О проекте</div>
<div class="case-item__info-prop-desc p --l">Demo — производитель мебели.</div></div>
<div class="case-item__info-prop"><div class="case-item__info-prop-label p --xl">140%</div>
<div class="case-item__info-prop-desc p --l">ROI проекта</div></div>
</div><div class="case-item__desk p --xl">Мебель, производство</div></div>
<div class="case-item --cursor"><div class="case-item__name link">
<a href="/projects/no-digits/" class="link">Тихий кейс</a></div>
<div class="case-item__tag p --l">Дизайн</div>
<div class="case-item__info-prop"><div class="case-item__info-prop-label p --xl">Создали сайт</div>
<div class="case-item__info-prop-desc p --l">клиент доволен</div></div></div>
"""


def test_parse_cases_extracts_fields():
    cases = parse_cases(SAMPLE_HTML)
    assert len(cases) == 2
    c = cases[0]
    assert c["client"] == "Demo"
    assert c["url"] == "https://acoola.team/projects/demo/"
    assert c["niche"] == "Мебель, производство"
    assert c["services"] == ["SEO"]
    assert c["summary"] == "Demo — производитель мебели."
    assert c["metrics"] == [{"label": "140%", "text": "ROI проекта"}]


def test_parse_cases_no_digits_means_no_metrics():
    cases = parse_cases(SAMPLE_HTML)
    assert cases[1]["metrics"] == []
    assert cases[1]["summary"] == "Создали сайт клиент доволен"


# ── шаблон и вставка ─────────────────────────────────────────────────────────

def test_template_has_cases_markers():
    tpl = (KP_DIR / "templates" / "seo-acoola" / "kp.html").read_text(encoding="utf-8")
    assert MARK_CASES_BEGIN in tpl
    assert MARK_CASES_END in tpl
    assert tpl.find(MARK_CASES_BEGIN) < tpl.find(MARK_CASES_END)


def test_inject_cases_replaces_between_markers():
    html = f"до {MARK_CASES_BEGIN} заглушки {MARK_CASES_END} после"
    out, ok = inject_cases(html, "<a>плитки</a>")
    assert ok and out == "до <a>плитки</a> после"
    out2, ok2 = inject_cases("без маркеров", "<a>x</a>")
    assert not ok2 and out2 == "без маркеров"
