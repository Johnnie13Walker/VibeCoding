from __future__ import annotations

from crm_deal_merge.cli import _print_detailed_status
from crm_deal_merge.models import Group
from crm_deal_merge.state import Status


def test_status_detailed_prints_top_tables(capsys) -> None:
    groups = [
        Group(
            company_id="10",
            company_name="Company",
            inn="123",
            domain="foo.ru",
            winner_id="200",
            winner_stage="C50:NEW",
            winner_stage_name="Новая",
            winner_closed=False,
            loser_ids=["100", "101"],
            status=Status.FAILED,
            n_activities_planned=10,
            n_timeline_planned=5,
            n_contacts_planned=1,
            error_message="TITLE safety check failed",
        )
    ]

    _print_detailed_status(groups)

    out = capsys.readouterr().out
    assert "Топ-10 групп по n_loser" in out
    assert "Топ-10 групп по transferable" in out
    assert "FAILED групп: 1" in out
    assert "TITLE safety check failed" in out
