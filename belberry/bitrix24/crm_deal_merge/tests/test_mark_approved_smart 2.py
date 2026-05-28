from __future__ import annotations

from crm_deal_merge.config import TAB_GROUPS
from crm_deal_merge.models import GROUP_HEADERS, Group
from crm_deal_merge.stages import mark_approved
from crm_deal_merge.state import Status


class FakeBitrix:
    def __init__(self, stages: dict[str, str]) -> None:
        self.stages = stages

    def get_deal(self, deal_id: str) -> dict | None:
        stage = self.stages.get(deal_id)
        return {"ID": deal_id, "STAGE_ID": stage} if stage else None


class FakeSheets:
    def __init__(self, groups: list[Group]) -> None:
        self.rows = [GROUP_HEADERS, *[group.to_sheet_row() for group in groups]]
        self.updated: list[list[str]] = []

    def read(self, sheet: str, *args, **kwargs):
        assert sheet == TAB_GROUPS
        return self.rows

    def update(self, sheet: str, range_: str, rows: list[list[str]], **kwargs) -> None:
        assert sheet == TAB_GROUPS
        self.updated.extend(rows)


def _group(**overrides) -> Group:
    data = dict(
        company_id="10",
        company_name="Company",
        inn="123",
        domain="foo.ru",
        winner_id="200",
        winner_stage="C50:NEW",
        winner_stage_name="Новая",
        winner_closed=False,
        loser_ids=["100"],
        n_total=2,
        status=Status.PLAN_READY,
        n_activities_planned=1,
        n_timeline_planned=1,
        n_contacts_planned=1,
    )
    data.update(overrides)
    return Group(**data)


def test_smart_skips_no_inn() -> None:
    result = mark_approved.run(FakeSheets([_group(inn="—")]), bx=FakeBitrix({"100": "C38:NEW"}), smart=True)
    assert result["approved"] == 0
    assert result["skipped"]["no_inn"] == 1


def test_smart_skips_mixed_funnels() -> None:
    group = _group(loser_ids=["100", "101"])
    result = mark_approved.run(FakeSheets([group]), bx=FakeBitrix({"100": "C38:NEW", "101": "C50:NEW"}), smart=True)
    assert result["approved"] == 0
    assert result["skipped"]["mixed_loser_funnels"] == 1


def test_smart_skips_won_winner() -> None:
    result = mark_approved.run(FakeSheets([_group(winner_stage="C50:WON")]), bx=FakeBitrix({"100": "C38:NEW"}), smart=True)
    assert result["approved"] == 0
    assert result["skipped"]["winner_won"] == 1


def test_smart_skips_heavy_groups() -> None:
    group = _group(n_activities_planned=99, n_timeline_planned=2, n_contacts_planned=0)
    result = mark_approved.run(FakeSheets([group]), bx=FakeBitrix({"100": "C38:NEW"}), smart=True)
    assert result["approved"] == 0
    assert result["skipped"]["heavy_group"] == 1


def test_smart_skips_heavy_groups_with_sp_planned() -> None:
    group = _group(n_activities_planned=50, n_timeline_planned=0, n_contacts_planned=0, n_sp_planned=80)
    result = mark_approved.run(FakeSheets([group]), bx=FakeBitrix({"100": "C38:NEW"}), smart=True)
    assert result["approved"] == 0
    assert result["skipped"]["heavy_group"] == 1


def test_smart_approves_clean_simple() -> None:
    sheets = FakeSheets([_group()])
    result = mark_approved.run(sheets, bx=FakeBitrix({"100": "C38:NEW"}), smart=True)
    assert result["approved"] == 1
    updated = Group.from_sheet_row(sheets.updated[0], GROUP_HEADERS)
    assert updated.status == Status.APPROVED
    assert updated.approved is True
