from __future__ import annotations

from crm_company_enrich.stages import dedupe_contacts
from crm_company_enrich.stages import sync_deals


class FakeBitrix:
    def __init__(
        self,
        *,
        company_contacts=None,
        contacts=None,
        contact_companies=None,
        contact_deals=None,
        deals_by_company=None,
        deal_contacts=None,
    ):
        self.company_contacts = company_contacts or {}
        self.contacts = contacts or {}
        self.contact_companies = contact_companies or {}
        self.contact_deals = contact_deals or {}
        self.deals_by_company = deals_by_company or {}
        self.deal_contacts = deal_contacts or {}
        self.update_contact_calls = []
        self.delete_contact_calls = []
        self.add_deal_contact_calls = []
        self.remove_deal_contact_calls = []
        self.remove_contact_company_calls = []

    def list_company_contacts_full(self, company_id):
        return [self.contacts[cid] for cid in self.company_contacts.get(str(company_id), []) if cid in self.contacts]

    def get_company_contacts(self, company_id):
        return list(self.company_contacts.get(str(company_id), []))

    def list_contact_companies(self, contact_id):
        return list(self.contact_companies.get(str(contact_id), ["1"]))

    def list_contact_deals(self, contact_id):
        return list(self.contact_deals.get(str(contact_id), []))

    def list_company_deals(self, company_id, select=None):
        return list(self.deals_by_company.get(str(company_id), []))

    def list_deal_contacts(self, deal_id):
        return list(self.deal_contacts.get(str(deal_id), []))

    def add_deal_contact(self, deal_id, contact_id):
        self.add_deal_contact_calls.append((str(deal_id), str(contact_id)))
        self.deal_contacts.setdefault(str(deal_id), []).append({"CONTACT_ID": str(contact_id)})
        return True

    def remove_deal_contact_relation(self, deal_id, contact_id):
        self.remove_deal_contact_calls.append((str(deal_id), str(contact_id)))
        self.deal_contacts[str(deal_id)] = [
            item for item in self.deal_contacts.get(str(deal_id), [])
            if str(item.get("CONTACT_ID")) != str(contact_id)
        ]
        return True

    def update_contact(self, contact_id, fields, params=None):
        self.update_contact_calls.append((str(contact_id), dict(fields)))
        self.contacts[str(contact_id)].update(fields)
        return True

    def remove_contact_company_relation(self, contact_id, company_id):
        self.remove_contact_company_calls.append((str(contact_id), str(company_id)))
        self.contact_companies[str(contact_id)] = [
            cid for cid in self.contact_companies.get(str(contact_id), [])
            if str(cid) != str(company_id)
        ]
        return True

    def delete_contact(self, contact_id):
        self.delete_contact_calls.append(str(contact_id))
        self.contacts.pop(str(contact_id), None)
        return True


def _contact(contact_id, *, name="Иван", last_name="Петров", phone="", email="", post="", date_create="2024-01-01T00:00:00+03:00", **extra):
    contact = {
        "ID": str(contact_id),
        "NAME": name,
        "LAST_NAME": last_name,
        "SECOND_NAME": "",
        "POST": post,
        "DATE_CREATE": date_create,
        "PHONE": [{"VALUE": phone, "VALUE_TYPE": "WORK", "TYPE_ID": "PHONE"}] if phone else [],
        "EMAIL": [{"VALUE": email, "VALUE_TYPE": "WORK", "TYPE_ID": "EMAIL"}] if email else [],
    }
    contact.update(extra)
    return contact


def _deal(deal_id, *, company_id="1", stage_id="C50:NEW", closed="N"):
    return {
        "ID": str(deal_id),
        "TITLE": f"deal {deal_id}",
        "COMPANY_ID": str(company_id),
        "CATEGORY_ID": "50",
        "STAGE_ID": stage_id,
        "CLOSED": closed,
    }


def test_no_duplicates_attach_missing_contacts_only():
    bx = FakeBitrix(
        company_contacts={"1": ["10"]},
        contacts={"10": _contact("10", phone="+7 999 111-22-33")},
        deals_by_company={"1": [_deal("100")]},
        deal_contacts={"100": []},
    )

    summary = dedupe_contacts.run_company(bx, company_id="1", dry_run=False)

    assert summary["no_duplicates"] == 1
    assert bx.add_deal_contact_calls == [("100", "10")]
    assert summary["outcomes"][0]["deals_with_added_contacts"] == {"100": ["10"]}


def test_obvious_duplicate_by_name_and_phone_merges():
    bx = FakeBitrix(
        company_contacts={"1": ["10", "20"]},
        contacts={
            "10": _contact("10", phone="+7 999 111-22-33", email="ivan@example.com"),
            "20": _contact("20", phone="8 (999) 111-22-33"),
        },
        contact_deals={"10": [_deal("100")], "20": [_deal("200")]},
        deal_contacts={"100": [{"CONTACT_ID": "10"}], "200": [{"CONTACT_ID": "20"}]},
    )

    summary = dedupe_contacts.run_company(bx, company_id="1", dry_run=False)

    assert summary["merged"] == 1
    assert bx.add_deal_contact_calls == [("200", "10")]
    assert bx.remove_deal_contact_calls == [("200", "20")]
    assert bx.delete_contact_calls == ["20"]


def test_duplicate_by_email_and_name_merges():
    bx = FakeBitrix(
        company_contacts={"1": ["10", "20"]},
        contacts={
            "10": _contact("10", phone="+7 999 111-22-33", email="ivan@example.com"),
            "20": _contact("20", phone="+7 999 444-55-66", email="ivan@example.com"),
        },
        contact_deals={},
        deal_contacts={"200": [{"CONTACT_ID": "20"}]},
    )

    dedupe_contacts.run_company(bx, company_id="1", dry_run=False)

    _, fields = bx.update_contact_calls[0]
    assert {item["VALUE"] for item in fields["PHONE"]} == {"+7 999 111-22-33", "+7 999 444-55-66"}
    assert bx.delete_contact_calls == ["20"]


def test_phone_only_match_is_unresolved():
    bx = FakeBitrix(
        company_contacts={"1": ["10", "20"]},
        contacts={
            "10": _contact("10", name="Иван", last_name="Петров", phone="+7 999 111-22-33"),
            "20": _contact("20", name="Анна", last_name="Сидорова", phone="8 999 111 22 33"),
        },
    )

    summary = dedupe_contacts.run_company(bx, company_id="1", dry_run=True)

    assert summary["unresolved"] == 1
    assert summary["outcomes"][0]["skipped_reason"] == "weak_match"
    assert bx.delete_contact_calls == []


def test_conflicting_title_marks_unresolved():
    bx = FakeBitrix(
        company_contacts={"1": ["10", "20"]},
        contacts={
            "10": _contact("10", phone="+7 999 111-22-33", post="Директор"),
            "20": _contact("20", phone="8 999 111 22 33", post="Бухгалтер"),
        },
    )

    summary = dedupe_contacts.run_company(bx, company_id="1", dry_run=True)

    assert summary["unresolved"] == 1
    assert summary["outcomes"][0]["skipped_reason"] == "conflicting_title"


def test_loser_attached_to_other_company_marks_unresolved():
    bx = FakeBitrix(
        company_contacts={"1": ["10", "20"]},
        contacts={
            "10": _contact("10", phone="+7 999 111-22-33", email="ivan@example.com"),
            "20": _contact("20", phone="8 999 111 22 33"),
        },
        contact_companies={"10": ["1"], "20": ["1", "2"]},
    )

    summary = dedupe_contacts.run_company(bx, company_id="1", dry_run=True)

    assert summary["unresolved"] == 1
    assert summary["outcomes"][0]["skipped_reason"] == "multi_company_contact:20"


def test_winner_selection_prefers_more_filled_fields():
    contact_a = _contact("10", phone="+7 999 111-22-33")
    contact_b = _contact("20", phone="+7 999 111-22-33", email="ivan@example.com")

    winner = dedupe_contacts._pick_winner([contact_a, contact_b], {"10": [], "20": []})

    assert winner["ID"] == "20"


def test_winner_selection_prefers_more_deals_when_fields_equal():
    contact_a = _contact("10", phone="+7 999 111-22-33")
    contact_b = _contact("20", phone="+7 999 111-22-33")

    winner = dedupe_contacts._pick_winner(
        [contact_a, contact_b],
        {"10": [_deal("1"), _deal("2"), _deal("3")], "20": [_deal("4")]},
    )

    assert winner["ID"] == "10"


def test_dry_run_does_not_call_delete_or_update():
    bx = FakeBitrix(
        company_contacts={"1": ["10", "20"]},
        contacts={
            "10": _contact("10", phone="+7 999 111-22-33", email="ivan@example.com"),
            "20": _contact("20", phone="8 999 111 22 33"),
        },
        contact_deals={"20": [_deal("200")]},
        deal_contacts={"200": [{"CONTACT_ID": "20"}]},
    )

    summary = dedupe_contacts.run_company(bx, company_id="1", dry_run=True)

    assert summary["dry_run_merges"] == 1
    assert bx.delete_contact_calls == []
    assert bx.update_contact_calls == []
    assert bx.add_deal_contact_calls == []


def test_live_creates_backup_before_delete(monkeypatch, tmp_path):
    monkeypatch.setattr(dedupe_contacts, "BACKUP_DIR", tmp_path)
    bx = FakeBitrix(
        company_contacts={"1": ["10", "20"]},
        contacts={
            "10": _contact("10", phone="+7 999 111-22-33", email="ivan@example.com"),
            "20": _contact("20", phone="8 999 111 22 33"),
        },
    )

    dedupe_contacts.run_company(bx, company_id="1", dry_run=False)

    backups = list(tmp_path.glob("dedupe_contact_20_*.json"))
    assert backups
    assert '"loser_contact_id": "20"' in backups[0].read_text(encoding="utf-8")


def test_after_merge_winner_attached_to_all_loser_deals():
    bx = FakeBitrix(
        company_contacts={"1": ["10", "20"]},
        contacts={
            "10": _contact("10", phone="+7 999 111-22-33", email="ivan@example.com"),
            "20": _contact("20", phone="8 999 111 22 33"),
        },
        contact_deals={"20": [_deal("100"), _deal("200")]},
        deal_contacts={"100": [{"CONTACT_ID": "20"}], "200": [{"CONTACT_ID": "10"}, {"CONTACT_ID": "20"}]},
    )

    dedupe_contacts.run_company(bx, company_id="1", dry_run=False)

    assert ("100", "10") in bx.add_deal_contact_calls
    assert ("200", "10") not in bx.add_deal_contact_calls


def test_after_merge_loser_unlinked_from_all_relations():
    bx = FakeBitrix(
        company_contacts={"1": ["10", "20"]},
        contacts={
            "10": _contact("10", phone="+7 999 111-22-33", email="ivan@example.com"),
            "20": _contact("20", phone="8 999 111 22 33"),
        },
        contact_deals={"20": [_deal("100")]},
        deal_contacts={"100": [{"CONTACT_ID": "20"}]},
    )

    dedupe_contacts.run_company(bx, company_id="1", dry_run=False)

    assert bx.remove_deal_contact_calls == [("100", "20")]
    assert bx.remove_contact_company_calls == [("20", "1")]
    assert bx.delete_contact_calls == ["20"]


def test_unresolved_appended_to_sheets(monkeypatch):
    calls = []
    monkeypatch.setattr(
        dedupe_contacts,
        "_append_unresolved",
        lambda outcome, *, cluster: calls.append((outcome.company_id, outcome.fail_reason or outcome.skipped_reason)) or "tab",
    )
    bx = FakeBitrix(
        company_contacts={"1": ["10", "20"]},
        contacts={
            "10": _contact("10", phone="+7 999 111-22-33", post="Директор"),
            "20": _contact("20", phone="8 999 111 22 33", post="Бухгалтер"),
        },
    )

    dedupe_contacts.run_company(bx, company_id="1", dry_run=False)

    assert calls == [("1", "conflicting_title")]


def test_sync_deals_with_dedupe_contacts_flag_invokes_run_company(monkeypatch):
    calls = []
    monkeypatch.setattr(
        dedupe_contacts,
        "run_company",
        lambda bx, *, company_id, dry_run: calls.append((company_id, dry_run)) or {"merged": 0},
    )
    monkeypatch.setattr(sync_deals, "_attach_scoped_contact_dedupe_summary", sync_deals._attach_scoped_contact_dedupe_summary)
    bx = _SyncFakeBitrix()

    summary = sync_deals.run(bx, company_id="1", dry_run=True, dedupe_contacts=True)
    no_flag = sync_deals.run(bx, company_id="1", dry_run=True, dedupe_contacts=False)

    assert calls == [("1", True)]
    assert summary["contact_dedupe"] == {"merged": 0}
    assert "contact_dedupe" not in no_flag


class _SyncFakeBitrix:
    def get_company(self, company_id):
        return {"ID": str(company_id), "TITLE": "ООО Тест", "UF_CRM_1735331882180": ""}

    def list_company_deals(self, company_id, select=None):
        return [_deal("100", company_id=company_id)]

    def get_company_contacts(self, company_id):
        return []

    def list_deal_contacts(self, deal_id):
        return []
