from __future__ import annotations

from crm_company_enrich.config import (
    HOLD_MARKER_FLAG_FIELD,
    HOLD_REASON_COMMENT_FIELD,
    REVIVE_AUDIT_FIELD,
    REVIVE_NEXT_COMMUNICATION_FIELD,
)
from crm_company_enrich.stages import auto_revive_lose as stage


class FakeBitrix:
    def __init__(
        self,
        deals: list[dict],
        *,
        active_users: set[str] | None = None,
    ):
        self.deals = deals
        self.active_users = active_users if active_users is not None else {"2772", "2832"}
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

    def update_deal(self, deal_id: str, fields: dict, *, params: dict | None = None):
        self.update_deal_calls.append((str(deal_id), dict(fields), dict(params or {})))
        for deal in self.deals:
            if str(deal.get("ID")) == str(deal_id):
                deal.update(fields)
        return True

    def add_timeline_comment(self, *, owner_type_id: int, owner_id: str, text: str):
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
        REVIVE_AUDIT_FIELD: "",
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


def test_revive_count_increments_in_audit_field(monkeypatch):
    monkeypatch.setattr(stage, "_today_iso", lambda: "2026-05-17")
    deal = _deal()

    first = stage._build_audit_text(deal)
    deal[REVIVE_AUDIT_FIELD] = first
    second = stage._build_audit_text(deal)

    assert first == "auto-revive 2026-05-17 #1"
    assert second == "auto-revive 2026-05-17 #1; auto-revive 2026-05-17 #2"


def test_ping_pong_limit_3_reached_marks_limit():
    bx = FakeBitrix([_deal(**{REVIVE_AUDIT_FIELD: "auto-revive 2026-05-17 #3"})])

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


def test_csv_audit_written_for_revived(monkeypatch, tmp_path):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    bx = FakeBitrix([_deal()])

    stage.run(bx, dry_run=False, due_before="2026-05-17")

    path = tmp_path / "auto_revive_lose.csv"
    text = path.read_text(encoding="utf-8")
    assert "deal_id,company_id,old_assignee,new_assignee,due_date,revive_count,status" in text
    assert "100,200,2772,2832,2026-05-10,1,REVIVED" in text

