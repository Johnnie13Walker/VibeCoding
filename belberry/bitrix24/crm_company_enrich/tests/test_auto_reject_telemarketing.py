from __future__ import annotations

from crm_company_enrich.config import (
    HOLD_MARKER_FLAG_FIELD,
    HOLD_REASON_COMMENT_FIELD,
    HOLD_REASON_FIELD,
    TELEMARKETING_AUTO_REJECT_SCAN_STAGES,
)
from crm_company_enrich.stages import auto_reject_telemarketing as stage


class FakeBitrix:
    def __init__(self, *, deals: list[dict], companies: dict[str, dict | None]):
        self.deals = deals
        self.companies = companies
        self.update_deal_calls: list[tuple[str, dict, dict | None]] = []
        self.timeline_calls: list[dict] = []
        self.list_calls: list[dict] = []

    def list_deals_by_stages(self, *, category_id, stage_ids, closed="N", select=None):
        self.list_calls.append({"category_id": category_id, "stage_ids": stage_ids, "closed": closed})
        return [
            deal for deal in self.deals
            if str(deal.get("CATEGORY_ID") or "") == str(category_id)
            and str(deal.get("STAGE_ID") or "") in set(stage_ids)
            and str(deal.get("CLOSED") or "N") == closed
        ]

    def get_company(self, company_id):
        return self.companies.get(str(company_id))

    def update_deal(self, deal_id, fields, *, params=None):
        self.update_deal_calls.append((str(deal_id), dict(fields), dict(params or {})))
        return True

    def add_timeline_comment(self, *, owner_type_id, owner_id, text):
        self.timeline_calls.append({"owner_type_id": owner_type_id, "owner_id": str(owner_id), "text": text})
        return "timeline-1"


class BatchFakeBitrix(FakeBitrix):
    def __init__(self, *, deals: list[dict], companies: dict[str, dict | None], batch_result: dict, raise_get_company: set[str] | None = None):
        super().__init__(deals=deals, companies=companies)
        self.batch_result = batch_result
        self.raise_get_company = raise_get_company or set()
        self.get_company_calls: list[str] = []

    def batch(self, commands):
        return dict(self.batch_result)

    def get_company(self, company_id):
        self.get_company_calls.append(str(company_id))
        if str(company_id) in self.raise_get_company:
            raise RuntimeError(f"get failed for {company_id}")
        return super().get_company(company_id)


def _deal(deal_id="100", company_id="10", stage_id="C50:NEW", **extra):
    return {
        "ID": deal_id,
        "TITLE": "Тестовая сделка",
        "COMPANY_ID": company_id,
        "CATEGORY_ID": "50",
        "STAGE_ID": stage_id,
        "CLOSED": "N",
        "ASSIGNED_BY_ID": "2772",
        **extra,
    }


def _run_live(monkeypatch, tmp_path, bx, **kwargs):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    return stage.run(bx, dry_run=False, **kwargs)


def test_liquidated_company_moves_deal_to_apology_8538(monkeypatch, tmp_path):
    bx = FakeBitrix(
        deals=[_deal()],
        companies={"10": {"UF_CRM_ORG_STATUS": "8852", "REVENUE": "50000000"}},
    )

    summary = _run_live(monkeypatch, tmp_path, bx)
    fields = bx.update_deal_calls[0][1]

    assert summary["rejected_8538"] == 1
    assert fields["STAGE_ID"] == "C50:APOLOGY"
    assert fields[HOLD_REASON_FIELD] == "8538"
    assert fields["CLOSED"] == "Y"
    assert fields[HOLD_MARKER_FLAG_FIELD] == "1"


def test_low_revenue_moves_deal_to_apology_8542(monkeypatch, tmp_path):
    bx = FakeBitrix(
        deals=[_deal()],
        companies={"10": {"UF_CRM_ORG_STATUS": "8850", "UF_CRM_1737098549301": "15000000"}},
    )

    summary = _run_live(monkeypatch, tmp_path, bx)
    fields = bx.update_deal_calls[0][1]

    assert summary["rejected_8542"] == 1
    assert fields["STAGE_ID"] == "C50:APOLOGY"
    assert fields[HOLD_REASON_FIELD] == "8542"
    assert "15 000 000" in fields[HOLD_REASON_COMMENT_FIELD]


def test_revenue_above_threshold_not_rejected():
    bx = FakeBitrix(
        deals=[_deal()],
        companies={"10": {"UF_CRM_ORG_STATUS": "8850", "UF_CRM_1737098549301": "50000000"}},
    )

    summary = stage.run(bx)

    assert summary["skipped"] == 1
    assert bx.update_deal_calls == []


def test_revenue_unknown_not_rejected():
    bx = FakeBitrix(deals=[_deal()], companies={"10": {"UF_CRM_ORG_STATUS": "8850"}})

    summary = stage.run(bx)

    assert summary["skipped"] == 1
    assert bx.update_deal_calls == []


def test_active_company_with_no_signals_not_rejected():
    bx = FakeBitrix(
        deals=[_deal()],
        companies={"10": {"UF_CRM_ORG_STATUS": "8850", "REVENUE": "50000000"}},
    )

    summary = stage.run(bx)

    assert summary["skipped"] == 1
    assert bx.update_deal_calls == []


def test_already_auto_rejected_skipped():
    bx = FakeBitrix(
        deals=[_deal(**{HOLD_MARKER_FLAG_FIELD: "1"})],
        companies={"10": {"UF_CRM_ORG_STATUS": "8852"}},
    )

    summary = stage.run(bx)

    assert summary["skipped"] == 1
    assert summary["outcomes"][0]["skipped_reason"] == "already_auto_rejected"
    assert bx.update_deal_calls == []


def test_preparation_stage_filtered_out():
    bx = FakeBitrix(
        deals=[_deal(stage_id="C50:PREPARATION")],
        companies={"10": {"UF_CRM_ORG_STATUS": "8852"}},
    )

    summary = stage.run(bx, stages=["C50:PREPARATION"])

    assert summary["scan_stages"] == []
    assert summary["examined"] == 0
    assert bx.list_calls == []


def test_won_stage_filtered_out():
    bx = FakeBitrix(
        deals=[_deal(stage_id="C50:WON")],
        companies={"10": {"UF_CRM_ORG_STATUS": "8852"}},
    )

    summary = stage.run(bx, stages=["C50:WON"])

    assert summary["scan_stages"] == []
    assert summary["examined"] == 0
    assert bx.list_calls == []


def test_dry_run_does_not_write():
    bx = FakeBitrix(
        deals=[_deal()],
        companies={"10": {"UF_CRM_ORG_STATUS": "8852"}},
    )

    summary = stage.run(bx, dry_run=True)

    assert summary["dry_run_8538"] == 1
    assert summary["outcomes"][0]["status"] == "DRY_RUN"
    assert bx.update_deal_calls == []
    assert bx.timeline_calls == []


def test_live_writes_deal_and_timeline(monkeypatch, tmp_path):
    bx = FakeBitrix(
        deals=[_deal()],
        companies={"10": {"UF_CRM_ORG_STATUS": "8852"}},
    )

    summary = _run_live(monkeypatch, tmp_path, bx)

    assert summary["rejected"] == 1
    assert len(bx.update_deal_calls) == 1
    assert len(bx.timeline_calls) == 1
    assert bx.timeline_calls[0]["text"].startswith("[auto-reject] 8538:")


def test_no_company_returns_no_company_status():
    bx = FakeBitrix(deals=[_deal(company_id="0")], companies={})

    summary = stage.run(bx)

    assert summary["no_company"] == 1
    assert summary["outcomes"][0]["status"] == "NO_COMPANY"
    assert bx.update_deal_calls == []


def test_update_deal_passes_register_sonet_event_param(monkeypatch, tmp_path):
    bx = FakeBitrix(
        deals=[_deal()],
        companies={"10": {"UF_CRM_ORG_STATUS": "8852"}},
    )

    _run_live(monkeypatch, tmp_path, bx)

    assert bx.update_deal_calls[0][2] == {"REGISTER_SONET_EVENT": "Y"}


def test_multiple_deals_summary_aggregates_by_reason(monkeypatch, tmp_path):
    bx = FakeBitrix(
        deals=[
            _deal(deal_id="1", company_id="1"),
            _deal(deal_id="2", company_id="2"),
            _deal(deal_id="3", company_id="3"),
        ],
        companies={
            "1": {"UF_CRM_ORG_STATUS": "8852"},
            "2": {"UF_CRM_ORG_STATUS": "8852"},
            "3": {"UF_CRM_ORG_STATUS": "8850", "REVENUE": "15000000"},
        },
    )

    summary = _run_live(monkeypatch, tmp_path, bx)

    assert summary["rejected_8538"] == 2
    assert summary["rejected_8542"] == 1


def test_revenue_extraction_handles_string_with_separators(monkeypatch, tmp_path):
    bx = FakeBitrix(
        deals=[_deal()],
        companies={"10": {"UF_CRM_ORG_STATUS": "8850", "UF_CRM_1737098549301": "15 000 000"}},
    )

    summary = _run_live(monkeypatch, tmp_path, bx)

    assert summary["rejected_8542"] == 1
    assert bx.update_deal_calls[0][1][HOLD_REASON_FIELD] == "8542"


def test_revenue_extraction_negative_returns_none():
    company = {"UF_CRM_1737098549301": "-50000000"}

    assert stage._extract_company_revenue(company) is None


def test_revenue_extraction_float_with_decimals_parses():
    company = {"UF_CRM_1737098549301": "15000000.50"}

    assert stage._extract_company_revenue(company) == 15000000


def test_revenue_boundary_29_999_999_rejects():
    company = {"UF_CRM_ORG_STATUS": "8850", "UF_CRM_1737098549301": "29999999"}

    decision = stage.classify_for_rejection(company)

    assert decision is not None
    assert decision[0] == "8542"


def test_revenue_boundary_30_000_000_does_not_reject():
    company = {"UF_CRM_ORG_STATUS": "8850", "UF_CRM_1737098549301": "30000000"}

    assert stage.classify_for_rejection(company) is None


def test_classify_priority_liquidated_first():
    company = {"UF_CRM_ORG_STATUS": "8852", "UF_CRM_1737098549301": "10000000"}

    decision = stage.classify_for_rejection(company)

    assert decision is not None
    assert decision[0] == "8538"


def test_marker_already_set_recognises_Y_and_true_and_True():
    for value in ("Y", "true", True, "1"):
        assert stage._marker_already_set(value) is True


def test_prefetch_batch_partial_failure_falls_back_to_single_get():
    bx = BatchFakeBitrix(
        deals=[_deal(company_id="10"), _deal(company_id="20")],
        companies={"10": {"ID": "10"}, "20": {"ID": "20", "UF_CRM_ORG_STATUS": "8852"}},
        batch_result={"co_10": {"ID": "10"}, "co_20": None},
    )

    companies = stage._prefetch_companies(bx, bx.deals)

    assert companies["20"] == {"ID": "20", "UF_CRM_ORG_STATUS": "8852"}
    assert bx.get_company_calls == ["20"]


def test_prefetch_batch_partial_failure_single_get_also_fails():
    bx = BatchFakeBitrix(
        deals=[_deal(company_id="10")],
        companies={"10": {"ID": "10"}},
        batch_result={"co_10": None},
        raise_get_company={"10"},
    )

    companies = stage._prefetch_companies(bx, bx.deals)

    assert companies["10"] is None


def test_default_scan_stages_are_base_and_new():
    bx = FakeBitrix(deals=[], companies={})

    summary = stage.run(bx)

    assert tuple(summary["scan_stages"]) == TELEMARKETING_AUTO_REJECT_SCAN_STAGES
