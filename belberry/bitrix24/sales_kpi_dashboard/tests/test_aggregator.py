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
