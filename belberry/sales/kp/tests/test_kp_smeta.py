"""Тесты расчётов генератора сметы (без записи файлов)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kp_smeta import (  # noqa: E402
    VAT,
    cascade,
    line_total,
    min_check_guard,
    validate_smeta,
)


# ── line_total ────────────────────────────────────────────────────────────────

def test_line_hours_rate():
    assert line_total({"hours": 10, "rate": 3100}) == 31_000


def test_line_fixed_monthly_and_once():
    assert line_total({"monthly": 85_000}) == 85_000
    assert line_total({"once": 50_000}) == 50_000
    assert line_total({}) == 0


def test_line_hours_zero_rate_is_hourly_not_fixed():
    assert line_total({"hours": 0, "rate": 3100, "monthly": 999}) == 0


# ── cascade ───────────────────────────────────────────────────────────────────

def test_cascade_vat_only():
    steps = cascade(100_000)
    assert steps == [("Итого без НДС", 100_000.0), ("Итого с НДС 5%", 105_000.0)]


def test_cascade_full_order_logo_then_fast():
    """Порядок выигравших смет: НДС → −10% лого → −5% оперативность."""
    steps = cascade(100_000, logo=True, fast=True)
    assert [round(v) for _, v in steps] == [100_000, 105_000, 94_500, 89_775]


def test_cascade_fast_only():
    assert cascade(100_000, fast=True)[-1][1] == 99_750.0


# ── min_check_guard ───────────────────────────────────────────────────────────

def test_guard_below_min_check_blocks():
    msg = min_check_guard(50_000, "seo", discounts_requested=False)
    assert msg and "ниже минимального чека" in msg


def test_guard_discount_on_min_check_forbidden():
    msg = min_check_guard(75_000, "seo", discounts_requested=True)
    assert msg and "запрещена" in msg


def test_guard_ok_above_min():
    assert min_check_guard(120_000, "seo", discounts_requested=True) is None
    assert min_check_guard(100, "нет_такой", True) is None  # неизвестная услуга — без контроля


# ── validate_smeta ───────────────────────────────────────────────────────────

def test_validate_catches_missing_fields():
    errs = validate_smeta({"items": [{"monthly": 100}]})
    assert any("client" in e for e in errs)
    assert any("name" in e for e in errs)


def test_validate_ok():
    assert validate_smeta({"client": "x.ru", "items": [{"name": "SEO", "monthly": 85_000}]}) == []


def test_vat_is_five_percent():
    """Решение 10.06: все сделки с НДС 5% без указания юрлица."""
    assert VAT == 0.05
