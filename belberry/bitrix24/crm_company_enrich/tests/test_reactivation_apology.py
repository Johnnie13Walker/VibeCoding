from datetime import date

from crm_company_enrich.stages import reactivation_apology as stage


class FakeBitrix:
    def __init__(self, deals=None, company=None, active_users=None):
        self.deals = deals or []
        self.company = company or {}
        self.active_users = active_users if active_users is not None else {"2772", "2832"}
        self.updated_deals = []
        self.timeline = []

    def list_deals_by_stages(self, *, category_id, stage_ids, closed, select):
        return [
            deal for deal in self.deals
            if deal.get("STAGE_ID") in stage_ids and str(deal.get("CLOSED")) == closed
        ]

    def get_company(self, company_id):
        return self.company

    def list_active_users(self):
        return set(self.active_users)

    def update_deal(self, deal_id, fields, *, params=None):
        self.updated_deals.append((deal_id, fields, params))
        return True

    def add_timeline_comment(self, *, owner_type_id, owner_id, text):
        self.timeline.append((owner_type_id, owner_id, text))
        return "1"


def apology_deal(reason, **overrides):
    deal = {
        "ID": "100",
        "COMPANY_ID": "200",
        "STAGE_ID": "C50:APOLOGY",
        "CLOSED": "Y",
        "ASSIGNED_BY_ID": "2772",
        "CLOSEDATE": "2025-01-01",
        "DATE_MODIFY": "2025-01-01",
        "UF_CRM_1771324790": reason,
        "UF_CRM_REACTIVATION_COUNT": 0,
    }
    deal.update(overrides)
    return deal


def test_reason_8538_never_reactivated_regardless_of_cooldown():
    bx = FakeBitrix([apology_deal("8538")])

    summary = stage.run(bx, today=date(2026, 5, 17))

    assert summary["skipped"] == 1
    assert summary["outcomes"][0]["skipped_reason"] == "never_reactivate"


def test_reason_8540_reactivated_after_12_months():
    bx = FakeBitrix([apology_deal("8540", ASSIGNED_BY_ID="2832")])

    summary = stage.run(bx, dry_run=False, today=date(2026, 5, 17))

    assert summary["reactivated"] == 1
    assert bx.updated_deals[0][1]["STAGE_ID"] == "C50:NEW"


def test_reason_8540_not_reactivated_before_12_months():
    bx = FakeBitrix([apology_deal("8540", CLOSEDATE="2026-01-01")])

    summary = stage.run(bx, today=date(2026, 5, 17))

    assert summary["outcomes"][0]["skipped_reason"] == "too_early"


def test_reason_8546_reactivated_after_6_months():
    bx = FakeBitrix([apology_deal("8546", CLOSEDATE="2025-11-01")])

    assert stage.run(bx, today=date(2026, 5, 17))["dry_run_reactivations"] == 1


def test_reason_8840_reactivated_when_contacts_appear():
    bx = FakeBitrix(
        [apology_deal("8840", CLOSEDATE="2026-01-01")],
        company={"PHONE": [{"VALUE": "+79990000000"}], "DATE_MODIFY": "2026-04-01"},
    )

    assert stage.run(bx, today=date(2026, 5, 17))["dry_run_reactivations"] == 1


def test_reason_8840_requires_new_contacts_since_close():
    bx = FakeBitrix(
        [apology_deal("8840", CLOSEDATE="2026-01-01")],
        company={"EMAIL": [{"VALUE": "new@example.com"}], "DATE_MODIFY": "2026-04-01"},
    )

    assert stage.run(bx, today=date(2026, 5, 17))["dry_run_reactivations"] == 1


def test_reason_8840_not_reactivated_when_contacts_existed_at_close():
    bx = FakeBitrix(
        [apology_deal("8840", CLOSEDATE="2026-04-01")],
        company={"PHONE": [{"VALUE": "+79990000000"}], "DATE_MODIFY": "2026-03-01"},
    )

    summary = stage.run(bx, today=date(2026, 5, 17))

    assert summary["outcomes"][0]["skipped_reason"] == "no_trigger_yet"


def test_reason_8840_not_reactivated_without_trigger():
    bx = FakeBitrix([apology_deal("8840")], company={"DATE_MODIFY": "2026-04-01"})

    summary = stage.run(bx, today=date(2026, 5, 17))

    assert summary["outcomes"][0]["skipped_reason"] == "no_trigger_yet"


def test_dasha_to_arkadiy_swap_on_reactivation():
    bx = FakeBitrix([apology_deal("8540", ASSIGNED_BY_ID="2772")])

    summary = stage.run(bx, today=date(2026, 5, 17))

    assert summary["outcomes"][0]["new_assignee"] == "2832"


def test_reactivation_count_increments():
    bx = FakeBitrix([apology_deal("8540", UF_CRM_REACTIVATION_COUNT=2)])

    stage.run(bx, dry_run=False, today=date(2026, 5, 17))

    assert bx.updated_deals[0][1]["UF_CRM_REACTIVATION_COUNT"] == 3


def test_dry_run_does_not_write():
    bx = FakeBitrix([apology_deal("8540")])

    summary = stage.run(bx, dry_run=True, today=date(2026, 5, 17))

    assert summary["dry_run_reactivations"] == 1
    assert bx.updated_deals == []


def test_unknown_reason_never_reactivated():
    bx = FakeBitrix([apology_deal("9999")])

    summary = stage.run(bx, today=date(2026, 5, 17))

    assert summary["outcomes"][0]["skipped_reason"] == "unknown_reason"


def test_csv_audit_written_for_reactivated(tmp_path, monkeypatch):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    bx = FakeBitrix([apology_deal("8540")])

    stage.run(bx, dry_run=False, today=date(2026, 5, 17))

    path = tmp_path / "reactivation_apology.csv"
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "deal_id,company_id,reason_id" in content
    assert "100,200,8540" in content


def test_no_trigger_skipped_appended_to_sheets(monkeypatch):
    class FakeSheets:
        def __init__(self):
            self.rows = []

        def ensure_sheet(self, tab):
            self.tab = tab

        def read(self, tab, range_):
            return []

        def update(self, tab, range_, rows):
            self.header = rows

        def append(self, tab, rows, value_input_option="RAW"):
            self.rows.extend(rows)

    sheets = FakeSheets()
    monkeypatch.setattr(stage, "_sheets", lambda: sheets)
    bx = FakeBitrix([apology_deal("8840")], company={})

    summary = stage.run(bx, dry_run=False, today=date(2026, 5, 17))

    assert summary["outcomes"][0]["skipped_reason"] == "no_trigger_yet"
    assert sheets.rows
    assert sheets.rows[0][1] == "100"


def test_cooldown_sentinel_trigger_only_csv_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    bx = FakeBitrix(
        [apology_deal("8840", CLOSEDATE="2026-01-01")],
        company={"PHONE": [{"VALUE": "+79990000000"}], "DATE_MODIFY": "2026-04-01"},
    )

    stage.run(bx, dry_run=False, today=date(2026, 5, 17))

    lines = (tmp_path / "reactivation_apology.csv").read_text(encoding="utf-8").splitlines()
    assert lines[1].split(",")[4] == ""


def test_failed_update_does_not_consume_rotation():
    class FailingFirstUpdateBitrix(FakeBitrix):
        def update_deal(self, deal_id, fields, *, params=None):
            if deal_id == "100":
                raise RuntimeError("bitrix down")
            return super().update_deal(deal_id, fields, params=params)

    bx = FailingFirstUpdateBitrix(
        [
            apology_deal("8540", ID="100", ASSIGNED_BY_ID="999"),
            apology_deal("8540", ID="101", ASSIGNED_BY_ID="999"),
        ]
    )

    summary = stage.run(bx, dry_run=False, today=date(2026, 5, 17), rotation_index=0)

    assert summary["outcomes"][0]["status"] == "FAILED"
    assert summary["outcomes"][1]["new_assignee"] == "2772"
    assert bx.updated_deals[0][0] == "101"
