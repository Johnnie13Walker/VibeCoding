from __future__ import annotations

import datetime as dt
from typing import Iterable, Optional

from .models import Baseline30d, DailyMetrics, Flag, TrainingPlan, Verdict

SPO2_DOCTOR_HINT_DAYS = 7


def build_verdict(
    today: DailyMetrics,
    history: Iterable[DailyMetrics],
    baseline: Baseline30d,
    *,
    hr_max: int = 177,
) -> Verdict:
    flags = build_flags(today, history, baseline)
    critical = any(flag.severity == "critical" for flag in flags)

    if critical or (today.recovery is not None and today.recovery < 34):
        color, emoji, headline = "red", "🔴", "КРАСНЫЙ — день восстановления"
    elif today.recovery is None:
        color, emoji, headline = "yellow", "🟡", "ЖЁЛТЫЙ — данных WHOOP недостаточно"
    elif today.recovery >= 67:
        color, emoji, headline = "green", "🟢", "ЗЕЛЁНЫЙ ДЕНЬ — можно умеренный тренинг"
    elif today.recovery >= 34:
        color, emoji, headline = "yellow", "🟡", "ЖЁЛТЫЙ — умеренная нагрузка"
    else:
        color, emoji, headline = "red", "🔴", "КРАСНЫЙ — день восстановления"

    ordered_flags = sorted(flags, key=lambda item: _severity_rank(item.severity))
    top_flag = ordered_flags[0].text if ordered_flags else "Главных флагов нет — день выглядит ровно."
    return Verdict(
        color=color,
        emoji=emoji,
        headline=headline,
        top_flag=top_flag,
        flags=ordered_flags,
        plan=training_plan(color, hr_max=hr_max, sleep_need_minutes=today.sleep_need_minutes),
    )


def build_flags(today: DailyMetrics, history: Iterable[DailyMetrics], baseline: Baseline30d) -> list[Flag]:
    flags: list[Flag] = []
    if today.recovery is not None and today.recovery < 34:
        flags.append(Flag("recovery_red", "critical", "🔴", f"Recovery {today.recovery:.0f}% — критически низкое восстановление."))

    spo2_streak = _streak_days(history, today.date, lambda item: item.spo2_pct is not None and item.spo2_pct < 94.0)
    if today.spo2_pct is not None and today.spo2_pct < 94.0:
        spo2_text = _format_spo2(today.spo2_pct)
        if spo2_streak >= SPO2_DOCTOR_HINT_DAYS:
            flags.append(
                Flag(
                    "spo2_low",
                    "critical",
                    "🔴",
                    f"SpO₂ {spo2_text} — {spo2_streak}-й день ниже 94%, обсуди с терапевтом (возможен вопрос апноэ)",
                    streak_days=spo2_streak,
                    doctor_hint=True,
                )
            )
        elif spo2_streak >= 3:
            flags.append(
                Flag(
                    "spo2_low",
                    "orange",
                    "🟠",
                    f"SpO₂ {spo2_text} — {spo2_streak}-й день ниже 94%, проверь нос/позу",
                    streak_days=spo2_streak,
                )
            )
        else:
            day_word = "первый" if spo2_streak <= 1 else f"{spo2_streak}-й"
            flags.append(Flag("spo2_low", "yellow", "🟡", f"SpO₂ {spo2_text} — {day_word} день ниже 94%, наблюдаем", streak_days=spo2_streak))

    sleep_ratio = _sleep_ratio(today)
    sleep_streak = _streak_days(history, today.date, lambda item: (_sleep_ratio(item) or 1.0) < 0.77)
    if sleep_ratio is not None and sleep_ratio < 0.77:
        severity = "orange" if sleep_streak >= 3 else "yellow"
        emoji = "🟠" if severity == "orange" else "🟡"
        flags.append(
            Flag(
                "sleep_low",
                severity,
                emoji,
                f"Сон {format_minutes(today.sleep_minutes)} — {sleep_ratio * 100:.0f}% от потребности.",
                streak_days=sleep_streak,
            )
        )

    if today.hrv_ms is not None and baseline.hrv_ms is not None and today.hrv_ms < baseline.hrv_ms * 0.70:
        flags.append(Flag("hrv_low", "orange", "🟠", f"HRV {today.hrv_ms:.0f}ms — ниже baseline 30д на 30%+."))

    if today.rhr_bpm is not None and baseline.rhr_bpm is not None and today.rhr_bpm > baseline.rhr_bpm * 1.10:
        flags.append(Flag("rhr_high", "yellow", "🟡", f"RHR {today.rhr_bpm:.0f} — выше baseline 30д на 10%+."))

    if today.strain is not None and today.strain > 15:
        flags.append(Flag("strain_high", "yellow", "🟡", f"Strain {today.strain:.1f} — высокая нагрузка, держи восстановление в фокусе."))

    return flags


def training_plan(color: str, *, hr_max: int = 177, sleep_need_minutes: Optional[int] = None) -> TrainingPlan:
    if color == "green":
        return TrainingPlan(
            "40-50 мин",
            f"{round(hr_max * 0.60)}-{round(hr_max * 0.70)} уд/мин",
            "низкоударно: ходьба с уклоном / эллипс / вело",
            "8-10 тыс дробно",
            "лечь до 23:30",
        )
    if color == "yellow":
        return TrainingPlan(
            "30-40 мин",
            f"{round(hr_max * 0.50)}-{round(hr_max * 0.60)} уд/мин",
            "низкоударно, без интенсива",
            "6-8 тыс дробно",
            "лечь до 23:30",
        )
    return TrainingPlan(
        "20-30 мин",
        "очень легко",
        "ходьба + мобилизация + дыхание",
        "3-4 тыс спокойно",
        "приоритет — добрать сон",
    )


def format_minutes(value: Optional[int]) -> str:
    if value is None:
        return "н/д"
    hours = value // 60
    minutes = value % 60
    if minutes == 0:
        return f"{hours}ч"
    return f"{hours}ч{minutes:02d}"


def _streak_days(history: Iterable[DailyMetrics], report_date: str, predicate) -> int:
    by_date = {item.date: item for item in history}
    cursor = dt.date.fromisoformat(report_date)
    days = 0
    while True:
        item = by_date.get(cursor.isoformat())
        if item is None or not predicate(item):
            return days
        days += 1
        cursor -= dt.timedelta(days=1)


def _format_spo2(value: float) -> str:
    rounded = round(value, 1)
    if rounded == int(rounded):
        return f"{int(rounded)}%"
    return f"{rounded:.1f}%"


def _sleep_ratio(item: DailyMetrics) -> Optional[float]:
    if item.sleep_minutes is not None and item.sleep_need_minutes and item.sleep_need_minutes > 0:
        return item.sleep_minutes / item.sleep_need_minutes
    if item.sleep_performance_pct is not None:
        return item.sleep_performance_pct / 100.0
    return None


def _severity_rank(value: str) -> int:
    return {"critical": 0, "orange": 1, "yellow": 2}.get(value, 9)

