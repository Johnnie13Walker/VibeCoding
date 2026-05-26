from __future__ import annotations

import datetime as dt
from pathlib import Path
from string import Template
from typing import Iterable, Optional

from .models import Baseline30d, DailyMetrics, Verdict
from .verdict import format_minutes

WEEKDAY_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
MONTH_RU = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}

TEMPLATES_DIR = Path(__file__).with_name("templates")


def render_morning_brief(
    report_date: dt.date,
    today: DailyMetrics,
    baseline: Baseline30d,
    verdict: Verdict,
    history: Iterable[DailyMetrics],
    *,
    header_note: Optional[str] = None,
) -> str:
    trend = trend_summary(list(history), report_date)
    flags = "\n".join(f"{flag.emoji} {flag.text}" for flag in verdict.flags) or "✅ Активных флагов нет."
    baseline_note = " <i>(baseline неполный)</i>" if baseline.incomplete else ""
    sleep_need = format_minutes(today.sleep_need_minutes)
    sleep_last = format_minutes(today.sleep_minutes)
    why = _why_block(today, baseline)

    template = _load_template("morning_brief.txt")
    return template.safe_substitute(
        date_header=_date_header(report_date),
        header_note=f"<i>{header_note}</i>\n" if header_note else "",
        emoji=verdict.emoji,
        headline=verdict.headline,
        top_flag=verdict.top_flag,
        training_duration=verdict.plan.duration,
        hr_zone=verdict.plan.hr_zone,
        modality=verdict.plan.modality,
        steps_target=verdict.plan.steps_target,
        sleep_action=verdict.plan.sleep_action,
        sleep_last=sleep_last,
        sleep_need=sleep_need,
        baseline_note=baseline_note,
        why=why,
        flags=flags,
        today_weekday=WEEKDAY_SHORT[report_date.weekday()],
        trend_recovery=trend["recovery"],
        trend_summary=trend["summary"],
    ).strip()


def render_weekly_brief(
    week_start: dt.date,
    week_end: dt.date,
    history: Iterable[DailyMetrics],
    *,
    workouts_count: int = 0,
) -> str:
    rows = [item for item in history if week_start.isoformat() <= item.date <= week_end.isoformat()]
    rows.sort(key=lambda item: item.date)
    recovery_avg = _avg(item.recovery for item in rows)
    hrv_avg = _avg(item.hrv_ms for item in rows)
    rhr_avg = _avg(item.rhr_bpm for item in rows)
    sleep_avg = _avg(item.sleep_minutes for item in rows)
    strain_avg = _avg(item.strain for item in rows)
    best = _best_recovery(rows)
    worst = _worst_recovery(rows)

    template = _load_template("weekly_brief.txt")
    return template.safe_substitute(
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
        recovery_avg=_percent(recovery_avg),
        hrv_avg=_number(hrv_avg, "ms"),
        rhr_avg=_number(rhr_avg),
        sleep_avg=format_minutes(int(round(sleep_avg))) if sleep_avg is not None else "н/д",
        strain_avg=f"{strain_avg:.1f}" if strain_avg is not None else "н/д",
        workouts_count=str(workouts_count),
        recovery_spark=_spark(item.recovery for item in rows),
        sleep_spark=_spark(item.sleep_minutes for item in rows),
        strain_spark=_spark(item.strain for item in rows),
        best_recovery=best,
        worst_recovery=worst,
    ).strip()


def trend_summary(history: list[DailyMetrics], report_date: dt.date) -> dict[str, str]:
    by_date = {item.date: item for item in history}
    start = report_date - dt.timedelta(days=6)
    rec_parts: list[str] = []
    hrv_vals: list[Optional[float]] = []
    rhr_vals: list[Optional[float]] = []
    sleep_vals: list[Optional[float]] = []
    strain_vals: list[Optional[float]] = []
    for offset in range(7):
        day = start + dt.timedelta(days=offset)
        item = by_date.get(day.isoformat())
        rec_parts.append(f"{WEEKDAY_SHORT[day.weekday()]}{int(item.recovery):02d}" if item and item.recovery is not None else f"{WEEKDAY_SHORT[day.weekday()]}·")
        hrv_vals.append(item.hrv_ms if item else None)
        rhr_vals.append(item.rhr_bpm if item else None)
        sleep_vals.append(item.sleep_minutes if item else None)
        strain_vals.append(item.strain if item else None)
    return {
        "recovery": " ".join(rec_parts),
        "summary": (
            f"HRV {_number(_avg(hrv_vals), 'ms')} ср · "
            f"RHR {_number(_avg(rhr_vals))} ср · "
            f"Сон {format_minutes(int(round(_avg(sleep_vals)))) if _avg(sleep_vals) is not None else 'н/д'} ср · "
            f"Strain {(_avg(strain_vals)):.1f} ср" if _avg(strain_vals) is not None else
            f"HRV {_number(_avg(hrv_vals), 'ms')} ср · RHR {_number(_avg(rhr_vals))} ср · Сон {format_minutes(int(round(_avg(sleep_vals)))) if _avg(sleep_vals) is not None else 'н/д'} ср · Strain н/д"
        ),
    }


def _why_block(today: DailyMetrics, baseline: Baseline30d) -> str:
    rows = [
        f"Восстановление  {_percent(today.recovery)}",
        f"HRV             {_number(today.hrv_ms, 'ms')}  {_delta(today.hrv_ms, baseline.hrv_ms, 'ms')}",
        f"RHR             {_number(today.rhr_bpm)}  {_delta(today.rhr_bpm, baseline.rhr_bpm, '', lower_is_better=True)}",
        f"Сон-эффективн.  {_percent(today.sleep_efficiency_pct)}",
        f"Baseline 30д: recovery {_percent(baseline.recovery)}, сон {format_minutes(baseline.sleep_minutes)}",
    ]
    return "\n".join(rows)


def _date_header(value: dt.date) -> str:
    return f"{value.day} {MONTH_RU.get(value.month, value.month)} · {WEEKDAY_SHORT[value.weekday()].lower()}"


def _load_template(name: str) -> Template:
    return Template((TEMPLATES_DIR / name).read_text(encoding="utf-8"))


def _avg(values: Iterable[Optional[float]]) -> Optional[float]:
    nums = [float(value) for value in values if value is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def _number(value: Optional[float], unit: str = "") -> str:
    if value is None:
        return "н/д"
    return f"{value:.0f}{unit}"


def _percent(value: Optional[float]) -> str:
    if value is None:
        return "н/д"
    return f"{value:.0f}%"


def _delta(value: Optional[float], baseline: Optional[float], unit: str = "", *, lower_is_better: bool = False) -> str:
    if value is None or baseline is None:
        return "н/д"
    diff = value - baseline
    improved = diff < 0 if lower_is_better else diff > 0
    arrow = "▲" if improved else ("▬" if abs(diff) < 0.5 else "▼")
    sign = "+" if diff > 0 else ""
    return f"{arrow} {sign}{diff:.0f}{unit} к baseline {baseline:.0f}{unit}"


def _spark(values: Iterable[Optional[float]]) -> str:
    nums = [value for value in values if value is not None]
    if not nums:
        return "н/д"
    blocks = "▁▂▃▄▅▆▇█"
    lo = min(nums)
    hi = max(nums)
    if hi == lo:
        return blocks[3] * len(nums)
    out = []
    for value in nums:
        idx = int(round((value - lo) / (hi - lo) * (len(blocks) - 1)))
        out.append(blocks[idx])
    return "".join(out)


def _best_recovery(rows: list[DailyMetrics]) -> str:
    candidates = [item for item in rows if item.recovery is not None]
    if not candidates:
        return "н/д"
    best = max(candidates, key=lambda item: item.recovery or 0)
    return f"{best.recovery:.0f}% ({best.date})"


def _worst_recovery(rows: list[DailyMetrics]) -> str:
    candidates = [item for item in rows if item.recovery is not None]
    if not candidates:
        return "н/д"
    worst = min(candidates, key=lambda item: item.recovery or 0)
    return f"{worst.recovery:.0f}% ({worst.date})"

