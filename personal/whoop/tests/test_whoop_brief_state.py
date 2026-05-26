import datetime as dt

from whoop_brief.models import DailyMetrics
from whoop_brief.state import baseline_30d, backfill_state, load_state, metrics_from_state, update_daily_metrics


def test_baseline_uses_latest_30_days():
    rows = [
        DailyMetrics(
            date=(dt.date(2026, 4, 1) + dt.timedelta(days=i)).isoformat(),
            recovery=50 + i,
            hrv_ms=40 + i,
            rhr_bpm=70 - i * 0.1,
            sleep_minutes=420 + i,
        )
        for i in range(35)
    ]

    baseline = baseline_30d(rows, "2026-05-05")

    assert baseline.sample_count == 30
    assert baseline.incomplete is False
    assert round(baseline.hrv_ms or 0) == 60


def test_update_daily_metrics_replaces_same_date():
    state = {"daily_metrics": [DailyMetrics(date="2026-05-01", recovery=40).__dict__]}

    update_daily_metrics(state, DailyMetrics(date="2026-05-01", recovery=70))

    rows = metrics_from_state(state)
    assert len(rows) == 1
    assert rows[0].recovery == 70


def test_backfill_state_roundtrip(tmp_path):
    path = tmp_path / "whoop-state.json"

    backfill_state([DailyMetrics(date="2026-05-26", recovery=88)], path=str(path))

    rows = metrics_from_state(load_state(str(path)))
    assert rows == [DailyMetrics(date="2026-05-26", recovery=88.0)]


def test_baseline_marks_incomplete_when_fewer_than_30_days():
    rows = [
        DailyMetrics(
            date=(dt.date(2026, 5, 1) + dt.timedelta(days=i)).isoformat(),
            recovery=70 + i,
        )
        for i in range(5)
    ]

    baseline = baseline_30d(rows, "2026-05-05")

    assert baseline.sample_count == 5
    assert baseline.incomplete is True


def test_baseline_takes_last_30_when_history_has_60_days():
    rows = [
        DailyMetrics(
            date=(dt.date(2026, 3, 1) + dt.timedelta(days=i)).isoformat(),
            recovery=i,
        )
        for i in range(60)
    ]

    baseline = baseline_30d(rows, "2026-04-29")

    assert baseline.sample_count == 30
    assert baseline.recovery in (44, 45, 44.5)
