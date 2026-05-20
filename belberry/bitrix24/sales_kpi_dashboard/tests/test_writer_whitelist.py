from __future__ import annotations

from unittest.mock import Mock

import pytest

from sales_kpi_dashboard.writer import SheetsWriter


def test_writer_rejects_plan_tab() -> None:
    client = Mock()
    writer = SheetsWriter(client)

    with pytest.raises(ValueError, match="read-only"):
        writer.write_tab("Plan", [])

    client.replace_tab.assert_not_called()


def test_writer_rejects_plan_mrr_tab() -> None:
    client = Mock()
    writer = SheetsWriter(client)

    with pytest.raises(ValueError, match="read-only"):
        writer.write_tab("Plan_MRR", [])

    client.replace_tab.assert_not_called()


def test_writer_replaces_writeable_tab() -> None:
    client = Mock()
    writer = SheetsWriter(client)

    writer.write_tab("tm_metrics", [["a", "b"], [1, 2]])

    client.replace_tab.assert_called_once_with("tm_metrics", ["a", "b"], [[1, 2]])
