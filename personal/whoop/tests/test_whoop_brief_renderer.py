import datetime as dt

from whoop_brief.models import Baseline30d, DailyMetrics
from whoop_brief.renderer import render_morning_brief, render_weekly_brief
from whoop_brief.verdict import build_verdict, format_minutes


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

    assert "WHOOP · 26 мая · вт" in text
    assert "🟢 ЗЕЛЁНЫЙ ДЕНЬ — можно умеренный тренинг" in text
    assert "ПЛАН: 40-50 мин" in text
    assert "Метрики vs baseline 30д:" in text
    assert "Тренд недели (recovery):" in text
    assert "Ср 72 · Чт 70 · Пт 69 · Сб 66 · Вс 64 · Пн 68 · Вт 78" in text
    assert "Среднее 7д:" in text
    # выпиленные элементы старого формата:
    assert "<b>" not in text
    assert "____" not in text
    assert "ПОЧЕМУ" not in text
    assert "ФЛАГИ" not in text
    assert "Профиль" not in text
    assert "План Б" not in text
    assert "Вода:" not in text
    # формат тренда без слипания weekday+number:
    assert "С618" not in text
    assert "Сб66" not in text


def test_render_weekly_brief_snapshot():
    text = render_weekly_brief(dt.date(2026, 5, 20), dt.date(2026, 5, 26), _history(), workouts_count=3)

    assert "<b>WHOOP · неделя</b>" in text
    assert "Recovery:" in text
    assert "Тренировок: 3" in text
    assert "Лучшее восстановление: 78% (2026-05-26)" in text


def test_format_minutes_zero_minutes_compact():
    assert format_minutes(480) == "8ч"
    assert format_minutes(355) == "5ч55"
    assert format_minutes(363) == "6ч03"
    assert format_minutes(None) == "н/д"


def test_zero_delta_renders_as_baseline_phrase():
    today = DailyMetrics(
        date="2026-05-26",
        recovery=72,
        hrv_ms=57,  # ровно baseline
        rhr_bpm=64,  # ровно baseline
        spo2_pct=98,
        sleep_minutes=440,
        sleep_need_minutes=480,
        sleep_efficiency_pct=92,
    )
    baseline = Baseline30d(sample_count=30, recovery=70, hrv_ms=57, rhr_bpm=64, sleep_minutes=440)
    verdict = build_verdict(today, [today], baseline)

    text = render_morning_brief(dt.date(2026, 5, 26), today, baseline, verdict, [today])

    assert "HRV 57ms — как baseline" in text
    assert "RHR 64 — как baseline" in text
    # никаких "+0ms" / "▬ +0":
    assert "+0ms" not in text
    assert "▬" not in text


def test_spo2_in_top_flag_not_duplicated_in_metrics():
    today = DailyMetrics(
        date="2026-05-26",
        recovery=72,
        hrv_ms=57,
        rhr_bpm=64,
        spo2_pct=93.0,  # триггерит spo2_low
        sleep_minutes=440,
        sleep_need_minutes=480,
        sleep_efficiency_pct=92,
    )
    baseline = Baseline30d(sample_count=30, recovery=70, hrv_ms=57, rhr_bpm=64, sleep_minutes=440)
    verdict = build_verdict(today, [today], baseline)

    text = render_morning_brief(dt.date(2026, 5, 26), today, baseline, verdict, [today])

    # SpO₂ должен быть упомянут ровно один раз (в top_flag), не повторно в блоке метрик
    assert text.count("SpO₂") == 1


def test_spo2_93_5_renders_with_decimal():
    today = DailyMetrics(
        date="2026-05-26",
        recovery=72,
        hrv_ms=57,
        rhr_bpm=64,
        spo2_pct=93.5,
        sleep_minutes=440,
        sleep_need_minutes=480,
        sleep_efficiency_pct=92,
    )
    baseline = Baseline30d(sample_count=30, recovery=70, hrv_ms=57, rhr_bpm=64, sleep_minutes=440)
    verdict = build_verdict(today, [today], baseline)

    text = render_morning_brief(dt.date(2026, 5, 26), today, baseline, verdict, [today])

    assert "93.5%" in text
    # никакого округления вверх — значение должно остаться 93.5, не "SpO₂ 94%":
    assert "SpO₂ 94%" not in text


def test_trend_weekday_and_number_separated_by_space():
    history = _history()
    today = history[-1]
    baseline = Baseline30d(sample_count=30, recovery=70, hrv_ms=57, rhr_bpm=64, sleep_minutes=435)
    verdict = build_verdict(today, history, baseline)

    text = render_morning_brief(dt.date(2026, 5, 26), today, baseline, verdict, history)

    # Не должно быть слипшихся weekday+числа типа "С618", "Сб66"
    for weekday in ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"):
        for digit in "0123456789":
            assert f"{weekday}{digit}" not in text, f"Найдено слипание {weekday}{digit}"
