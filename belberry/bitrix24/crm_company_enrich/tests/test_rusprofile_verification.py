"""Тесты geo-верификации rusprofile-источника.

Покрытие (см. post-mortem ПрофиДент):
  1. geo на rusprofile = Свердловская область, bitrix_title = «ПрофиДент Екатеринбург»
     → verified (Екатеринбург matched substring).
  2. geo на rusprofile = Свердловская область / Екатеринбург,
     bitrix_title = «ПрофиДент Краснодар» → unverified.
  3. geo = Москва, web = msk-clinic.ru → verified (TLD-эвристика msk → москва).
  4. Нет geo-блока → unverified (conservative default).
  5. row.uf_inn_candidate → source="uf", verification не вызывается.
  6. row.web даёт ИНН → source="web", verification не вызывается.
"""
from __future__ import annotations

from crm_company_enrich.models import QueueRow
from crm_company_enrich.stages.enrich_web import (
    FetchResult,
    _enrich_one,
    _verify_rusprofile_match,
    extract_rusprofile_geo_tokens,
)


# ----- 1. Geo matches bitrix_title city -----


def test_rusprofile_verified_when_city_in_bitrix_title():
    html = (
        "<title>ООО Профидент — Rusprofile</title>"
        "<div class=\"company-address\">620014, Свердловская область, г. Екатеринбург, ул. Ленина, 10</div>"
        "ИНН: 6674188744"
    )

    def fetcher(url):
        if "rusprofile.ru" in url:
            return FetchResult(url=url, status=200, text=html)
        return FetchResult(url=url, status=404, text="")

    row = QueueRow(
        company_id="37342",
        company_name="ПрофиДент Екатеринбург",
        web=None,
        uf_inn_candidate=None,
    )
    inn, source, name = _enrich_one(row, fetcher, sleep_s=0)
    assert inn == "6674188744"
    assert source == "rusprofile_verified"


# ----- 2. Geo mismatch → unverified -----


def test_rusprofile_unverified_when_city_does_not_match():
    html = (
        "<title>ООО Профидент</title>"
        "<div class=\"company-address\">620014, Свердловская область, г. Екатеринбург, ул. Ленина, 10</div>"
        "ИНН: 6674188744"
    )

    def fetcher(url):
        if "rusprofile.ru" in url:
            return FetchResult(url=url, status=200, text=html)
        return FetchResult(url=url, status=404, text="")

    row = QueueRow(
        company_id="37342",
        company_name="ПрофиДент Краснодар",  # реальный bitrix-title для другого юрлица
        web=None,
        uf_inn_candidate=None,
    )
    inn, source, name = _enrich_one(row, fetcher, sleep_s=0)
    assert inn == "6674188744"
    assert source == "rusprofile_unverified"


# ----- 3. Domain TLD hint (msk → москва) -----


def test_rusprofile_verified_via_domain_hint():
    html = (
        "<title>ООО Клиника — Rusprofile</title>"
        "<div class=\"company-address\">123456, г. Москва, ул. Тверская, 1</div>"
        "ИНН: 7707083893"
    )

    def fetcher(url):
        if "rusprofile.ru" in url:
            return FetchResult(url=url, status=200, text=html)
        return FetchResult(url=url, status=404, text="")

    row = QueueRow(
        company_id="100",
        company_name="Клиника",
        web="msk-clinic.ru",
        uf_inn_candidate=None,
    )
    inn, source, _ = _enrich_one(row, fetcher, sleep_s=0)
    assert inn == "7707083893"
    assert source == "rusprofile_verified"


# ----- 4. No geo info → unverified by default -----


def test_rusprofile_unverified_when_no_geo_block():
    html = "<title>ООО Тестовая</title> ИНН: 7707083893"  # никакого адреса

    def fetcher(url):
        if "rusprofile.ru" in url:
            return FetchResult(url=url, status=200, text=html)
        return FetchResult(url=url, status=404, text="")

    row = QueueRow(
        company_id="200",
        company_name="ООО Тестовая",
        web=None,
        uf_inn_candidate=None,
    )
    inn, source, _ = _enrich_one(row, fetcher, sleep_s=0)
    assert inn == "7707083893"
    assert source == "rusprofile_unverified"


# ----- 5. UF source bypasses verification -----


def test_uf_source_skips_verification():
    row = QueueRow(
        company_id="1",
        company_name="ПрофиДент Краснодар",
        web="example.ru",
        uf_inn_candidate="7707083893",
    )

    def fetcher(url):  # pragma: no cover — не должен дёргаться
        raise AssertionError("fetcher must not be called for UF source")

    inn, source, _ = _enrich_one(row, fetcher, sleep_s=0)
    assert inn == "7707083893"
    assert source == "uf"


# ----- 6. Web source bypasses verification -----


def test_web_source_skips_verification():
    row = QueueRow(
        company_id="2",
        company_name="ПрофиДент Краснодар",
        web="example.ru",
        uf_inn_candidate=None,
    )

    def fetcher(url):
        if url.endswith("/requisites/"):
            return FetchResult(url=url, status=200, text="<title>Acme</title> ИНН: 7707083893")
        return FetchResult(url=url, status=404, text="")

    inn, source, _ = _enrich_one(row, fetcher, sleep_s=0)
    assert inn == "7707083893"
    assert source == "web"  # никакой rusprofile-verification


# ----- Direct unit tests on helpers -----


def test_extract_rusprofile_geo_tokens_finds_city_and_region():
    html = (
        "<div class=\"company-address\">"
        "620014, Свердловская область, г. Екатеринбург, ул. Ленина, 10"
        "</div>"
    )
    tokens = extract_rusprofile_geo_tokens(html)
    assert "екатеринбург" in tokens
    assert "свердловская" in tokens
    # Почтовый индекс отфильтрован
    assert "620014" not in tokens


def test_verify_match_returns_false_when_no_geo():
    assert (
        _verify_rusprofile_match(
            geo_tokens=[],
            bitrix_title="ПрофиДент Краснодар",
            web=None,
        )
        is False
    )


def test_verify_match_substring_in_title():
    assert (
        _verify_rusprofile_match(
            geo_tokens=["екатеринбург", "свердловская"],
            bitrix_title="ПрофиДент Екатеринбург",
            web=None,
        )
        is True
    )


def test_verify_match_uses_web_substring_when_geo_token_in_url():
    """web может содержать русский geo-токен (например IDN или path) — тогда match.

    Это «дешёвый» substring-чек; реальные latin-translit поддомены ловит
    TLD-эвристика _domain_geo_hints (см. test_rusprofile_verified_via_domain_hint).
    """
    assert (
        _verify_rusprofile_match(
            geo_tokens=["краснодар"],
            bitrix_title="ПрофиДент",  # geo-free
            web="example.ru/о-нас/краснодар",
        )
        is True
    )


def test_verify_match_uses_tld_hint_when_no_substring():
    """Latin поддомен msk-* → москва — обрабатывается _domain_geo_hints."""
    assert (
        _verify_rusprofile_match(
            geo_tokens=["москва", "московская"],
            bitrix_title="Клиника",
            web="msk-clinic.ru",
        )
        is True
    )
