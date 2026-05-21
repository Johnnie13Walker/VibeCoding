from __future__ import annotations

import sys
import types
from datetime import date, timedelta

import pytest

from crm_company_enrich.config import COMPANY_UF_CITY, COMPANY_UF_ORGANIZATION_STATUS, COMPANY_UF_REGION
from crm_company_enrich.stages import enrich_company_full as stage


class FakeBitrix:
    def __init__(
        self,
        *,
        companies=None,
        deals=None,
        requisites=None,
        search_requisites=None,
    ):
        self.companies = {str(k): dict(v) for k, v in (companies or {}).items()}
        self.deals = {str(k): dict(v) for k, v in (deals or {}).items()}
        self.requisites = {str(k): [dict(r) for r in v] for k, v in (requisites or {}).items()}
        self.search_requisites = [dict(r) for r in (search_requisites or [])]
        self.updated_companies = []
        self.updated_deals = []
        self.added_requisites = []
        self.started_workflows = []
        self.added_companies = []
        self.added_deals = []
        self.timeline_comments = []

    def get_company(self, company_id):
        company = self.companies.get(str(company_id))
        return dict(company) if company else None

    def list_companies(self, select=None, filter_=None):
        return [dict(c) for c in self.companies.values()]

    def add_company(self, fields, params=None):
        company_id = str(90000 + len(self.added_companies))
        self.added_companies.append((dict(fields), dict(params or {})))
        self.companies[company_id] = {"ID": company_id, **fields}
        return company_id

    def update_company(self, company_id, fields):
        self.updated_companies.append((str(company_id), dict(fields)))
        self.companies.setdefault(str(company_id), {"ID": str(company_id)}).update(fields)
        return True

    def get_deal(self, deal_id):
        deal = self.deals.get(str(deal_id))
        return dict(deal) if deal else None

    def list_company_deals(self, company_id, select=None):
        return [dict(d) for d in self.deals.values() if str(d.get("COMPANY_ID")) == str(company_id)]

    def add_deal(self, fields, params=None):
        deal_id = str(80000 + len(self.added_deals))
        self.added_deals.append((dict(fields), dict(params or {})))
        self.deals[deal_id] = {"ID": deal_id, **fields}
        return deal_id

    def update_deal(self, deal_id, fields, params=None):
        self.updated_deals.append((str(deal_id), dict(fields), dict(params or {})))
        self.deals.setdefault(str(deal_id), {"ID": str(deal_id)}).update(fields)
        return True

    def list_company_requisites(self, company_id):
        return [dict(r) for r in self.requisites.get(str(company_id), [])]

    def search_requisite_by_inn(self, inn):
        return [dict(r) for r in self.search_requisites if str(r.get("RQ_INN")) == str(inn)]

    def add_requisite(self, fields):
        req_id = str(70000 + len(self.added_requisites))
        self.added_requisites.append(dict(fields))
        self.requisites.setdefault(str(fields["ENTITY_ID"]), []).append({"ID": req_id, **fields})
        return req_id

    def start_workflow(self, template_id, document_type):
        self.started_workflows.append((template_id, list(document_type)))
        return {"workflow_id": f"wf-{template_id}"}

    def add_timeline_comment(self, *, owner_type_id, owner_id, text):
        self.timeline_comments.append({"owner_type_id": owner_type_id, "owner_id": str(owner_id), "text": text})
        return "timeline-1"

    def list_active_users(self):
        return {"2772", "2832"}


def company(company_id="10", **extra):
    data = {
        "ID": str(company_id),
        "TITLE": "ООО Тест",
        "WEB": [{"VALUE": "https://test.ru"}],
        "UF_CRM_1735331882180": "7720238793",
        "UF_CRM_ORG_STATUS": "8850",
        "UF_CRM_1737098549301": "105000000",
        COMPANY_UF_CITY: "Москва",
        COMPANY_UF_REGION: "9234",
    }
    data.update(extra)
    return data


def deal(deal_id="100", company_id="10", **extra):
    data = {
        "ID": str(deal_id),
        "TITLE": "Тестовая сделка",
        "COMPANY_ID": str(company_id),
        "CATEGORY_ID": "50",
        "STAGE_ID": "C50:NEW",
        "CLOSED": "N",
        "ASSIGNED_BY_ID": "2772",
    }
    data.update(extra)
    return data


def req(company_id="10", inn="7720238793", **extra):
    data = {"ID": "500", "ENTITY_ID": str(company_id), "RQ_INN": inn, "RQ_OGRN": "1027700000000"}
    data.update(extra)
    return data


def test_write_audit_does_not_add_deal_timeline_comment():
    bx = FakeBitrix()
    outcome = stage.FullEnrichmentOutcome(
        input_kind="deal_id",
        input_value="100",
        company_id="10",
        deal_id="100",
    )

    step = stage._step_write_audit(bx, outcome, {}, {"dry_run": False})

    assert step.status == "DONE"
    assert bx.timeline_comments == []


@pytest.fixture(autouse=True)
def no_network(monkeypatch, tmp_path):
    monkeypatch.setattr(stage, "AUDIT_PATH", tmp_path / "enrich_company_full.csv")
    monkeypatch.setattr(stage, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(stage.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(stage.sync_deals, "fetch_rusprofile_html", lambda inn: "")
    monkeypatch.setattr(stage.sync_deals, "parse_organization_status", lambda html: "")
    monkeypatch.setattr(stage.enrich_web, "try_web", lambda *a, **k: (None, None))
    monkeypatch.setattr(stage.enrich_web, "try_rusprofile", lambda *a, **k: (None, None, []))
    monkeypatch.setattr(stage.sync_deals, "run_company", lambda *a, **k: {"failed": 0, "outcomes": [{"status": "DRY_RUN"}]})
    monkeypatch.setattr(stage.sync_deals, "run", lambda *a, **k: {"failed": 0, "outcomes": [{"status": "DRY_RUN"}]})
    monkeypatch.setattr(stage.dedupe_contacts, "run_company", lambda *a, **k: {"failed": 0, "outcomes": [{"status": "NO_DUPLICATES"}]})
    monkeypatch.setattr(stage.telemarketing_dedupe, "run_company", lambda *a, **k: {"failed": 0, "unresolved": 0, "outcomes": [{"status": "NO_DUPLICATES"}]})
    monkeypatch.setattr(stage.auto_reject_telemarketing, "run_deal", lambda *a, **k: {"failed": 0, "outcomes": [{"status": "DRY_RUN"}]})


def test_resolve_by_company_id():
    bx = FakeBitrix(companies={"10": company()}, requisites={"10": [req()]})
    out = stage.run(bx, company_id="10")
    assert out.company_id == "10"
    assert out.steps[0].status == "DONE"


def test_resolve_by_deal_id_finds_company():
    bx = FakeBitrix(companies={"10": company()}, deals={"100": deal()}, requisites={"10": [req()]})
    out = stage.run(bx, deal_id="100")
    assert out.company_id == "10"
    assert out.deal_id == "100"


def test_resolve_by_inn_via_requisite():
    bx = FakeBitrix(companies={"10": company()}, requisites={"10": [req()]}, search_requisites=[req()])
    out = stage.run(bx, inn="7720238793")
    assert out.company_id == "10"


def test_resolve_by_url_via_web_field():
    bx = FakeBitrix(companies={"10": company(WEB=[{"VALUE": "https://zublechit.ru"}])}, requisites={"10": [req()]})
    out = stage.run(bx, url="https://zublechit.ru/")
    assert out.company_id == "10"


def test_resolve_fails_without_create_if_missing():
    out = stage.run(FakeBitrix(), url="https://missing.ru")
    assert out.final_status == "FAILED"


def test_create_if_missing_creates_minimum_company():
    bx = FakeBitrix()
    out = stage.run(bx, inn="7720238793", create_if_missing=True, dry_run=False, skip_bp=True, bizproc_wait_s=0)
    assert out.company_id in bx.companies
    assert bx.added_companies


def test_create_if_missing_skips_without_inn():
    bx = FakeBitrix(deals={"100": deal(company_id="")})

    out = stage.run(
        bx,
        deal_id="100",
        url="https://missing-inn.ru",
        create_if_missing=True,
        dry_run=False,
        skip_bp=True,
        bizproc_wait_s=0,
    )

    assert out.final_status == "SKIPPED"
    assert "no_inn_no_company" in out.flags
    assert bx.added_companies == []
    assert bx.updated_deals == []


def test_deal_without_company_skips_creation_when_inn_missing():
    sync_company_calls = []
    sync_deal_calls = []
    stage.sync_deals.run_company = lambda *a, **k: sync_company_calls.append(k) or {"failed": 0, "outcomes": [{"status": "DRY_RUN"}]}
    stage.sync_deals.run = lambda *a, **k: sync_deal_calls.append(k) or {"failed": 0, "outcomes": [{"status": "DRY_RUN"}]}
    bx = FakeBitrix(deals={"100": deal(company_id="")})

    out = stage.run(
        bx,
        deal_id="100",
        url="https://kankadze.school",
        create_if_missing=True,
        dry_run=False,
        skip_bp=True,
        skip_dedupe_contacts=True,
        skip_director_inn=True,
        skip_telemarketing_dedupe=True,
        bizproc_wait_s=0,
    )

    assert out.final_status == "SKIPPED"
    assert out.company_id == ""
    assert bx.added_companies == []
    assert bx.updated_deals == []
    assert sync_company_calls == []
    assert sync_deal_calls == []


def test_deal_without_company_creates_company_only_after_inn_found(monkeypatch):
    sync_company_calls = []
    sync_deal_calls = []
    stage.sync_deals.run_company = lambda *a, **k: sync_company_calls.append(k) or {"failed": 0, "outcomes": [{"status": "DRY_RUN"}]}
    stage.sync_deals.run = lambda *a, **k: sync_deal_calls.append(k) or {"failed": 0, "outcomes": [{"status": "DRY_RUN"}]}
    monkeypatch.setattr(stage.enrich_web, "try_web", lambda *a, **k: ("7720238793", "ООО Тест"))
    bx = FakeBitrix(deals={"100": deal(company_id="")})

    out = stage.run(
        bx,
        deal_id="100",
        url="https://kankadze.school",
        create_if_missing=True,
        dry_run=False,
        skip_bp=True,
        skip_dedupe_contacts=True,
        skip_director_inn=True,
        skip_telemarketing_dedupe=True,
        bizproc_wait_s=0,
    )

    assert out.company_id in bx.companies
    assert bx.added_companies[0][0]["TITLE"] == "kankadze.school"
    assert bx.added_companies[0][0]["WEB"] == [{"VALUE": "https://kankadze.school", "VALUE_TYPE": "WORK"}]
    assert bx.added_companies[0][0]["UF_CRM_5DEF838D882A2"] == "https://kankadze.school"
    assert bx.added_companies[0][0]["UF_CRM_1735331882180"] == "7720238793"
    assert bx.updated_deals[0][0] == "100"
    assert bx.updated_deals[0][1] == {"COMPANY_ID": out.company_id}
    assert bx.added_deals == []
    assert _step(out, "RESOLVE_DEAL").details["attached_input_deal"] is True
    assert sync_company_calls[-1]["company_id"] == out.company_id
    assert sync_company_calls[-1]["site"] == "https://kankadze.school"
    assert sync_deal_calls[-1]["telemarketing_workflow"] is True


def test_deal_without_company_reuses_existing_company_by_found_inn(monkeypatch):
    sync_company_calls = []
    sync_deal_calls = []
    stage.sync_deals.run_company = lambda *a, **k: sync_company_calls.append(k) or {"failed": 0, "outcomes": [{"status": "DRY_RUN"}]}
    stage.sync_deals.run = lambda *a, **k: sync_deal_calls.append(k) or {"failed": 0, "outcomes": [{"status": "DRY_RUN"}]}
    monkeypatch.setattr(stage.enrich_web, "try_web", lambda *a, **k: ("2614018356", "ООО Фирма Феррум"))
    bx = FakeBitrix(
        companies={"24208": company("24208", TITLE='ООО ФИРМА "ФЕРРУМ"')},
        deals={"10996": deal("10996", company_id="")},
        requisites={"24208": [req("24208", inn="2614018356")]},
        search_requisites=[req("24208", inn="2614018356")],
    )

    out = stage.run(
        bx,
        deal_id="10996",
        url="https://ferrum-sk.ru",
        create_if_missing=True,
        dry_run=False,
        skip_bp=True,
        skip_dedupe_contacts=True,
        skip_director_inn=True,
        skip_telemarketing_dedupe=True,
        bizproc_wait_s=0,
    )

    assert out.company_id == "24208"
    assert bx.added_companies == []
    assert bx.updated_deals[0][0] == "10996"
    assert bx.updated_deals[0][1] == {"COMPANY_ID": "24208"}
    assert sync_company_calls[-1]["company_id"] == "24208"
    assert sync_deal_calls[-1]["deal_id"] == "10996"


def test_dry_run_created_company_reuses_context_without_bitrix_get():
    class StrictBitrix(FakeBitrix):
        def get_company(self, company_id):
            if str(company_id) == "DRY_RUN_COMPANY":
                raise AssertionError("dry-run must not fetch fake company from Bitrix")
            return super().get_company(company_id)

    bx = StrictBitrix(deals={"100": deal(company_id="")})
    out = stage.run(
        bx,
        deal_id="100",
        url="https://kankadze.school",
        create_if_missing=True,
        dry_run=True,
        skip_bp=True,
        skip_dedupe_contacts=True,
        skip_director_inn=True,
        skip_telemarketing_dedupe=True,
        skip_auto_reject=True,
        bizproc_wait_s=0,
    )

    assert out.company_id == ""
    assert out.final_status == "SKIPPED"


def test_find_site_writes_web_if_empty():
    bx = FakeBitrix(companies={"10": company(WEB=[])}, requisites={"10": [req()]})
    out = stage.run(bx, company_id="10", url="", dry_run=False, skip_bp=True, bizproc_wait_s=0)
    assert _step(out, "FIND_SITE").status == "SKIPPED"


def test_find_site_skipped_if_present():
    bx = FakeBitrix(companies={"10": company(WEB=[{"VALUE": "https://test.ru"}])}, requisites={"10": [req()]})
    out = stage.run(bx, company_id="10")
    assert _step(out, "FIND_SITE").details["reason"] == "already_present"


def test_find_inn_from_site_html(monkeypatch):
    monkeypatch.setattr(stage.enrich_web, "try_web", lambda *a, **k: ("7720238793", "ООО"))
    bx = FakeBitrix(companies={"10": company(UF_CRM_1735331882180="")})
    out = stage.run(bx, company_id="10", skip_bp=True)
    assert _step(out, "FIND_INN").details["source"] == "web"


def test_find_inn_from_rusprofile_fallback(monkeypatch):
    monkeypatch.setattr(stage.enrich_web, "try_rusprofile", lambda *a, **k: ("7720238793", "ООО", []))
    bx = FakeBitrix(companies={"10": company(WEB=[], UF_CRM_1735331882180="")})
    out = stage.run(bx, company_id="10", skip_bp=True)
    assert _step(out, "FIND_INN").details["source"] == "rusprofile"


def test_no_inn_found_continues_without_block():
    bx = FakeBitrix(companies={"10": company(WEB=[], UF_CRM_1735331882180="")})
    out = stage.run(bx, company_id="10")
    assert "no_inn_found" in out.flags
    assert out.final_status in {"ENRICHED", "PARTIAL", "SKIPPED"}


def test_duplicate_inn_on_another_company_flagged_not_blocked():
    bx = FakeBitrix(companies={"10": company()}, requisites={"10": [req()]}, search_requisites=[req("10"), req("20")])
    out = stage.run(bx, company_id="10")
    assert out.duplicate_company_ids == ["20"]
    assert "duplicate_inn" in out.flags


def test_apply_inn_creates_requisite():
    bx = FakeBitrix(companies={"10": company()}, requisites={"10": []})
    out = stage.run(bx, company_id="10", dry_run=False, skip_bp=True, bizproc_wait_s=0)
    assert bx.added_requisites
    assert _step(out, "APPLY_INN").status == "DONE"


def test_apply_inn_skipped_if_exists():
    bx = FakeBitrix(companies={"10": company()}, requisites={"10": [req()]})
    out = stage.run(bx, company_id="10")
    assert _step(out, "APPLY_INN").status == "SKIPPED"


def test_run_bp_calls_5938_then_8612_for_first_entry():
    bx = FakeBitrix(companies={"10": company()}, requisites={"10": []})
    stage.run(bx, company_id="10", dry_run=False, bizproc_wait_s=0)
    assert [x[0] for x in bx.started_workflows] == [5938, 8612]


def test_run_bp_calls_only_8612_for_existing_inn():
    bx = FakeBitrix(companies={"10": company()}, requisites={"10": [req()]})
    stage.run(bx, company_id="10", dry_run=False, bizproc_wait_s=0)
    assert [x[0] for x in bx.started_workflows] == [8612]


def test_skip_bp_flag_does_not_start_workflow():
    bx = FakeBitrix(companies={"10": company()}, requisites={"10": [req()]})
    out = stage.run(bx, company_id="10", dry_run=False, skip_bp=True, bizproc_wait_s=0)
    assert bx.started_workflows == []
    assert _step(out, "RUN_BP").status == "SKIPPED"


def test_liquidated_company_with_deal_marks_REJECTED():
    bx = FakeBitrix(companies={"10": company(UF_CRM_ORG_STATUS="8852")}, deals={"100": deal()}, requisites={"10": [req()]})
    out = stage.run(bx, company_id="10")
    assert out.final_status == "REJECTED"
    assert out.deal_id == "100"


def test_stale_liquidated_company_rechecked_before_auto_reject(monkeypatch):
    monkeypatch.setattr(stage.sync_deals, "fetch_rusprofile_html", lambda inn: "<span>Действующая организация</span>")
    monkeypatch.setattr(stage.sync_deals, "parse_organization_status", lambda html: "Действующая")
    bx = FakeBitrix(companies={"10": company(UF_CRM_ORG_STATUS="8852")}, deals={"100": deal()}, requisites={"10": [req()]})

    out = stage.run(bx, company_id="10", dry_run=False, skip_bp=True, bizproc_wait_s=0)

    assert out.final_status != "REJECTED"
    assert bx.companies["10"][COMPANY_UF_ORGANIZATION_STATUS] == "8850"
    assert ("10", {COMPANY_UF_ORGANIZATION_STATUS: "8850"}) in bx.updated_companies
    step = _step(out, "RANK_DEAL_VIABILITY")
    assert step.details["decision"] == "continue"
    assert step.details["liquidated_status_recheck"]["status"] == "restored_active"


def test_low_revenue_with_deal_marks_REJECTED():
    bx = FakeBitrix(companies={"10": company(UF_CRM_1737098549301="10000000")}, deals={"100": deal()}, requisites={"10": [req()]})
    out = stage.run(bx, company_id="10")
    assert out.final_status == "REJECTED"


def test_liquidated_no_deal_marks_SKIPPED():
    bx = FakeBitrix(companies={"10": company(UF_CRM_ORG_STATUS="8852")}, requisites={"10": [req()]})
    out = stage.run(bx, company_id="10")
    assert out.final_status == "SKIPPED"


def test_no_deal_creates_in_C50_NEW_with_rotation():
    bx = FakeBitrix(companies={"10": company()}, requisites={"10": [req()]})
    out = stage.run(bx, company_id="10", dry_run=False, skip_bp=True, bizproc_wait_s=0)
    assert bx.added_deals
    assert bx.added_deals[0][0]["STAGE_ID"] == "C50:NEW"
    assert out.deal_id


def test_create_deal_skipped_when_no_site():
    bx = FakeBitrix(companies={"10": company(WEB=[])}, requisites={"10": [req()]})
    out = stage.run(bx, company_id="10", dry_run=False, skip_bp=True, bizproc_wait_s=0)
    assert "no_site_skipped" in out.flags
    assert out.final_status == "SKIPPED"
    assert _step(out, "CREATE_DEAL").status == "SKIPPED"
    assert _step(out, "CREATE_DEAL").details["reason"] == "no_site_skipped"
    assert bx.added_deals == []


def test_active_deal_triggers_sync(monkeypatch):
    called = {}
    monkeypatch.setattr(stage.sync_deals, "run", lambda *a, **k: called.setdefault("kwargs", k) or {"failed": 0, "outcomes": []})
    bx = FakeBitrix(companies={"10": company()}, deals={"100": deal()}, requisites={"10": [req()]})
    stage.run(bx, company_id="10")
    assert called["kwargs"]["deal_id"] == "100"


def test_lose_with_passed_date_revives():
    due = (date.today() - timedelta(days=1)).isoformat()
    bx = FakeBitrix(companies={"10": company()}, deals={"100": deal(STAGE_ID="C50:LOSE", CLOSED="Y", **{"UF_CRM_1770901971": due})}, requisites={"10": [req()]})
    out = stage.run(bx, company_id="10")
    assert _step(out, "REVIVE_DEAL").status == "DONE"


def test_apology_within_cooldown_skipped():
    bx = FakeBitrix(companies={"10": company()}, deals={"100": deal(STAGE_ID="C50:APOLOGY", CLOSED="Y", UF_CRM_1771324790="8540", CLOSEDATE=date.today().isoformat())}, requisites={"10": [req()]})
    out = stage.run(bx, company_id="10")
    assert out.final_status == "SKIPPED"


def test_apology_after_cooldown_reactivates():
    old = (date.today() - timedelta(days=400)).isoformat()
    bx = FakeBitrix(companies={"10": company()}, deals={"100": deal(STAGE_ID="C50:APOLOGY", CLOSED="Y", UF_CRM_1771324790="8540", CLOSEDATE=old)}, requisites={"10": [req()]})
    out = stage.run(bx, company_id="10")
    assert _step(out, "REVIVE_DEAL").status == "DONE"


def test_dedupe_contacts_called_after_bp(monkeypatch):
    calls = []
    monkeypatch.setattr(stage.dedupe_contacts, "run_company", lambda *a, **k: calls.append("dedupe") or {"failed": 0})
    bx = FakeBitrix(companies={"10": company()}, requisites={"10": [req()]})
    out = stage.run(bx, company_id="10")
    assert calls == ["dedupe"]
    assert _step_index(out, "RUN_BP") < _step_index(out, "DEDUPE_CONTACTS")


def test_director_inn_skipped_when_flag_set():
    bx = FakeBitrix(companies={"10": company()}, requisites={"10": [req()]})
    out = stage.run(bx, company_id="10", skip_director_inn=True)
    step = _step(out, "ENRICH_DIRECTOR_INN")
    assert step.status == "SKIPPED"
    assert step.details["reason"] == "skip_director_inn"


def test_telemarketing_dedupe_called_for_multiple_open_deals(monkeypatch):
    called = {}
    monkeypatch.setattr(stage.telemarketing_dedupe, "run_company", lambda *a, **k: called.setdefault("yes", True) or {"failed": 0, "unresolved": 0})
    bx = FakeBitrix(companies={"10": company()}, deals={"100": deal("100"), "101": deal("101")}, requisites={"10": [req()]})
    stage.run(bx, company_id="10", skip_director_inn=True)
    assert called["yes"] is True


def test_dry_run_does_not_call_any_write():
    bx = FakeBitrix(companies={"10": company()}, requisites={"10": [req()]})
    stage.run(bx, company_id="10")
    assert bx.updated_companies == []
    assert bx.updated_deals == []
    assert bx.added_companies == []
    assert bx.added_deals == []
    assert bx.added_requisites == []
    assert bx.started_workflows == []


def test_full_pipeline_returns_outcome_with_all_steps_recorded():
    bx = FakeBitrix(companies={"10": company()}, deals={"100": deal()}, requisites={"10": [req()]})
    out = stage.run(bx, company_id="10", skip_director_inn=True)
    assert len(out.steps) >= 19
    assert out.final_status == "ENRICHED"


def test_audit_csv_written_in_live_mode(tmp_path):
    bx = FakeBitrix(companies={"10": company()}, deals={"100": deal()}, requisites={"10": [req()]})
    stage.run(bx, company_id="10", dry_run=False, skip_bp=True, bizproc_wait_s=0)
    assert stage.AUDIT_PATH.exists()
    assert "company_id" in stage.AUDIT_PATH.read_text(encoding="utf-8").splitlines()[0]


def _step(out, name):
    return next(s for s in out.steps if s.step == name)


def _step_index(out, name):
    return [s.step for s in out.steps].index(name)
