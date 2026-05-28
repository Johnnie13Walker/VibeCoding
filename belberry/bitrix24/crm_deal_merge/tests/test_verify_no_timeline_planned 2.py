from __future__ import annotations

from crm_deal_merge.models import Group
from crm_deal_merge.stages.verify import _verify_group
from crm_deal_merge.state import Status


class FakeBitrix:
    def list_deal_contacts(self, deal_id: str):
        return [{"CONTACT_ID": "1"}]

    def list_deal_timeline_comments(self, deal_id: str):
        return []

    def get_deal(self, deal_id: str):
        return {"ID": deal_id, "STAGE_ID": "C38:3"}

    def list_deal_activities(self, deal_id: str):
        return []


def test_verify_does_not_require_transfer_marker_when_no_timeline_planned() -> None:
    group = Group(
        company_id="10",
        company_name="Company",
        inn="—",
        domain="example.ru",
        winner_id="200",
        winner_stage="C38:NEW",
        winner_stage_name="Новая",
        winner_closed=False,
        loser_ids=["100"],
        n_total=2,
        n_winner=1,
        status=Status.MERGED,
        n_timeline_planned=0,
        n_contacts_planned=1,
    )

    assert _verify_group(FakeBitrix(), group, set()) == []


def test_verify_already_linked_contacts_do_not_require_extra_contacts() -> None:
    group = Group(
        company_id="10",
        company_name="Company",
        inn="—",
        domain="example.ru",
        winner_id="200",
        winner_stage="C38:NEW",
        winner_stage_name="Новая",
        winner_closed=False,
        loser_ids=["100"],
        n_total=2,
        n_winner=1,
        status=Status.MERGED,
        n_timeline_planned=0,
        n_contacts_planned=2,
    )
    inventory_rows = [
        (2, {"company_id": "10", "loser_id": "100", "entity_type": "contact", "child_id": "1", "transferred": "1", "note": "already_linked"}),
        (3, {"company_id": "10", "loser_id": "100", "entity_type": "contact", "child_id": "2", "transferred": "1", "note": "already_linked"}),
    ]

    assert _verify_group(FakeBitrix(), group, set(), inventory_rows) == []
