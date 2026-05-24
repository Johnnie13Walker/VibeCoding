from __future__ import annotations

import argparse
import json

from crm_deal_merge import cli
from crm_deal_merge.stages import empty_companies


def test_cmd_empty_companies_uses_target_sheet_and_writes_summary(monkeypatch, tmp_path) -> None:
    seen = {}

    def fake_make_clients(sheet_id=cli.SHEET_ID):
        seen["sheet_id"] = sheet_id
        return object(), object()

    def fake_run(bx, sheets, *, write_sheet: bool):
        seen["write_sheet"] = write_sheet
        return {
            "trash_companies": 42,
            "previous_snapshot_rows": 40,
            "delta_vs_previous": 2,
        }

    monkeypatch.setattr(cli, "_make_clients", fake_make_clients)
    monkeypatch.setattr(empty_companies, "run", fake_run)
    summary_path = tmp_path / "summary.json"

    code = cli.cmd_empty_companies_refresh(
        argparse.Namespace(live=False, max_rows=12000, summary_json=str(summary_path))
    )

    assert code == 0
    assert seen == {"sheet_id": empty_companies.TARGET_SHEET_ID, "write_sheet": False}
    assert json.loads(summary_path.read_text(encoding="utf-8"))["trash_companies"] == 42


def test_cmd_empty_companies_stops_on_safety_limit(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_make_clients", lambda sheet_id=cli.SHEET_ID: (object(), object()))
    monkeypatch.setattr(
        empty_companies,
        "run",
        lambda bx, sheets, *, write_sheet: {"trash_companies": 12001},
    )

    code = cli.cmd_empty_companies_refresh(
        argparse.Namespace(live=True, max_rows=12000, summary_json=None)
    )

    assert code == 2
