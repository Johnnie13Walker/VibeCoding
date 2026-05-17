from __future__ import annotations

from crm_company_enrich.config import HOLD_MARKER_FLAG_FIELD, HOLD_REASON_FIELD
from crm_company_enrich.stages import telemarketing_dedupe as stage


class FakeBitrix:
    def __init__(
        self,
        *,
        deals: list[dict],
        activities: dict[str, list[dict]] | None = None,
        contacts: dict[str, list[str]] | None = None,
        active_users: set[str] | None = None,
        companies: dict[str, dict] | None = None,
        raise_on_update_deal: set[str] | None = None,
    ):
        self.deals = deals
        self.activities = activities or {}
        self.contacts = contacts or {}
        self.active_users = active_users if active_users is not None else {"2772", "2832"}
        self.companies = companies or {}
        self.raise_on_update_deal = raise_on_update_deal or set()
        self.update_deal_calls: list[tuple[str, dict, dict]] = []
        self.timeline_calls: list[dict] = []
        self.add_deal_contact_calls: list[tuple[str, str]] = []

    def list_deals_by_stages(self, *, category_id, stage_ids, closed="N", select=None):
        return [
            deal for deal in self.deals
            if str(deal.get("CATEGORY_ID") or "") == str(category_id)
            and str(deal.get("STAGE_ID") or "") in set(stage_ids)
            and str(deal.get("CLOSED") or "N") == closed
        ]

    def list_active_users(self):
        return set(self.active_users)

    def list_deal_activities(self, deal_id):
        return list(self.activities.get(str(deal_id), []))

    def list_deal_contacts(self, deal_id):
        return [{"CONTACT_ID": contact_id} for contact_id in self.contacts.get(str(deal_id), [])]

    def add_deal_contact(self, deal_id, contact_id):
        self.add_deal_contact_calls.append((str(deal_id), str(contact_id)))
        self.contacts.setdefault(str(deal_id), []).append(str(contact_id))
        return True

    def update_deal(self, deal_id, fields, *, params=None):
        if str(deal_id) in self.raise_on_update_deal:
            raise RuntimeError(f"update failed for {deal_id}")
        self.update_deal_calls.append((str(deal_id), dict(fields), dict(params or {})))
        return True

    def add_timeline_comment(self, *, owner_type_id, owner_id, text):
        self.timeline_calls.append({"owner_type_id": owner_type_id, "owner_id": str(owner_id), "text": text})
        return "timeline-1"

    def get_company(self, company_id):
        return self.companies.get(str(company_id), {"ID": str(company_id), "TITLE": f"Компания {company_id}"})


class FakeSheets:
    def __init__(self):
        self.append_calls: list[tuple[str, list[list], str]] = []
        self.update_calls: list[tuple[str, str, list[list]]] = []
        self.ensure_calls: list[str] = []
        self.rows: dict[str, list[list]] = {}

    def get_sheet_title_by_id(self, sheet_id):
        return "Dedupe unresolved"

    def ensure_sheet(self, title):
        self.ensure_calls.append(title)
        return 1

    def read(self, sheet, range_="A1:Z10000", unformatted=False):
        return self.rows.get(sheet, [])

    def update(self, sheet, range_, rows, value_input_option="RAW"):
        self.update_calls.append((sheet, range_, rows))
        self.rows[sheet] = rows

    def append(self, sheet, rows, value_input_option="RAW"):
        self.append_calls.append((sheet, rows, value_input_option))
        self.rows.setdefault(sheet, []).extend(rows)


def _deal(deal_id, company_id="10", stage_id="C50:NEW", assigned_by="2772", date_modify="2026-05-17T10:00:00+03:00", **extra):
    return {
        "ID": str(deal_id),
        "TITLE": f"deal {deal_id}",
        "COMPANY_ID": str(company_id),
        "CATEGORY_ID": "50",
        "STAGE_ID": stage_id,
        "CLOSED": "N",
        "ASSIGNED_BY_ID": assigned_by,
        "DATE_MODIFY": date_modify,
        **extra,
    }


def _activities(count: int) -> list[dict]:
    return [{"ID": str(i)} for i in range(count)]


def test_no_duplicates_returns_no_op():
    bx = FakeBitrix(deals=[_deal("1")])

    summary = stage.run(bx)

    assert summary["duplicate_companies"] == 0
    assert summary["outcomes"] == []
    assert bx.update_deal_calls == []


def test_winner_picked_by_activity_count():
    deals = [_deal("1"), _deal("2")]
    bx = FakeBitrix(deals=deals, activities={"1": _activities(5), "2": _activities(2)})

    summary = stage.run(bx)

    assert summary["outcomes"][0]["winner_deal_id"] == "1"


def test_winner_picked_by_stage_when_activities_equal():
    deals = [_deal("1", stage_id="C50:UC_1S1KIU"), _deal("2", stage_id="C50:PREPARATION")]
    bx = FakeBitrix(deals=deals, activities={"1": _activities(2), "2": _activities(2)})

    summary = stage.run(bx)

    assert summary["outcomes"][0]["winner_deal_id"] == "2"


def test_winner_picked_by_modify_date_when_tied():
    deals = [
        _deal("1", date_modify="2026-05-17T09:00:00+03:00"),
        _deal("2", date_modify="2026-05-17T10:00:00+03:00"),
    ]
    bx = FakeBitrix(deals=deals)

    summary = stage.run(bx)

    assert summary["outcomes"][0]["winner_deal_id"] == "2"


def test_winner_assignee_active_stays():
    bx = FakeBitrix(deals=[_deal("1", assigned_by="2772"), _deal("2")], active_users={"2772", "2832"})

    summary = stage.run(bx)

    assert summary["outcomes"][0]["reassigned_winner_to"] == ""
    assert summary["outcomes"][0]["winner_assigned_by"] == "2772"


def test_winner_assignee_inactive_reassigned_to_active_via_rotation():
    bx = FakeBitrix(
        deals=[_deal("1", assigned_by="999"), _deal("2")],
        activities={"1": _activities(3), "2": _activities(1)},
        active_users={"2772", "2832"},
    )

    summary = stage.run(bx, rotation_index=1)

    assert summary["outcomes"][0]["reassigned_winner_from"] == "999"
    assert summary["outcomes"][0]["reassigned_winner_to"] == "2832"


def test_inactive_assignee_in_whitelist_kept():
    bx = FakeBitrix(deals=[_deal("1", assigned_by="2772"), _deal("2")], active_users=set())

    summary = stage.run(bx)

    assert summary["outcomes"][0]["winner_assigned_by"] == "2772"
    assert summary["outcomes"][0]["reassigned_winner_to"] == ""


def test_loser_closed_with_reason_8544(monkeypatch, tmp_path):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    bx = FakeBitrix(deals=[_deal("1"), _deal("2")])

    stage.run(bx, dry_run=False)
    loser_call = [call for call in bx.update_deal_calls if call[0] == "1"][0]

    assert loser_call[1]["STAGE_ID"] == "C50:APOLOGY"
    assert loser_call[1]["CLOSED"] == "Y"
    assert loser_call[1][HOLD_REASON_FIELD] == "8544"


def test_loser_timeline_links_to_winner(monkeypatch, tmp_path):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    bx = FakeBitrix(deals=[_deal("1"), _deal("2")])

    stage.run(bx, dry_run=False)

    assert any(call["owner_id"] == "1" and "2" in call["text"] for call in bx.timeline_calls)


def test_winner_timeline_lists_losers(monkeypatch, tmp_path):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    bx = FakeBitrix(deals=[_deal("1"), _deal("2")])

    stage.run(bx, dry_run=False)

    assert any(call["owner_id"] == "2" and "1" in call["text"] for call in bx.timeline_calls)


def test_unique_contacts_transferred_to_winner(monkeypatch, tmp_path):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    bx = FakeBitrix(
        deals=[_deal("1"), _deal("2")],
        contacts={"1": ["10", "20"], "2": ["10", "30"]},
    )

    stage.run(bx, dry_run=False)

    assert ("2", "20") in bx.add_deal_contact_calls
    assert ("2", "10") not in bx.add_deal_contact_calls


def test_dry_run_writes_nothing():
    bx = FakeBitrix(deals=[_deal("1"), _deal("2")], activities={"1": _activities(1), "2": _activities(3)})

    summary = stage.run(bx, dry_run=True)

    assert summary["outcomes"][0]["status"] == "DRY_RUN"
    assert summary["outcomes"][0]["activity_counts"] == {"1": 1, "2": 3}
    assert bx.update_deal_calls == []
    assert bx.timeline_calls == []


def test_merge_failure_appends_row_to_sheets(monkeypatch, tmp_path):
    fake_sheets = FakeSheets()
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    monkeypatch.setattr(stage, "_sheets", lambda: fake_sheets)
    bx = FakeBitrix(deals=[_deal("1"), _deal("2")], raise_on_update_deal={"1"})

    summary = stage.run(bx, dry_run=False)

    assert summary["unresolved"] == 1
    assert summary["outcomes"][0]["status"] == "UNRESOLVED"
    assert fake_sheets.append_calls


def test_sheets_append_failure_falls_back_to_csv(monkeypatch, tmp_path):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    monkeypatch.setattr(stage, "_append_unresolved", lambda outcome, *, company: (_ for _ in ()).throw(RuntimeError("sheets down")))
    bx = FakeBitrix(deals=[_deal("1"), _deal("2")], raise_on_update_deal={"1"})

    summary = stage.run(bx, dry_run=False)

    path = tmp_path / "telemarketing_dedupe_failed.csv"
    assert summary["unresolved"] == 1
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "10" in text
    assert "update failed for 1" in text
    assert "sheets down" in text
    assert "sheets_append_failed" in summary["outcomes"][0]["fail_reason"]


def test_sheets_append_failure_does_not_block_other_groups(monkeypatch, tmp_path):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    monkeypatch.setattr(stage, "_append_unresolved", lambda outcome, *, company: (_ for _ in ()).throw(RuntimeError("sheets down")))
    bx = FakeBitrix(
        deals=[
            _deal("1", company_id="10"),
            _deal("2", company_id="10"),
            _deal("3", company_id="20"),
            _deal("4", company_id="20"),
        ],
        raise_on_update_deal={"1"},
    )

    summary = stage.run(bx, dry_run=False)

    assert summary["merged"] >= 1
    assert summary["unresolved"] == 1
    assert (tmp_path / "telemarketing_dedupe_failed.csv").exists()


def test_already_dedupe_marker_skipped():
    bx = FakeBitrix(
        deals=[
            _deal("1"),
            _deal("2", **{HOLD_MARKER_FLAG_FIELD: "1", HOLD_REASON_FIELD: "8544"}),
        ]
    )

    summary = stage.run(bx)

    assert summary["duplicate_companies"] == 0
    assert bx.update_deal_calls == []


def test_dedupe_marker_skips_only_marked_deal_in_group():
    deals = [
        _deal("1", **{HOLD_MARKER_FLAG_FIELD: "1"}),
        _deal("2"),
        _deal("3"),
    ]

    groups = stage._duplicate_groups(deals)

    assert len(groups) == 1
    assert groups[0][0] == "10"
    assert [deal["ID"] for deal in groups[0][1]] == ["2", "3"]


def test_no_active_users_fallback_to_unresolved(monkeypatch):
    fake_sheets = FakeSheets()
    monkeypatch.setattr(stage, "HARDCODED_ACTIVE_USER_IDS", set())
    monkeypatch.setattr(stage, "_sheets", lambda: fake_sheets)
    bx = FakeBitrix(deals=[_deal("1", assigned_by="999"), _deal("2")], active_users=set())

    summary = stage.run(bx, dry_run=False)

    assert summary["unresolved"] == 1
    assert summary["outcomes"][0]["fail_reason"] == "cannot_determine_active_users"
    assert bx.update_deal_calls == []
    assert fake_sheets.append_calls


def test_three_duplicates_one_winner_two_losers():
    bx = FakeBitrix(
        deals=[_deal("1"), _deal("2", stage_id="C50:PREPARATION"), _deal("3", stage_id="C50:NEW")],
        activities={"1": _activities(1), "2": _activities(5), "3": _activities(2)},
    )

    summary = stage.run(bx)

    assert summary["outcomes"][0]["winner_deal_id"] == "2"
    assert set(summary["outcomes"][0]["closed_deal_ids"]) == {"1", "3"}
