from __future__ import annotations

import pytest

from crm_company_enrich.models import (
    inn_checksum_ok,
    is_valid_inn_format,
    normalize_inn,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("7707083893", "7707083893"),
        ("770708389300", "770708389300"),
        (" 7707083893 ", "7707083893"),
        ("ИНН 7707083893", "7707083893"),
        ("7707-083-893", "7707083893"),  # цифры сшиваются
        ("123", None),
        ("12345678901", None),  # 11 цифр — невалидно
        ("abcdefghij", None),
        ("", None),
        (None, None),
        ("12345678901234", None),  # 14 цифр — невалидно
    ],
)
def test_normalize_inn(raw, expected):
    assert normalize_inn(raw) == expected


@pytest.mark.parametrize(
    ("inn", "expected"),
    [
        ("7707083893", True),
        ("770708389300", True),
        ("123", False),
        ("12345678901", False),
        ("", False),
        (None, False),
        ("abcdefghij", False),
    ],
)
def test_is_valid_inn_format(inn, expected):
    assert is_valid_inn_format(inn) is expected


def test_inn_checksum_real_examples():
    # Известные валидные ИНН организаций (Сбербанк, Google Russia, Яндекс)
    assert inn_checksum_ok("7707083893")
    assert inn_checksum_ok("7704270863")
    # phys-person 12-digit (synthetic, but checksum-valid)
    # Сгенерирован по алгоритму для проверки расчёта обеих контрольных цифр.
    assert inn_checksum_ok("500100732259")


def test_inn_checksum_rejects_corrupted():
    assert not inn_checksum_ok("7707083894")  # подменили последнюю цифру
    assert not inn_checksum_ok("500100732250")
    assert not inn_checksum_ok("123")
