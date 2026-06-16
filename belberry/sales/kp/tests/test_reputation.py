"""Тесты репутационного аудита (pure, без сети)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reputation_audit import (  # noqa: E402
    aggregate, classify, render_platforms_html, render_resource_types_svg)


def test_classify_known_types():
    assert classify("prodoctorov.ru")[0] == "медагрегаторы"
    assert classify("2gis.ru")[0] == "гео-сервисы"
    assert classify("otzovik.com")[0] == "отзовики"
    assert classify("vk.com")[0] == "соцсети"
    assert classify("spb.napopravku.ru")[0] == "медагрегаторы"  # поддомен
    assert classify("unknown-site.ru")[0] == "прочее"
    assert classify("ria.ru")[0] == "СМИ"


def test_aggregate_counts_and_names():
    results = [
        ("prodoctorov.ru", "https://prodoctorov.ru/x", "ПроДокторов — отзывы"),
        ("2gis.ru", "https://2gis.ru/x", "2ГИС"),
        ("otzovik.com", "https://otzovik.com/x", "Otzovik"),
    ]
    d = aggregate(results, "Клиника N", "Москва", own_domain="")
    assert d["found"] and len(d["platforms"]) == 3
    assert d["type_counts"] == {"гео-сервисы": 1, "медагрегаторы": 1, "отзовики": 1}
    assert d["prodoctorov_url"] == "https://prodoctorov.ru/x"
    assert d["query"] == "Клиника N отзывы Москва"


def test_aggregate_excludes_own_domain():
    results = [
        ("clinic.ru", "https://clinic.ru", "Главная"),
        ("www.clinic.ru", "https://www.clinic.ru/reviews", "Отзывы"),
        ("otzovik.com", "https://otzovik.com/x", "Otzovik"),
    ]
    d = aggregate(results, "Клиника", "", own_domain="clinic.ru")
    domains = [p["domain"] for p in d["platforms"]]
    assert "clinic.ru" not in domains and "www.clinic.ru" not in domains
    assert domains == ["otzovik.com"]


def test_aggregate_empty():
    d = aggregate([], "X", "")
    assert d["found"] is False and d["platforms"] == [] and d["type_counts"] == {}
    assert d["prodoctorov_url"] is None


def test_render_resource_types_svg():
    data = {"type_counts": {"гео-сервисы": 2, "медагрегаторы": 4, "отзовики": 3}}
    svg = render_resource_types_svg(data, accent="#6B5AF9")
    assert svg.startswith("<svg") and "#6B5AF9" in svg
    assert ">4<" in svg and "медагрегаторы" in svg
    assert render_resource_types_svg({"type_counts": {}}) is None


def test_render_platforms_html():
    data = {"platforms": [
        {"name": "ПроДокторов", "type": "медагрегаторы", "domain": "prodoctorov.ru"},
        {"name": "2ГИС", "type": "гео-сервисы", "domain": "2gis.ru"}]}
    html = render_platforms_html(data, accent="#6B5AF9")
    assert "ПроДокторов" in html and "медагрегаторы" in html and "#6B5AF9" in html
    assert render_platforms_html({"platforms": []}) is None
