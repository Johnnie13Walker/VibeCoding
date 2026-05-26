import datetime as dt

from whoop_brief.models import Baseline30d, DailyMetrics
from whoop_brief.renderer import render_morning_brief, render_weekly_brief
from whoop_brief.verdict import build_verdict


def _history():
    start = dt.date(2026, 5, 20)
    recoveries = [72, 70, 69, 66, 64, 68, 78]
    return [
        DailyMetrics(
            date=(start + dt.timedelta(days=i)).isoformat(),
            recovery=recoveries[i],
            hrv_ms=55 + i,
            rhr_bpm=65 - i * 0.2,
            spo2_pct=98,
            sleep_minutes=430 + i,
            sleep_need_minutes=480,
            sleep_efficiency_pct=91,
            strain=8 + i * 0.5,
        )
        for i in range(7)
    ]


def test_render_morning_brief_snapshot():
    history = _history()
    today = history[-1]
    baseline = Baseline30d(sample_count=30, recovery=70, hrv_ms=57, rhr_bpm=64, sleep_minutes=435)
    verdict = build_verdict(today, history, baseline)

    text = render_morning_brief(dt.date(2026, 5, 26), today, baseline, verdict, history)

    assert "<b>WHOOP · 26 мая · вт</b>" in text
    assert "<b>🟢 ЗЕЛЁНЫЙ ДЕНЬ — можно умеренный тренинг</b>" in text
    assert "Тренировка: 40-50 мин" in text
    assert "Восстан.  Ср72 Чт70 Пт69 Сб66 Вс64 Пн68 Вт78" in text
    assert "Профиль" not in text
    assert "План Б" not in text
    assert "Вода:" not in text


def test_render_weekly_brief_snapshot():
    text = render_weekly_brief(dt.date(2026, 5, 20), dt.date(2026, 5, 26), _history(), workouts_count=3)

    assert "<b>WHOOP · неделя</b>" in text
    assert "Recovery:" in text
    assert "Тренировок: 3" in text
    assert "Лучшее восстановление: 78% (2026-05-26)" in text

