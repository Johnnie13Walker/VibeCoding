from crm_company_enrich.config import CONTACT_PERSONAL_INN_FIELD
from crm_company_enrich.stages import enrich_director_inn as stage


HTML = '<h2>Руководитель</h2><a href="/person/rozhkov-vs-263201428652">Рожков Виктор Сергеевич</a>'


class FakeBitrix:
    def __init__(self, requisites=None, contacts=None, deals=None):
        self.requisites = requisites if requisites is not None else [{"RQ_INN": "7710875112"}]
        self.contacts = contacts if contacts is not None else []
        self.deals = deals if deals is not None else []
        self.update_contact_calls = []
        self.timeline_calls = []

    def list_company_requisites(self, company_id):
        return self.requisites

    def list_company_contacts_full(self, company_id):
        return self.contacts

    def update_contact(self, contact_id, fields, *, params=None):
        self.update_contact_calls.append((str(contact_id), dict(fields), params))
        return True

    def add_timeline_comment(self, *, owner_type_id, owner_id, text):
        self.timeline_calls.append((owner_type_id, str(owner_id), text))
        return "1"

    def list_deals_by_stages(self, *, category_id, stage_ids, closed, select):
        return self.deals


def contact(**overrides):
    data = {
        "ID": "10",
        "LAST_NAME": "Рожков",
        "NAME": "Виктор",
        "SECOND_NAME": "Сергеевич",
        "POST": "Генеральный директор",
    }
    data.update(overrides)
    return data


def patch_fetch(monkeypatch, html=HTML):
    monkeypatch.setattr(stage, "_fetch_rusprofile_html", lambda inn: html)


def test_ip_company_skipped(monkeypatch):
    patch_fetch(monkeypatch)
    bx = FakeBitrix(requisites=[{"RQ_INN": "123", "RQ_OGRNIP": "123456789012345"}])

    summary = stage.run_company(bx, company_id="1")

    assert summary["outcomes"][0]["skipped_reason"] == "company_is_ip"


def test_no_rusprofile_html_skipped(monkeypatch):
    patch_fetch(monkeypatch, html="")
    bx = FakeBitrix()

    assert stage.run_company(bx, company_id="1")["outcomes"][0]["skipped_reason"] == "rusprofile_not_available"


def test_director_not_found_in_html_skipped(monkeypatch):
    patch_fetch(monkeypatch, html="<html></html>")
    bx = FakeBitrix()

    assert stage.run_company(bx, company_id="1")["outcomes"][0]["skipped_reason"] == "director_inn_not_found_in_rusprofile"


def test_no_contacts_skipped(monkeypatch):
    patch_fetch(monkeypatch)
    bx = FakeBitrix(contacts=[])

    assert stage.run_company(bx, company_id="1")["outcomes"][0]["skipped_reason"] == "no_company_contacts"


def test_exact_name_match_enriches(monkeypatch):
    patch_fetch(monkeypatch)
    bx = FakeBitrix(contacts=[contact()])

    summary = stage.run_company(bx, company_id="1")

    assert summary["dry_run_enrichments"] == 1
    assert summary["outcomes"][0]["matched_contact_id"] == "10"
    assert summary["outcomes"][0]["director_inn"] == "263201428652"


def test_partial_name_match_first_only(monkeypatch):
    patch_fetch(monkeypatch)
    bx = FakeBitrix(contacts=[contact(SECOND_NAME="")])

    assert stage.run_company(bx, company_id="1")["dry_run_enrichments"] == 1


def test_partial_name_match_middle_only(monkeypatch):
    patch_fetch(monkeypatch)
    bx = FakeBitrix(contacts=[contact(NAME="", SECOND_NAME="Сергеевич")])

    assert stage.run_company(bx, company_id="1")["dry_run_enrichments"] == 1


def test_no_match_unresolved(monkeypatch, tmp_path):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    patch_fetch(monkeypatch)
    bx = FakeBitrix(contacts=[contact(LAST_NAME="Иванов")])

    summary = stage.run_company(bx, company_id="1")

    assert summary["unresolved"] == 1
    assert summary["outcomes"][0]["skipped_reason"] == "no_matching_contact"


def test_dry_run_unresolved_does_not_write_csv(monkeypatch, tmp_path):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    patch_fetch(monkeypatch)
    bx = FakeBitrix(contacts=[contact(LAST_NAME="Иванов")])

    stage.run_company(bx, company_id="1", dry_run=True)

    assert not (tmp_path / "enrich_director_inn.csv").exists()


def test_ambiguous_match_unresolved(monkeypatch, tmp_path):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    patch_fetch(monkeypatch)
    bx = FakeBitrix(contacts=[contact(ID="10"), contact(ID="11")])

    summary = stage.run_company(bx, company_id="1")

    assert summary["unresolved"] == 1
    assert summary["outcomes"][0]["skipped_reason"] == "ambiguous_matches"
    assert summary["outcomes"][0]["ambiguous_candidates"] == ["10", "11"]


def test_existing_manual_inn_differs_unresolved(monkeypatch, tmp_path):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    patch_fetch(monkeypatch)
    bx = FakeBitrix(contacts=[contact(**{CONTACT_PERSONAL_INN_FIELD: "111111111111"})])

    summary = stage.run_company(bx, company_id="1")

    assert summary["outcomes"][0]["skipped_reason"] == "manual_inn_differs"


def test_already_set_skipped(monkeypatch):
    patch_fetch(monkeypatch)
    bx = FakeBitrix(contacts=[contact(**{CONTACT_PERSONAL_INN_FIELD: "263201428652"})])

    assert stage.run_company(bx, company_id="1")["outcomes"][0]["skipped_reason"] == "already_set"


def test_dry_run_does_not_write(monkeypatch):
    patch_fetch(monkeypatch)
    bx = FakeBitrix(contacts=[contact()])

    stage.run_company(bx, company_id="1", dry_run=True)

    assert bx.update_contact_calls == []


def test_live_writes_uf_and_timeline(monkeypatch, tmp_path):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    patch_fetch(monkeypatch)
    bx = FakeBitrix(contacts=[contact()])

    summary = stage.run_company(bx, company_id="1", dry_run=False)

    assert summary["enriched"] == 1
    assert bx.update_contact_calls[0][1] == {CONTACT_PERSONAL_INN_FIELD: "263201428652"}
    assert bx.timeline_calls


def test_register_sonet_event_param_passed(monkeypatch, tmp_path):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    patch_fetch(monkeypatch)
    bx = FakeBitrix(contacts=[contact()])

    stage.run_company(bx, company_id="1", dry_run=False)

    assert bx.update_contact_calls[0][2] == {"REGISTER_SONET_EVENT": "Y"}


def test_csv_audit_in_tmp_path(monkeypatch, tmp_path):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    patch_fetch(monkeypatch)
    bx = FakeBitrix(contacts=[contact()])

    stage.run_company(bx, company_id="1", dry_run=False)

    path = tmp_path / "enrich_director_inn.csv"
    assert path.exists()
    assert "263201428652" in path.read_text(encoding="utf-8")
