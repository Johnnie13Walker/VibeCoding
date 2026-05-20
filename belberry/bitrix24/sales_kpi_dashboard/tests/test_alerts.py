from __future__ import annotations

from unittest.mock import Mock

import pytest

from sales_kpi_dashboard import alerts


def test_consecutive_failures_counts_until_ok() -> None:
    rows = [
        ["2026-05-20T10:00:00+03:00", "ok", "phase 3"],
        ["2026-05-20T14:00:00+03:00", "error", "phase 4"],
        ["2026-05-20T18:00:00+03:00", "error", "phase 4"],
    ]

    assert alerts.consecutive_failures(rows) == 2


def test_no_alert_if_below_threshold(monkeypatch) -> None:
    send = Mock()
    monkeypatch.setattr(alerts, "read_last_sync_rows", lambda _n: [["ts", "error", "phase 4"]])
    monkeypatch.setattr(alerts, "send_telegram_alert", send)

    failures = alerts.check_and_alert(threshold=2)

    assert failures == 1
    send.assert_not_called()


def test_sends_alert_at_threshold(monkeypatch) -> None:
    send = Mock()
    monkeypatch.setattr(
        alerts,
        "read_last_sync_rows",
        lambda _n: [
            ["2026-05-20T10:00:00+03:00", "ok", "phase 3"],
            ["2026-05-20T14:00:00+03:00", "error", "phase 4"],
            ["2026-05-20T18:00:00+03:00", "error", "phase 4"],
        ],
    )
    monkeypatch.setattr(alerts, "send_telegram_alert", send)

    failures = alerts.check_and_alert(threshold=2)

    assert failures == 2
    send.assert_called_once()
    assert "упал 2" in send.call_args.args[0]


def test_alert_requires_env(monkeypatch) -> None:
    monkeypatch.delenv("LARISA_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("LARISA_TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(RuntimeError, match="LARISA_TELEGRAM_BOT_TOKEN"):
        alerts.send_telegram_alert("test")


def test_append_sync_error_writes_error_row(monkeypatch) -> None:
    fake_sheets = Mock()
    monkeypatch.setattr(alerts, "SheetsClient", Mock(return_value=fake_sheets))

    alerts.append_sync_error("boom", phase="phase test")

    fake_sheets.append_log.assert_called_once()
    tab, header, rows = fake_sheets.append_log.call_args.args
    assert tab == "sync_log"
    assert header == alerts.SYNC_LOG_HEADER
    assert rows[0][1:3] == ["error", "phase test"]
    assert rows[0][5] == "boom"
