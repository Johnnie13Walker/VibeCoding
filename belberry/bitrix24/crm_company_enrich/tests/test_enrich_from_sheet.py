from __future__ import annotations

import json
import sys
import types
from datetime import datetime
from zoneinfo import ZoneInfo

from crm_company_enrich.stages import enrich_from_sheet


class FakeSheets:
    sheet_id = "sheet"
    service_account_path = "service.json"

    def __init__(self, rows, links=None):
        self.rows = rows
        self.links = links or []
        self.updates = []

    def get_sheet_title_by_id(self, gid):
        return "Телемаркетинг без реквизитов" if gid == 1318170868 else None

    def read(self, tab, range_):
        return [list(row) for row in self.rows]

    def read_cell_hyperlinks(self, tab, range_):
        return self.links

    def update(self, tab, range_, rows, value_input_option="RAW"):
        self.updates.append((tab, range_, rows))
        if range_.startswith("A1:"):
            self.rows[0] = rows[0]


class FakeBitrix:
    def __init__(self, deals=None, companies=None):
        self.deals = {str(k): dict(v) for k, v in (deals or {}).items()}
        self.companies = {str(k): dict(v) for k, v in (companies or {}).items()}
        self.workflow_starts = []

    def get_deal(self, deal_id):
        deal = self.deals.get(str(deal_id))
        return dict(deal) if deal else None

    def get_company(self, company_id):
        company = self.companies.get(str(company_id))
        return dict(company) if company else None

    def start_workflow(self, template_id, document_type):
        self.workflow_starts.append((template_id, document_type))
        return {"workflow_id": "wf"}


def _rows(*data_rows):
    return [
        ["Сделка (название, гиперссылка в Б24)", "Воронка", "Ответственный", "Стадия сделки"],
        *data_rows,
    ]


def _links(*deal_ids):
    return [[""], *[[f"https://belberrycrm.bitrix24.ru/crm/deal/details/{deal_id}/"] for deal_id in deal_ids]]


def _deal(deal_id="100", company_id="10", **extra):
    return {
        "ID": deal_id,
        "COMPANY_ID": company_id,
        "STAGE_ID": "C50:NEW",
        "ASSIGNED_BY_ID": "2772",
        **extra,
    }


def _company(company_id="10", **extra):
    return {
        "ID": company_id,
        "TITLE": "ООО Тест",
        "UF_CRM_1735331882180": "7726672534",
        "UF_CRM_1737098549301": "50966000",
        **extra,
    }


def _patch_pipeline(monkeypatch, *, sync=None, reject=None, dedupe=None):
    from crm_company_enrich.stages import auto_reject_telemarketing, dedupe_contacts, sync_deals

    monkeypatch.setattr(
        sync_deals,
        "run",
        sync or (lambda *a, **k: {"failed": 0, "outcomes": [{"fields": {"UF": "value"}}]}),
    )
    monkeypatch.setattr(
        auto_reject_telemarketing,
        "run_deal",
        reject or (lambda *a, **k: {"failed": 0, "outcomes": [{"status": "SKIPPED"}]}),
    )
    monkeypatch.setattr(
        dedupe_contacts,
        "run_company",
        dedupe or (lambda *a, **k: {"failed": 0, "outcomes": [{"status": "NO_DUPLICATES"}]}),
    )


def test_dry_run_reads_sheet_but_does_not_write(monkeypatch):
    _patch_pipeline(monkeypatch)
    sheets = FakeSheets(_rows(["site.ru"]), _links("100"))
    bx = FakeBitrix(deals={"100": _deal()}, companies={"10": _company()})

    summary = enrich_from_sheet.run(bx, sheets, dry_run=True, limit=1)

    assert summary["examined"] == 1
    assert sheets.updates == []


def test_live_processes_single_deal_updates_row(monkeypatch):
    _patch_pipeline(monkeypatch)
    sheets = FakeSheets(_rows(["site.ru"]), _links("100"))
    bx = FakeBitrix(deals={"100": _deal()}, companies={"10": _company()})

    summary = enrich_from_sheet.run(bx, sheets, dry_run=False, limit=1, trigger_bp=False)

    assert summary["counts"] == {"ENRICHED": 1}
    assert any(update[1].startswith("A2:") for update in sheets.updates)
    row_update = [u for u in sheets.updates if u[1].startswith("A2:")][0][2][0]
    assert "100" in row_update
    assert "ENRICHED" in row_update


def test_skip_already_enriched_within_30_days(monkeypatch):
    _patch_pipeline(monkeypatch)
    now = datetime.now(ZoneInfo("Europe/Moscow")).isoformat(timespec="seconds")
    sheets = FakeSheets([
        ["Сделка", "enriched_at", "status"],
        ["site.ru", now, "ENRICHED"],
    ], _links("100"))
    bx = FakeBitrix(deals={"100": _deal()}, companies={"10": _company()})

    summary = enrich_from_sheet.run(bx, sheets, dry_run=True)

    assert summary["examined"] == 0
    assert summary["skipped_rows"] == 1


def test_missing_deal_id_in_row_skipped(monkeypatch):
    _patch_pipeline(monkeypatch)
    sheets = FakeSheets(_rows(["site.ru"]), [[""], [""]])
    bx = FakeBitrix()

    summary = enrich_from_sheet.run(bx, sheets, dry_run=True)

    assert summary["examined"] == 0
    assert summary["skipped_rows"] == 1


def test_deal_not_found_in_bitrix_marked_NO_DEAL(monkeypatch):
    _patch_pipeline(monkeypatch)
    sheets = FakeSheets(_rows(["site.ru"]), _links("404"))
    bx = FakeBitrix()

    summary = enrich_from_sheet.run(bx, sheets, dry_run=True, limit=1)

    assert summary["counts"] == {"NO_DEAL": 1}
    assert summary["outcomes"][0]["error"] == "deal not found"


def test_auto_reject_low_revenue_marks_REJECTED(monkeypatch):
    _patch_pipeline(
        monkeypatch,
        reject=lambda *a, **k: {
            "failed": 0,
            "outcomes": [{"status": "DRY_RUN", "reason_id": "8542", "reason_desc": "выручка <30M"}],
        },
    )
    sheets = FakeSheets(_rows(["site.ru"]), _links("100"))
    bx = FakeBitrix(deals={"100": _deal()}, companies={"10": _company(UF_CRM_1737098549301="10000000")})

    summary = enrich_from_sheet.run(bx, sheets, dry_run=True, limit=1)

    assert summary["counts"] == {"REJECTED": 1}
    assert summary["outcomes"][0]["rejected_reason"] == "выручка <30M"


def test_director_inn_enriched_when_match_found(monkeypatch):
    _patch_pipeline(monkeypatch)
    module = types.SimpleNamespace(
        run_company=lambda *a, **k: {"director_inn": "770100000001", "outcomes": [{"director_inn": "770100000001"}]}
    )
    monkeypatch.setitem(sys.modules, "crm_company_enrich.stages.enrich_director_inn", module)
    sheets = FakeSheets(_rows(["site.ru"]), _links("100"))
    bx = FakeBitrix(deals={"100": _deal()}, companies={"10": _company()})

    summary = enrich_from_sheet.run(bx, sheets, dry_run=True, limit=1)

    assert summary["outcomes"][0]["director_inn"] == "770100000001"


def test_failed_sync_deals_marks_FAILED_with_error(monkeypatch):
    _patch_pipeline(monkeypatch, sync=lambda *a, **k: {"failed": 1, "outcomes": [{"error": "sync boom"}]})
    sheets = FakeSheets(_rows(["site.ru"]), _links("100"))
    bx = FakeBitrix(deals={"100": _deal()}, companies={"10": _company()})

    summary = enrich_from_sheet.run(bx, sheets, dry_run=True, limit=1)

    assert summary["counts"] == {"FAILED": 1}
    assert "sync boom" in summary["outcomes"][0]["error"]


def test_limit_respects(monkeypatch):
    _patch_pipeline(monkeypatch)
    sheets = FakeSheets(_rows(["a"], ["b"], ["c"]), _links("100", "101", "102"))
    bx = FakeBitrix(
        deals={str(i): _deal(str(i)) for i in (100, 101, 102)},
        companies={"10": _company()},
    )

    summary = enrich_from_sheet.run(bx, sheets, dry_run=True, limit=2)

    assert summary["examined"] == 2
    assert [o["deal_id"] for o in summary["outcomes"]] == ["100", "101"]


def test_resume_continues_from_last_checkpoint(monkeypatch, tmp_path):
    _patch_pipeline(monkeypatch)
    progress = tmp_path / "progress.json"
    monkeypatch.setattr(enrich_from_sheet, "PROGRESS_PATH", progress)
    progress.write_text(json.dumps({"last_row_processed": 2}), encoding="utf-8")
    sheets = FakeSheets(_rows(["a"], ["b"]), _links("100", "101"))
    bx = FakeBitrix(deals={"100": _deal("100"), "101": _deal("101")}, companies={"10": _company()})

    summary = enrich_from_sheet.run(bx, sheets, dry_run=True, resume=True)

    assert [o["deal_id"] for o in summary["outcomes"]] == ["101"]


def test_csv_audit_written_for_each_outcome(monkeypatch, tmp_path):
    _patch_pipeline(monkeypatch)
    audit = tmp_path / "audit.csv"
    monkeypatch.setattr(enrich_from_sheet, "AUDIT_PATH", audit)
    sheets = FakeSheets(_rows(["a"], ["b"]), _links("100", "101"))
    bx = FakeBitrix(deals={"100": _deal("100"), "101": _deal("101")}, companies={"10": _company()})

    enrich_from_sheet.run(bx, sheets, dry_run=True, limit=2)

    lines = audit.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert "100" in lines[1]
    assert "101" in lines[2]
