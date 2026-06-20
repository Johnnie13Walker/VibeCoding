from __future__ import annotations

from crm_company_enrich.stages import rebind_orphan_contacts as rob


def _contact(cid: str, *, name="Иван", last="Иванов", phones=None, emails=None) -> dict:
    return {
        "ID": cid,
        "NAME": name,
        "LAST_NAME": last,
        "SECOND_NAME": "",
        "PHONE": [{"VALUE": p} for p in (phones or [])],
        "EMAIL": [{"VALUE": e} for e in (emails or [])],
        "SOURCE_ID": "5",
    }


class FakeBitrix:
    def __init__(self, *, comm_company=None, comm_contact=None, contact_companies=None,
                 company_deals=None, companies=None):
        self.comm_company = comm_company or {}      # phone10 -> [company_id]
        self.comm_contact = comm_contact or {}      # phone10 -> [contact_id]
        self.contact_companies = contact_companies or {}  # contact_id -> [company_id]
        self.company_deals = company_deals or {}    # company_id -> [deal dict]
        self.companies = companies or {}            # company_id -> dict
        self.updates: list[tuple] = []
        self.company_links: list[tuple] = []
        self.deal_links: list[tuple] = []

    def find_by_comm(self, comm_type, value, entity_type):
        key = value[-10:]
        if entity_type == "COMPANY":
            return [str(x) for x in self.comm_company.get(key, [])]
        if entity_type == "CONTACT":
            return [str(x) for x in self.comm_contact.get(key, [])]
        return []

    def list_contact_companies(self, contact_id):
        return [str(x) for x in self.contact_companies.get(str(contact_id), [])]

    def get_company(self, company_id):
        return self.companies.get(str(company_id), {"ID": company_id, "TITLE": f"Co {company_id}"})

    def list_company_deals(self, company_id):
        return self.company_deals.get(str(company_id), [])

    def update_contact(self, contact_id, fields):
        self.updates.append((str(contact_id), fields))
        return True

    def add_contact_company_relation(self, contact_id, company_id):
        self.company_links.append((str(contact_id), str(company_id)))
        return True

    def list_deal_contacts(self, deal_id):
        return []

    def add_deal_contact(self, deal_id, contact_id):
        self.deal_links.append((str(deal_id), str(contact_id)))
        return True


def test_junk_contact_is_skipped():
    bx = FakeBitrix()
    out = rob._plan_one(bx, _contact("1", name="Битрикс24", last="", phones=["+79991112233"]))
    assert out.status == "JUNK"


def test_no_phone_is_skipped():
    bx = FakeBitrix()
    out = rob._plan_one(bx, _contact("1", phones=[]))
    assert out.status == "NO_PHONE"


def test_direct_company_match():
    bx = FakeBitrix(comm_company={"9991112233": ["555"]},
                    company_deals={"555": [{"ID": "10", "CLOSED": "N"}, {"ID": "11", "CLOSED": "Y"}]})
    out = rob._plan_one(bx, _contact("1", phones=["+7 999 111-22-33"]))
    assert out.status == "MATCH_COMPANY"
    assert out.target_company_id == "555"
    assert out.target_deal_ids == ["10"]  # закрытая 11 не берётся


def test_match_via_contact_company():
    bx = FakeBitrix(comm_contact={"9991112233": ["2"]}, contact_companies={"2": ["777"]},
                    company_deals={"777": [{"ID": "20", "CLOSED": "N"}]})
    out = rob._plan_one(bx, _contact("1", phones=["+79991112233"]))
    assert out.status == "MATCH_VIA_CONTACT"
    assert out.target_company_id == "777"


def test_ambiguous_when_multiple_companies():
    bx = FakeBitrix(comm_company={"9991112233": ["1", "2"]})
    out = rob._plan_one(bx, _contact("1", phones=["+79991112233"]))
    assert out.status == "AMBIGUOUS"
    assert out.target_company_id == ""
    assert sorted(out.candidates) == ["1", "2"]


def test_no_match():
    bx = FakeBitrix()
    out = rob._plan_one(bx, _contact("1", phones=["+79991112233"]))
    assert out.status == "NO_MATCH"


def test_self_excluded_from_contact_match():
    # тот же телефон только у самого сироты → не считаем матчем
    bx = FakeBitrix(comm_contact={"9991112233": ["1"]})
    out = rob._plan_one(bx, _contact("1", phones=["+79991112233"]))
    assert out.status == "NO_MATCH"


def test_apply_binds_company_and_open_deals():
    bx = FakeBitrix(comm_company={"9991112233": ["555"]},
                    company_deals={"555": [{"ID": "10", "CLOSED": "N"}]})
    out = rob._plan_one(bx, _contact("1", phones=["+79991112233"]))
    rob._apply_one(bx, out)
    assert ("1", {"COMPANY_ID": "555"}) in bx.updates
    assert ("1", "555") in bx.company_links
    assert ("10", "1") in bx.deal_links


def test_run_batch_dry_run_does_not_write(monkeypatch):
    contacts = [_contact("1", phones=["+79991112233"])]
    bx = FakeBitrix(comm_company={"9991112233": ["555"]}, company_deals={"555": []})
    monkeypatch.setattr(bx, "list_contacts", lambda **kw: contacts, raising=False)
    summary = rob.run_batch(bx, dry_run=True, write_report=False)
    assert summary["total"] == 1
    assert summary["rebindable"] == 1
    assert bx.updates == [] and bx.deal_links == []
