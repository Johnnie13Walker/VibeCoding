from __future__ import annotations

from unittest.mock import Mock

from sales_kpi_dashboard import aggregator


def test_aggregate_returns_expected_tabs(monkeypatch) -> None:
    class FakeSheetsClient:
        service = Mock()

        def __init__(self, *_args, **_kwargs):
            pass

        def _execute(self, _request):
            return {"values": [["Period", "Metric", "Dimension", "Value"]]}

    class FakeReader:
        pass

    monkeypatch.setattr(aggregator, "SheetsClient", FakeSheetsClient)
    monkeypatch.setattr(aggregator, "BitrixReader", FakeReader)
    monkeypatch.setattr(aggregator.telemarketing, "compute", lambda reader, plan, today: [["h"], ["tm"]])
    monkeypatch.setattr(aggregator.sales_plan, "compute", lambda reader, plan, today: [["h"], ["sales"]])
    monkeypatch.setattr(aggregator.mop_effectiveness, "compute", lambda reader, today: [["h"], ["mop"]])

    result = aggregator.aggregate()

    assert set(result) == {"tm_metrics", "sales_plan", "mop_metrics", "sync_log"}
    assert all(isinstance(rows, list) for rows in result.values())
    assert all(isinstance(row, list) for rows in result.values() for row in rows)
    assert result["sync_log"][0] == ["ts", "status", "phase", "duration_ms", "rows_written", "error"]
    assert result["sync_log"][1][1:3] == ["ok", "phase 3"]
    assert result["sync_log"][1][4] == 3


def test_read_plan_returns_empty_when_plan_tab_missing(caplog) -> None:
    class FakeSheetsClient:
        service = Mock()

        def _execute(self, _request):
            raise RuntimeError("Unable to parse range: 'Plan'!A1:D")

    plan = aggregator.read_plan(FakeSheetsClient())

    assert plan.by_key == {}
    assert "Plan tab недоступен" in caplog.text
