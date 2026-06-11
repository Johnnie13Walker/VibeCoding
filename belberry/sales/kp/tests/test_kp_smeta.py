"""Тесты расчётов генератора сметы (без записи файлов)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kp_smeta import (  # noqa: E402
    PRESETS,
    VAT,
    build_rows,
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


# ── build_rows (секции-этапы) ─────────────────────────────────────────────────

def test_build_rows_flat_no_section_totals():
    rows, subtotal = build_rows([{"name": "a", "once": 100}, {"name": "b", "once": 50}])
    assert subtotal == 150
    assert [r["kind"] for r in rows] == ["item", "item"]


def test_build_rows_sections_with_totals():
    rows, subtotal = build_rows([
        {"section": "ЭТАП 1"}, {"name": "a", "once": 100}, {"name": "b", "once": 50},
        {"section": "ЭТАП 2"}, {"name": "c", "once": 200},
    ])
    kinds = [r["kind"] for r in rows]
    assert kinds == ["section", "item", "item", "section_total",
                     "section", "item", "section_total"]
    assert rows[3]["total"] == 150 and rows[6]["total"] == 200
    assert subtotal == 350


def test_validate_allows_sections():
    assert validate_smeta({"client": "x", "items": [{"section": "ЭТАП 1"},
                                                    {"name": "a", "once": 1}]}) == []


# ── пресеты = итоги продуктовой матрицы (снято 10.06.2026) ───────────────────

def _preset_total(key):
    return build_rows(PRESETS[key]["items"])[1]


def test_preset_tv_total_matches_matrix():
    assert _preset_total("tv") == 681_100  # ОБЩАЯ СУММА БЕЗ НДС, вкладка «ТВ»


def test_preset_tv_section_totals_match_matrix():
    rows, _ = build_rows(PRESETS["tv"]["items"])
    sec = [r["total"] for r in rows if r["kind"] == "section_total"]
    assert sec == [267_800, 222_100, 191_200]  # этапы: дизайн / вёрстка / контент


def test_preset_ta_total_matches_matrix():
    assert _preset_total("ta") == 676_101  # вкладка «TA» (шаблон за 1 ₽ — спецпредложение)


def test_preset_lp_total_matches_matrix():
    assert _preset_total("lp") == 145_300


def test_preset_branding_total_matches_matrix():
    assert _preset_total("branding") == 517_700


def test_preset_program_deposit():
    assert _preset_total("program-deposit") == 39_000


def test_preset_program_included_rows_dont_change_total():
    """Типовые работы 1-го месяца — «включено», сумма пакета не меняется."""
    assert _preset_total("program") == 31_000
    rows, _ = build_rows(PRESETS["program"]["items"])
    included = [r for r in rows if r["kind"] == "item" and r["item"].get("included")]
    assert len(included) == 6 and all(r["total"] == 0 for r in included)
    # нулевой подытог секции «включено» не печатается
    assert not any(r["kind"] == "section_total" and r["total"] == 0 for r in rows)
