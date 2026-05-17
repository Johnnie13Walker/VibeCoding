"""Тесты regex-парсинга ИНН из HTML-ответа web-сайта.

Не делает реальных HTTP-вызовов — только проверяет extract_inn_from_text
и behaviour _enrich_one через подменённый FetcherFn.
"""
from __future__ import annotations

from crm_company_enrich.models import QueueRow
from crm_company_enrich.stages.enrich_web import (
    FetchResult,
    extract_company_name_from_html,
    extract_inn_from_text,
    _enrich_one,
)


# ----- extract_inn_from_text -----

def test_extract_inn_labeled_classic():
    html = "<p>ИНН: 7707083893</p>"
    assert extract_inn_from_text(html) == "7707083893"


def test_extract_inn_labeled_english():
    html = "INN 7707083893"
    assert extract_inn_from_text(html) == "7707083893"


def test_extract_inn_labeled_html_nbsp_entity():
    html = "ООО Фирма «Феррум» ИНН&nbsp;2614018356, ОГРН&nbsp;1032600181569"
    assert extract_inn_from_text(html) == "2614018356"


def test_extract_inn_12_digit():
    html = "<div>ИНН 770708389300</div>"
    assert extract_inn_from_text(html) == "770708389300"


def test_extract_inn_bare_requires_requisites_url():
    # Без label и без requisites-URL — bare-число игнорируется.
    html = "Реквизиты компании 7707083893 и контакты"
    assert extract_inn_from_text(html) is None
    # На странице /requisites/ — bare-число принимается.
    assert (
        extract_inn_from_text(html, source_url="https://example.ru/requisites/")
        == "7707083893"
    )


def test_extract_inn_ignores_phone_like_numbers():
    html = "Тел: +7 (495) 1234567890 круглосуточно"
    # 1234567890 окружено пунктуацией от телефона → должен пропустить
    assert extract_inn_from_text(html) is None


def test_extract_inn_returns_first_valid():
    html = "Старый ИНН: 7707083893\nНовый ИНН: 770708389300"
    # labeled regex захватывает первый match
    assert extract_inn_from_text(html) == "7707083893"


def test_extract_inn_returns_none_when_no_inn():
    html = "<html><body>Нет ИНН здесь</body></html>"
    assert extract_inn_from_text(html) is None


def test_extract_inn_empty_input():
    assert extract_inn_from_text("") is None
    assert extract_inn_from_text(None) is None  # type: ignore[arg-type]


def test_extract_company_name_from_html():
    html = "<html><head><title>ООО Ромашка — официальный сайт</title></head></html>"
    assert extract_company_name_from_html(html) == "ООО Ромашка — официальный сайт"


def test_extract_company_name_returns_none_when_no_title():
    assert extract_company_name_from_html("<html></html>") is None


# ----- _enrich_one with mocked fetcher -----

def test_enrich_one_uses_uf_first():
    row = QueueRow(company_id="1", web="example.ru", uf_inn_candidate="7707083893")

    def fail_fetcher(url):
        raise AssertionError("fetcher must not be called when UF candidate is valid")

    inn, source, name = _enrich_one(row, fail_fetcher, sleep_s=0)
    assert inn == "7707083893"
    assert source == "uf"


def test_enrich_one_falls_back_to_web():
    row = QueueRow(company_id="2", web="example.ru", uf_inn_candidate=None)

    fetched: list[str] = []

    def fetcher(url):
        fetched.append(url)
        if url.endswith("/requisites/"):
            return FetchResult(url=url, status=200, text="<title>Acme</title> ИНН: 7707083893")
        return FetchResult(url=url, status=404, text="")

    inn, source, name = _enrich_one(row, fetcher, sleep_s=0)
    assert inn == "7707083893"
    assert source == "web"
    assert name == "Acme"
    # должны были обойти как минимум первые два URL
    assert any("/requisites/" in u for u in fetched)


def test_enrich_one_returns_none_when_all_sources_fail():
    row = QueueRow(company_id="3", web="example.ru")

    def fetcher(url):
        return FetchResult(url=url, status=200, text="<title>No INN here</title>")

    inn, source, name = _enrich_one(row, fetcher, sleep_s=0)
    assert inn is None
    assert source is None


def test_enrich_one_skips_invalid_uf_falls_to_web():
    row = QueueRow(company_id="4", web="example.ru", uf_inn_candidate="not-an-inn")

    def fetcher(url):
        return FetchResult(url=url, status=200, text="ИНН 770708389300")

    inn, source, name = _enrich_one(row, fetcher, sleep_s=0)
    assert inn == "770708389300"
    assert source == "web"


def test_enrich_one_title_as_domain():
    row = QueueRow(
        company_id="5",
        company_name="example.ru",
        web=None,
        uf_inn_candidate=None,
    )

    calls: list[str] = []

    def fetcher(url):
        calls.append(url)
        return FetchResult(url=url, status=200, text="ИНН 7707083893")

    inn, source, _ = _enrich_one(row, fetcher, sleep_s=0)
    assert inn == "7707083893"
    assert source == "title"
    assert any("example.ru" in u for u in calls)


def test_enrich_one_rusprofile_fallback():
    row = QueueRow(company_id="6", company_name="ООО Тестовая", web=None, uf_inn_candidate=None)

    def fetcher(url):
        if "rusprofile.ru" in url:
            return FetchResult(url=url, status=200, text="<title>ООО Тестовая</title> ИНН: 7707083893")
        return FetchResult(url=url, status=404, text="")

    inn, source, name = _enrich_one(row, fetcher, sleep_s=0)
    assert inn == "7707083893"
    # Без geo-блока в HTML rusprofile-карточки совпадение не подтверждено →
    # помечаем источник как unverified (см. _verify_rusprofile_match).
    assert source == "rusprofile_unverified"
