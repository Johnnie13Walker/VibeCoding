"""Regression-тесты очистки company_name перед отправкой в crm.requisite.add.

discovered_name приходит из enrich-web (HTML-title rusprofile / сайта компании)
и часто содержит SEO-хвосты («- результаты поиска на Rusprofile.ru»,
«(ИНН ...) адрес, официальный сайт и телефон»), HTML-entities (&quot;) и
HTML-title trail после ` | `. clean_company_name_for_requisite их снимает;
интеграционный тест проверяет, что apply действительно использует чистое
значение в RQ_COMPANY_NAME_FULL.
"""
from __future__ import annotations

import pytest

from crm_company_enrich.models import QueueRow, TargetAction, clean_company_name_for_requisite
from crm_company_enrich.stages import apply
from crm_company_enrich.state import Status

from .test_apply_create_req import FakeBitrix, FakeSheets


# =========================================================================
# Unit-тесты helper'а
# =========================================================================


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Rusprofile SEO-хвост
        (
            "ПрофиДент, стоматологическая клиника - результаты поиска на Rusprofile.ru",
            "ПрофиДент, стоматологическая клиника",
        ),
        (
            "Республиканская Стоматологическая Поликлиника - результаты поиска на Rusprofile.ru",
            "Республиканская Стоматологическая Поликлиника",
        ),
        (
            "Жемчужина, стоматологическая клиника - результаты поиска на Rusprofile.ru",
            "Жемчужина, стоматологическая клиника",
        ),
        # HTML-entities + «(ИНН ...) адрес, официальный сайт и телефон»
        (
            'ООО &quot;Вивасмайл&quot; Москва (ИНН 9702014360) адрес, официальный сайт и телефон',
            'ООО "Вивасмайл" Москва',
        ),
        # HTML-title trail после ` | `
        (
            "Стоматология в Сколково, Одинцово, Трехгорке | Ecodent - Экодент клиника",
            "Стоматология в Сколково, Одинцово, Трехгорке",
        ),
        # Неидеально, но безопасно: режем всё после ` | `
        ("Контакты | клиника Effi в Красноярске", "Контакты"),
        # Already-clean — без изменений
        ("ООО Ромашка", "ООО Ромашка"),
        # &amp; → &
        ("ООО &amp; Co", "ООО & Co"),
        # Сжатие whitespace
        ("  лишние   пробелы  ", "лишние пробелы"),
        # Пустота
        ("", None),
        (None, None),
        # Слишком короткое после чистки → None
        ("a", None),
        # Placeholder не должен резаться этим helper'ом (фильтр placeholder'ов
        # живёт на уровне enrich-web; здесь только структурные SEO-хвосты).
        (
            "Битрикс24 помогает бизнесу работать",
            "Битрикс24 помогает бизнесу работать",
        ),
        # Только хвост (после чистки пусто/слишком коротко) → None
        (" - результаты поиска на Rusprofile.ru", None),
    ],
)
def test_clean_company_name_for_requisite(raw, expected):
    assert clean_company_name_for_requisite(raw) == expected


# =========================================================================
# Интеграционный тест apply → payload
# =========================================================================


def test_apply_uses_clean_name_in_rq_company_name_full():
    """apply должен прогонять discovered_name через clean-helper перед сборкой
    payload, чтобы в Bitrix не попадали SEO-хвосты вида «… - результаты поиска
    на Rusprofile.ru»."""
    row = QueueRow(
        company_id="42",
        company_name="Bitrix-title 42",
        discovered_inn="7707083893",
        discovered_name="ООО Ромашка - результаты поиска на Rusprofile.ru",
        discovered_source="rusprofile",
        target_action=TargetAction.CREATE_REQ,
        status=Status.APPROVED,
        approved=True,
    )
    bx = FakeBitrix(existing_requisites={"42": []})
    sheets = FakeSheets([row])

    summary = apply.run(
        bx, sheets, sleep_s=0, bizproc_template_id=None, write_name_full=True
    )

    assert summary["applied"] == 1
    assert len(bx.add_calls) == 1
    payload = bx.add_calls[0]
    assert payload["RQ_COMPANY_NAME_FULL"] == "ООО Ромашка"


def test_apply_drops_rq_company_name_full_when_clean_returns_none():
    """Если discovered_name после чистки превращается в мусор (< 2 символов),
    payload не должен содержать ключ RQ_COMPANY_NAME_FULL — bizproc подтянет
    название из ЕГРЮЛ."""
    row = QueueRow(
        company_id="43",
        company_name=" ",  # bitrix_title тоже мусорный
        discovered_inn="7707083893",
        discovered_name=" - результаты поиска на Rusprofile.ru",
        discovered_source="rusprofile",
        target_action=TargetAction.CREATE_REQ,
        status=Status.APPROVED,
        approved=True,
    )
    bx = FakeBitrix(existing_requisites={"43": []})
    sheets = FakeSheets([row])

    summary = apply.run(bx, sheets, sleep_s=0, bizproc_template_id=None)

    assert summary["applied"] == 1
    payload = bx.add_calls[0]
    assert "RQ_COMPANY_NAME_FULL" not in payload
