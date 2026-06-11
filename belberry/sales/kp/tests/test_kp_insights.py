"""Тесты смыслового слоя (pure, без сети и LLM)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kp_insights import (  # noqa: E402
    build_prompt,
    parse_insights,
    pick_inner_links,
    render_pains_html,
    render_site_rows,
)


def test_build_prompt_sections():
    bx = {"brief": {"УТП": "только мы"}, "transcript": "Клиент: дорого. " * 10}
    p = build_prompt(bx, {"https://x.ru/": "текст главной"})
    assert "БРИФ" in p and "ТРАНСКРИПТ" in p and "СТРАНИЦА САЙТА" in p


def test_build_prompt_truncates_transcript():
    bx = {"brief": {}, "transcript": "х" * 50_000}
    assert len(build_prompt(bx, {})) < 20_000


def test_parse_insights_strict_and_wrapped():
    raw = '```json\n{"pains": [{"pain": "p", "quote": "q", "source": "бриф"}],' \
          ' "site_issues": [], "key_argument": "a", "next_step": "n"}\n```'
    d = parse_insights(raw)
    assert d["pains"][0]["pain"] == "p" and d["site_issues"] == []


def test_parse_insights_no_json_raises():
    import pytest
    with pytest.raises(ValueError):
        parse_insights("модель ответила прозой")


def test_pick_inner_links_filters_and_limits():
    home = ('<a href="/uslugi/seo">a</a><a href="/about">b</a>'
            '<a href="https://other.site/x">c</a><a href="/price">d</a>'
            '<a href="/blog/post1">e</a>')
    links = pick_inner_links(home, "x.ru", limit=2)
    assert links == ["https://x.ru/uslugi/seo", "https://x.ru/about"]


def test_render_pains_escapes_and_marks_source():
    html = render_pains_html({"pains": [
        {"pain": "<b>дорого</b>", "quote": "нам дорого", "source": "встреча"}],
        "key_argument": "аргумент"})
    assert "&lt;b&gt;" in html and "встреча" in html and "ГЛАВНЫЙ АРГУМЕНТ" in html
    assert render_pains_html({"pains": []}) is None


def test_render_site_rows_format():
    rows = render_site_rows({"site_issues": [
        {"issue": "нет цен", "evidence": "на /price пусто", "action": "добавить прайс"}]})
    assert '<td class="metric">' in rows and "добавить прайс" in rows
    assert render_site_rows({"site_issues": []}) is None
