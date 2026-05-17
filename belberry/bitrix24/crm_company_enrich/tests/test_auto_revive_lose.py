from __future__ import annotations

from crm_company_enrich.config import (
    HOLD_MARKER_FLAG_FIELD,
    HOLD_REASON_COMMENT_FIELD,
    LAST_AUTO_ACTION_DESC_FIELD,
    LOG_DIR as PRODUCTION_LOG_DIR,
    REVIVE_COUNT_FIELD,
    REVIVE_NEXT_COMMUNICATION_FIELD,
)
from crm_company_enrich.stages import auto_revive_lose as stage


class FakeBitrix:
    def __init__(
        self,
        deals: list[dict],
        *,
        active_users: set[str] | None = None,
        fresh_deals: dict[str, dict | None] | None = None,
        fail_update: bool = False,
        fail_timeline: bool = False,
    ):
        self.deals = deals
        self.active_users = active_users if active_users is not None else {"2772", "2832"}
        self.fresh_deals = fresh_deals or {}
        self.fail_update = fail_update
        self.fail_timeline = fail_timeline
        self.update_deal_calls: list[tuple[str, dict, dict]] = []
        self.timeline_calls: list[dict] = []

    def list_revive_candidates(self, *, due_before: str):
        return [
            dict(deal) for deal in self.deals
            if str(deal.get("STAGE_ID") or "") == "C50:LOSE"
            and str(deal.get("CLOSED") or "") == "Y"
        ]

    def list_active_users(self):
        return set(self.active_users)

    def get_deal(self, deal_id: str):
        if str(deal_id) in self.fresh_deals:
            fresh = self.fresh_deals[str(deal_id)]
            return dict(fresh) if fresh else None
        for deal in self.deals:
            if str(deal.get("ID")) == str(deal_id):
                return dict(deal)
        return None

    def update_deal(self, deal_id: str, fields: dict, *, params: dict | None = None):
        if self.fail_update:
            raise RuntimeError("update failed")
        self.update_deal_calls.append((str(deal_id), dict(fields), dict(params or {})))
        for deal in self.deals:
            if str(deal.get("ID")) == str(deal_id):
                deal.update(fields)
        return True

    def add_timeline_comment(self, *, owner_type_id: int, owner_id: str, text: str):
        if self.fail_timeline:
            raise RuntimeError("timeline failed")
        self.timeline_calls.append({"owner_type_id": owner_type_id, "owner_id": str(owner_id), "text": text})
        return "timeline-1"


def _deal(**overrides) -> dict:
    data = {
        "ID": "100",
        "TITLE": "Отложенная сделка",
        "COMPANY_ID": "200",
        "STAGE_ID": "C50:LOSE",
        "CLOSED": "Y",
        "ASSIGNED_BY_ID": "2772",
        REVIVE_NEXT_COMMUNICATION_FIELD: "2026-05-10",
        HOLD_REASON_COMMENT_FIELD: "вернуться через 3 месяца",
        HOLD_MARKER_FLAG_FIELD: "0",
        LAST_AUTO_ACTION_DESC_FIELD: "",
        REVIVE_COUNT_FIELD: 0,
    }
    data.update(overrides)
    return data


def test_lose_with_past_date_revives_to_new(monkeypatch):
    monkeypatch.setattr(stage, "_today_iso", lambda: "2026-05-17")
    bx = FakeBitrix([_deal()])

    summary = stage.run(bx, dry_run=False, due_before="2026-05-17")

    assert summary["revived"] == 1
    _, fields, _ = bx.update_deal_calls[0]
    assert fields["STAGE_ID"] == "C50:NEW"
    assert fields["CLOSED"] == "N"
    assert fields["SOURCE_ID"] == "12"
    assert fields["ASSIGNED_BY_ID"] == "2832"


def test_lose_with_future_date_not_revived():
    bx = FakeBitrix([_deal(**{REVIVE_NEXT_COMMUNICATION_FIELD: "2030-01-01"})])

    summary = stage.run(bx, due_before="2026-05-17")

    assert summary["examined"] == 0
    assert bx.update_deal_calls == []


def test_dasha_to_arkadiy_assignee_swap():
    bx = FakeBitrix([_deal(ASSIGNED_BY_ID="2772")])

    summary = stage.run(bx, due_before="2026-05-17")

    assert summary["outcomes"][0]["new_assignee"] == "2832"


def test_arkadiy_to_dasha_assignee_swap():
    bx = FakeBitrix([_deal(ASSIGNED_BY_ID="2832")])

    summary = stage.run(bx, due_before="2026-05-17")

    assert summary["outcomes"][0]["new_assignee"] == "2772"


def test_inactive_assignee_uses_rotation():
    bx = FakeBitrix([_deal(ASSIGNED_BY_ID="999")])

    summary = stage.run(bx, due_before="2026-05-17")

    assert summary["outcomes"][0]["new_assignee"] == "2772"


def test_auto_rejected_lose_is_skipped():
    bx = FakeBitrix([_deal(**{HOLD_MARKER_FLAG_FIELD: "1"})])

    summary = stage.run(bx, dry_run=False, due_before="2026-05-17")

    assert summary["skipped"] == 1
    assert summary["outcomes"][0]["skipped_reason"] == "auto_rejected_skip"
    assert bx.update_deal_calls == []


def test_revive_count_reads_from_int_field():
    deal = _deal(**{REVIVE_COUNT_FIELD: 2})

    assert stage._revive_count(deal) == 2


def test_revive_count_ignores_string_desc_field():
    deal = _deal(
        **{
            REVIVE_COUNT_FIELD: 0,
            LAST_AUTO_ACTION_DESC_FIELD: "auto-revive 2026-05-17 #5",
        }
    )

    assert stage._revive_count(deal) == 0


def test_revive_increments_int_field(monkeypatch):
    monkeypatch.setattr(stage, "_today_iso", lambda: "2026-05-17")
    bx = FakeBitrix([_deal(**{REVIVE_COUNT_FIELD: 1})])

    stage.run(bx, dry_run=False, due_before="2026-05-17")

    _, fields, _ = bx.update_deal_calls[0]
    assert fields[REVIVE_COUNT_FIELD] == 2


def test_last_auto_action_desc_is_overwritten_not_appended(monkeypatch):
    monkeypatch.setattr(stage, "_today_iso", lambda: "2026-05-17")
    bx = FakeBitrix(
        [_deal(**{LAST_AUTO_ACTION_DESC_FIELD: "auto-reject 8538 @ 2026-04-01"})]
    )

    stage.run(bx, dry_run=False, due_before="2026-05-17")

    _, fields, _ = bx.update_deal_calls[0]
    assert fields[LAST_AUTO_ACTION_DESC_FIELD] == "auto-revive 2026-05-17 #1"


def test_limit_reached_uses_int_not_string_parse():
    bx = FakeBitrix([_deal(**{REVIVE_COUNT_FIELD: 3, LAST_AUTO_ACTION_DESC_FIELD: "любой текст"})])

    summary = stage.run(bx, dry_run=False, due_before="2026-05-17")

    assert summary["limit_reached"] == 1
    assert summary["outcomes"][0]["status"] == "LIMIT_REACHED"
    assert bx.update_deal_calls == []


def test_dry_run_does_not_write():
    bx = FakeBitrix([_deal()])

    summary = stage.run(bx, dry_run=True, due_before="2026-05-17")

    assert summary["dry_run_updates"] == 1
    assert bx.update_deal_calls == []
    assert bx.timeline_calls == []


def test_timeline_comment_includes_reason_and_due_date():
    bx = FakeBitrix([_deal()])

    stage.run(bx, dry_run=False, due_before="2026-05-17")

    text = bx.timeline_calls[0]["text"]
    assert "вернуться через 3 месяца" in text
    assert "2026-05-10" in text


def test_register_sonet_event_param_passed():
    bx = FakeBitrix([_deal()])

    stage.run(bx, dry_run=False, due_before="2026-05-17")

    assert bx.update_deal_calls[0][2] == {"REGISTER_SONET_EVENT": "Y"}


def test_csv_audit_written_for_revived(tmp_path):
    bx = FakeBitrix([_deal()])

    stage.run(bx, dry_run=False, due_before="2026-05-17")

    path = tmp_path / "logs" / "auto_revive_lose.csv"
    text = path.read_text(encoding="utf-8")
    assert "deal_id,company_id,old_assignee,new_assignee,due_date,revive_count,status" in text
    assert "100,200,2772,2832,2026-05-10,1,REVIVED" in text


def test_csv_audit_uses_tmp_path_not_production(tmp_path):
    production_path = PRODUCTION_LOG_DIR / "auto_revive_lose.csv"
    size_before = production_path.stat().st_size if production_path.exists() else 0
    bx = FakeBitrix([_deal()])

    stage.run(bx, dry_run=False, due_before="2026-05-17")

    assert (tmp_path / "logs" / "auto_revive_lose.csv").exists()
    size_after = production_path.stat().st_size if production_path.exists() else 0
    assert size_after == size_before


def test_stage_changed_between_list_and_update_skips():
    bx = FakeBitrix([_deal()], fresh_deals={"100": {"ID": "100", "STAGE_ID": "C50:NEW", "CLOSED": "N"}})

    summary = stage.run(bx, dry_run=False, due_before="2026-05-17")

    assert summary["skipped"] == 1
    assert summary["outcomes"][0]["status"] == "SKIPPED"
    assert "stage_changed" in summary["outcomes"][0]["skipped_reason"]
    assert bx.update_deal_calls == []


def test_already_open_between_list_and_update_skips():
    bx = FakeBitrix([_deal()], fresh_deals={"100": {"ID": "100", "STAGE_ID": "C50:LOSE", "CLOSED": "N"}})

    summary = stage.run(bx, dry_run=False, due_before="2026-05-17")

    assert summary["skipped"] == 1
    assert summary["outcomes"][0]["skipped_reason"] == "already_open"
    assert bx.update_deal_calls == []


def test_timeline_failure_does_not_fail_revive(tmp_path):
    bx = FakeBitrix([_deal()], fail_timeline=True)

    summary = stage.run(bx, dry_run=False, due_before="2026-05-17")

    assert summary["revived"] == 1
    assert summary["failed"] == 0
    assert summary["outcomes"][0]["status"] == "REVIVED"
    assert "timeline_failed:" in summary["outcomes"][0]["error"]
    assert len(bx.update_deal_calls) == 1
    text = (tmp_path / "logs" / "auto_revive_lose.csv").read_text(encoding="utf-8")
    assert "100,200,2772,2832,2026-05-10,1,REVIVED,timeline_failed:timeline failed" in text


def test_update_deal_failure_returns_failed_status():
    bx = FakeBitrix([_deal()], fail_update=True)

    summary = stage.run(bx, dry_run=False, due_before="2026-05-17")

    assert summary["failed"] == 1
    assert summary["outcomes"][0]["status"] == "FAILED"
    assert "update failed" in summary["outcomes"][0]["error"]
    assert bx.timeline_calls == []
