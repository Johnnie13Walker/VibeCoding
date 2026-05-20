from __future__ import annotations

from datetime import datetime, timedelta

from sales_kpi_dashboard.config import MOSCOW_TZ
from sales_kpi_dashboard.freshness import evaluate_last_sync_row


def test_fresh_sync_log_ok() -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=MOSCOW_TZ)
    row = [(now - timedelta(hours=2)).isoformat(timespec="seconds"), "ok", "phase 4"]

    result = evaluate_last_sync_row(row, now=now)

    assert result.ok is True
    assert "OK" in result.message


def test_old_sync_log_warns() -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=MOSCOW_TZ)
    row = [(now - timedelta(hours=7)).isoformat(timespec="seconds"), "ok", "phase 4"]

    result = evaluate_last_sync_row(row, now=now)

    assert result.ok is False
    assert "старше 6ч" in result.message


def test_error_status_warns() -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=MOSCOW_TZ)
    row = [now.isoformat(timespec="seconds"), "error", "phase 4"]

    result = evaluate_last_sync_row(row, now=now)

    assert result.ok is False
    assert "status=error" in result.message
