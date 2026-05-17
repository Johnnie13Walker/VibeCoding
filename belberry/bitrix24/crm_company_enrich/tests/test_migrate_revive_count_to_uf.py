from __future__ import annotations

from crm_company_enrich.config import LAST_AUTO_ACTION_DESC_FIELD, REVIVE_COUNT_FIELD
from crm_company_enrich.stages import migrate_revive_count_to_uf as stage


class FakeBitrix:
    def __init__(self, deals: list[dict], *, fail_ids: set[str] | None = None):
        self.deals = deals
        self.fail_ids = fail_ids or set()
        self.update_deal_calls: list[tuple[str, dict]] = []

    def paginate(self, method: str, params: dict):
        assert method == "crm.deal.list"
        for deal in self.deals:
            if str(deal.get(LAST_AUTO_ACTION_DESC_FIELD) or "").strip():
                yield dict(deal)

    def update_deal(self, deal_id: str, fields: dict) -> bool:
        if str(deal_id) in self.fail_ids:
            raise RuntimeError(f"update failed for {deal_id}")
        self.update_deal_calls.append((str(deal_id), dict(fields)))
        for deal in self.deals:
            if str(deal.get("ID")) == str(deal_id):
                deal.update(fields)
        return True


def _deal(deal_id: str = "1", *, desc: str = "auto-revive 2026-05-17 #2", count=0):
    return {"ID": deal_id, LAST_AUTO_ACTION_DESC_FIELD: desc, REVIVE_COUNT_FIELD: count}


def test_dry_run_reports_migration_candidates():
    bx = FakeBitrix([_deal()])

    summary = stage.run(bx)

    assert summary["dry_run_migrations"] == 1
    assert summary["outcomes"][0]["status"] == "DRY_RUN"
    assert summary["outcomes"][0]["new_count"] == 2
    assert bx.update_deal_calls == []


def test_live_writes_count_to_uf():
    bx = FakeBitrix([_deal()])

    summary = stage.run(bx, dry_run=False)

    assert summary["migrated"] == 1
    assert bx.update_deal_calls == [("1", {REVIVE_COUNT_FIELD: 2})]


def test_already_migrated_idempotent():
    bx = FakeBitrix([_deal(count=2)])

    summary = stage.run(bx, dry_run=False)

    assert summary["skipped"] == 1
    assert bx.update_deal_calls == []


def test_unknown_old_id_no_op():
    bx = FakeBitrix([_deal(desc="auto-reject 8538 @ 2026-05-17")])

    summary = stage.run(bx)

    assert summary["outcomes"] == []
    assert summary["dry_run_migrations"] == 0


def test_failure_during_update_does_not_block_others():
    bx = FakeBitrix([_deal("1"), _deal("2", desc="auto-revive 2026-05-18 #3")], fail_ids={"1"})

    summary = stage.run(bx, dry_run=False)

    assert summary["failed"] == 1
    assert summary["migrated"] == 1
    assert bx.update_deal_calls == [("2", {REVIVE_COUNT_FIELD: 3})]
