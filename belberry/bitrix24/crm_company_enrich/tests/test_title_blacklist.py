"""Регрессия Bug-2: TITLE-as-domain не должен срабатывать для плейсхолдеров Bitrix.

В портале belberrycrm у ~30 компаний TITLE = дефолт "Битрикс24 помогает бизнесу работать".
Старый _enrich_one пытался normalize_domain() этого мусора, получал что-то
ненулевое и фетчил левый сайт — это привело к одинаковому фейковому ИНН
у 30 разных компаний.
"""
from __future__ import annotations

from crm_company_enrich.models import QueueRow
from crm_company_enrich.stages.enrich_web import (
    FetchResult,
    _enrich_one,
    _is_safe_domain_candidate,
)


def _fail_fetcher(url):
    raise AssertionError(f"fetcher не должен вызываться, но был вызван: {url}")


def test_bitrix_default_placeholder_does_not_trigger_title_fallback():
    row = QueueRow(
        company_id="1",
        company_name="Битрикс24 помогает бизнесу работать",
        web=None,
        uf_inn_candidate=None,
    )
    # Без web и без uf — title→domain должен быть заблокирован, rusprofile
    # тоже пускаем, но фетчер настроен на провал. Здесь мы проверяем именно
    # отсутствие "title"-source: для этого подменяем fetcher на «всегда 404».
    inn, source, _ = _enrich_one(
        row,
        lambda url: FetchResult(url=url, status=404, text=""),
        sleep_s=0,
    )
    assert inn is None
    assert source is None


def test_placeholder_variants_blocked():
    # Самые частые мусорные TITLE — не пытаемся фетчить их как домен.
    titles = [
        "Битрикс24 помогает бизнесу работать",
        "Новая компания",
        "Без названия",
        "ID 12345",
        "placeholder",
    ]
    for title in titles:
        row = QueueRow(
            company_id="x", company_name=title, web=None, uf_inn_candidate=None,
        )

        # Если TITLE-blacklist пропустит — fetcher либо вообще не позовут
        # (нужный кейс), либо позовут rusprofile с 404 → None.
        def fetcher(url):
            # Любой fetch на title-as-domain заглушаем 404; rusprofile тоже 404.
            return FetchResult(url=url, status=404, text="")

        inn, source, _ = _enrich_one(row, fetcher, sleep_s=0)
        assert inn is None
        assert source is None


def test_safe_domain_candidate_rejects_noise():
    # Если бы normalize_domain что-то и вернул, фильтр обязан срезать мусор.
    assert _is_safe_domain_candidate(None) is False
    assert _is_safe_domain_candidate("") is False
    assert _is_safe_domain_candidate("foo bar.ru") is False  # пробелы
    assert _is_safe_domain_candidate("a" * 70 + ".ru") is False  # слишком длинно
    assert _is_safe_domain_candidate("noTLD") is False
    assert _is_safe_domain_candidate("example.zzzzz") is False  # 5-буквенный TLD не в whitelist
    # Реальные домены — ок
    assert _is_safe_domain_candidate("example.ru") is True
    assert _is_safe_domain_candidate("example.com") is True
    assert _is_safe_domain_candidate("example.рф") is True


def test_real_title_with_domain_still_works():
    # Если в TITLE есть честный домен, fallback должен сработать.
    row = QueueRow(
        company_id="2",
        company_name="example.ru",
        web=None,
        uf_inn_candidate=None,
    )

    def fetcher(url):
        # На /requisites/ возвращаем ИНН с label.
        if "/requisites/" in url:
            return FetchResult(url=url, status=200, text="ИНН: 7707083893")
        return FetchResult(url=url, status=404, text="")

    inn, source, _ = _enrich_one(row, fetcher, sleep_s=0)
    assert inn == "7707083893"
    assert source == "title"
