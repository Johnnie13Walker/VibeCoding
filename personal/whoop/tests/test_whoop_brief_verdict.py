import datetime as dt

from whoop_brief.models import Baseline30d, DailyMetrics
from whoop_brief.verdict import build_verdict


def _history(days: int, **overrides):
    start = dt.date(2026, 5, 26) - dt.timedelta(days=days - 1)
    rows = []
    for offset in range(days):
        values = {
            "date": (start + dt.timedelta(days=offset)).isoformat(),
            "recovery": 75,
            "hrv_ms": 55,
            "rhr_bpm": 63,
            "spo2_pct": 98,
            "sleep_minutes": 450,
            "sleep_need_minutes": 480,
        }
        values.update(overrides)
        rows.append(
            DailyMetrics(**values)
        )
    return rows


def test_verdict_green_without_flags():
    today = DailyMetrics(date="2026-05-26", recovery=78, hrv_ms=55, rhr_bpm=63, spo2_pct=98, sleep_minutes=455, sleep_need_minutes=480)

    verdict = build_verdict(today, [today], Baseline30d(sample_count=30, hrv_ms=54, rhr_bpm=64))

    assert verdict.color == "green"
    assert verdict.flags == []
    assert verdict.plan.steps_target == "8-10 тыс дробно"


def test_verdict_red_when_recovery_is_critical():
    today = DailyMetrics(date="2026-05-26", recovery=25, hrv_ms=40, rhr_bpm=70, spo2_pct=98)

    verdict = build_verdict(today, [today], Baseline30d(sample_count=30, hrv_ms=55, rhr_bpm=64))

    assert verdict.color == "red"
    assert verdict.flags[0].code == "recovery_red"


def test_verdict_red_spo2_streak_7_escalates_to_doctor_hint():
    history = _history(7, spo2_pct=93)
    today = history[-1]

    verdict = build_verdict(today, history, Baseline30d(sample_count=30, hrv_ms=55, rhr_bpm=64))

    assert verdict.color == "red"
    assert verdict.flags[0].code == "spo2_low"
    assert verdict.flags[0].doctor_hint is True
    assert "терапевтом" in verdict.flags[0].text


def test_sleep_below_77_percent_creates_flag():
    today = DailyMetrics(date="2026-05-26", recovery=70, sleep_minutes=350, sleep_need_minutes=480)

    verdict = build_verdict(today, [today], Baseline30d(sample_count=30, hrv_ms=55, rhr_bpm=64))

    assert verdict.color == "green"
    assert any(flag.code == "sleep_low" for flag in verdict.flags)
