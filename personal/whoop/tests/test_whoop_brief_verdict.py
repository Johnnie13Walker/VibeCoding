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


def test_verdict_yellow_when_recovery_between_34_and_67():
    today = DailyMetrics(date="2026-05-26", recovery=50, hrv_ms=55, rhr_bpm=63, spo2_pct=98)

    verdict = build_verdict(today, [today], Baseline30d(sample_count=30, hrv_ms=55, rhr_bpm=63))

    assert verdict.color == "yellow"
    assert "ЖЁЛТЫЙ" in verdict.headline


def test_spo2_streak_3_is_orange_not_red():
    history = _history(3, spo2_pct=92)

    verdict = build_verdict(history[-1], history, Baseline30d(sample_count=30, hrv_ms=55, rhr_bpm=63))
    spo2_flag = next(flag for flag in verdict.flags if flag.code == "spo2_low")

    assert spo2_flag.severity == "orange"
    assert spo2_flag.emoji == "🟠"
    assert spo2_flag.doctor_hint is False


def test_streak_resets_after_normal_day():
    start = dt.date(2026, 5, 22)
    values = [92, 92, 98, 92, 92]
    history = [
        DailyMetrics(
            date=(start + dt.timedelta(days=offset)).isoformat(),
            recovery=75,
            hrv_ms=55,
            rhr_bpm=63,
            spo2_pct=spo2,
        )
        for offset, spo2 in enumerate(values)
    ]

    verdict = build_verdict(history[-1], history, Baseline30d(sample_count=30, hrv_ms=55, rhr_bpm=63))
    spo2_flag = next(flag for flag in verdict.flags if flag.code == "spo2_low")

    assert spo2_flag.streak_days == 2


def test_hrv_below_baseline_by_30pct_creates_flag():
    today = DailyMetrics(date="2026-05-26", recovery=75, hrv_ms=35, rhr_bpm=63, spo2_pct=98)

    verdict = build_verdict(today, [today], Baseline30d(sample_count=30, hrv_ms=55, rhr_bpm=63))
    hrv_flag = next(flag for flag in verdict.flags if flag.code == "hrv_low")

    assert hrv_flag.severity == "orange"


def test_green_with_spo2_streak_3_keeps_color_green_but_flag_present():
    history = _history(3, recovery=78, spo2_pct=93)

    verdict = build_verdict(history[-1], history, Baseline30d(sample_count=30, hrv_ms=55, rhr_bpm=63))

    assert verdict.color == "green"
    assert any(flag.code == "spo2_low" and flag.severity == "orange" for flag in verdict.flags)
    assert "SpO₂" in verdict.top_flag
