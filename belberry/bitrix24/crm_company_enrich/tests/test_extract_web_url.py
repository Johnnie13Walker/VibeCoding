"""Регрессия Bug-1: extract_web_url должен парсить REST-формат list[dict].

Боевой инцидент: API возвращал WEB как
    [{"ID": "...", "VALUE": "https://example.ru", "VALUE_TYPE": "WORK"}, ...]
а старая реализация писала в Sheets обрезанный str() — `"[{'ID': '863890'"`.
"""
from __future__ import annotations

from crm_company_enrich.models import extract_web_url


def test_list_of_dict_single_value():
    web = [{"ID": "1", "VALUE": "https://example.ru", "VALUE_TYPE": "WORK"}]
    assert extract_web_url(web) == "https://example.ru"


def test_list_of_dict_returns_first_non_empty():
    web = [
        {"ID": "1", "VALUE": "https://first.ru", "VALUE_TYPE": "WORK"},
        {"ID": "2", "VALUE": "https://second.ru", "VALUE_TYPE": "HOME"},
    ]
    assert extract_web_url(web) == "https://first.ru"


def test_list_of_dict_skips_empty_value():
    web = [
        {"ID": "1", "VALUE": "", "VALUE_TYPE": "WORK"},
        {"ID": "2", "VALUE": "https://second.ru", "VALUE_TYPE": "HOME"},
    ]
    assert extract_web_url(web) == "https://second.ru"


def test_list_of_dict_url_alias():
    web = [{"URL": "https://aliased.ru"}]
    assert extract_web_url(web) == "https://aliased.ru"


def test_legacy_string_format():
    assert extract_web_url("https://foo.ru|WORK") == "https://foo.ru"


def test_legacy_multi_line_string():
    assert (
        extract_web_url("https://foo.ru|WORK\nhttps://bar.ru|HOME")
        == "https://foo.ru"
    )


def test_dict_format():
    assert extract_web_url({"VALUE": "https://x.com"}) == "https://x.com"


def test_dict_url_alias():
    assert extract_web_url({"URL": "https://y.com"}) == "https://y.com"


def test_none_returns_none():
    assert extract_web_url(None) is None


def test_empty_string_returns_none():
    assert extract_web_url("") is None


def test_empty_list_returns_none():
    assert extract_web_url([]) is None


def test_list_of_empty_dicts_returns_none():
    assert extract_web_url([{}]) is None


def test_list_of_dicts_with_only_empty_values_returns_none():
    assert extract_web_url([{"VALUE": ""}, {"VALUE": "   "}]) is None
