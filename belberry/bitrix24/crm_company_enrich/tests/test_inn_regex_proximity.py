"""Регрессия Bug-3: INN regex должен требовать proximity к label ИНН/INN.

Старая жадная версия `\\b\\d{10}(\\d{2})?\\b` ловила любые 10/12-значные числа:
timestamps, ID, телефоны, мусор — и записывала их как `discovered_inn`.
"""
from __future__ import annotations

from crm_company_enrich.stages.enrich_web import (
    INN_STOPLIST,
    extract_inn_from_text,
)


def test_labeled_inn_matched():
    assert extract_inn_from_text("ИНН: 7707083893") == "7707083893"
    assert extract_inn_from_text("INN 7707083893") == "7707083893"
    assert extract_inn_from_text("Tax ID: 7707083893") == "7707083893"


def test_labeled_inn_12_digits():
    assert extract_inn_from_text("ИНН 770708389300") == "770708389300"


def test_bare_id_not_matched_without_label_and_without_requisites_url():
    # Просто 10-значное число — никакого label, никакого requisites URL.
    assert extract_inn_from_text("ID: 7707083893") is None
    assert extract_inn_from_text("user_id=7707083893 logged in") is None


def test_bare_match_allowed_on_requisites_url():
    html = "Реквизиты компании: 7707083893"
    assert (
        extract_inn_from_text(html, source_url="https://example.ru/requisites/")
        == "7707083893"
    )


def test_bare_match_allowed_on_russian_requisites_url():
    html = "Реквизиты компании: 7707083893"
    assert (
        extract_inn_from_text(html, source_url="https://example.ru/реквизиты/")
        == "7707083893"
    )


def test_bare_match_rejected_outside_requisites_url():
    html = "Здесь просто число 7707083893"
    assert (
        extract_inn_from_text(html, source_url="https://example.ru/about/")
        is None
    )


def test_repeating_digits_rejected_as_junk():
    # 1111111111 — очевидный мусор.
    assert (
        extract_inn_from_text(
            "ИНН 1111111111", source_url="https://example.ru/requisites/"
        )
        is None
    )
    assert (
        extract_inn_from_text(
            "ИНН 9999999999", source_url="https://example.ru/requisites/"
        )
        is None
    )
    # И даже на bare-fallback тоже.
    assert (
        extract_inn_from_text(
            "1111111111", source_url="https://example.ru/requisites/"
        )
        is None
    )


def test_stoplist_inn_rejected():
    # 173937695939 — fake-ИНН из инцидента enrich-web --limit 30.
    assert "173937695939" in INN_STOPLIST
    assert (
        extract_inn_from_text("ИНН 173937695939") is None
    )
    assert (
        extract_inn_from_text(
            "173937695939", source_url="https://example.ru/requisites/"
        )
        is None
    )
    # Прочие записанные в stoplist значения
    for junk in ("0000000000", "0123456789", "1234567890"):
        assert (
            extract_inn_from_text(
                f"ИНН {junk}", source_url="https://example.ru/requisites/"
            )
            is None
        )


def test_label_inn_skips_junk_and_returns_next_valid():
    # Если первый match в stoplist — продолжаем искать.
    html = "ИНН: 1111111111. Реальный ИНН: 7707083893."
    assert extract_inn_from_text(html) == "7707083893"
