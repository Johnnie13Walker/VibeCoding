from __future__ import annotations

from crm_company_enrich.stages import sheet_row_guard, sync_deals


class FakeBitrix:
    def __init__(self, *, company: dict, deal: dict):
        self.company = company
        self.deal = deal

    def get_company(self, company_id: str) -> dict | None:
        return self.company if str(company_id) == str(self.company.get("ID")) else None

    def get_deal(self, deal_id: str) -> dict | None:
        return self.deal if str(deal_id) == str(self.deal.get("ID")) else None


class FakeExecute:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class FakeValues:
    def __init__(self, service):
        self.service = service

    def get(self, **kwargs):
        return FakeExecute({"values": [self.service.row]})


class FakeSpreadsheets:
    def __init__(self, service):
        self.service = service

    def values(self):
        return FakeValues(self.service)

    def batchUpdate(self, *, spreadsheetId, body):
        self.service.batch_updates.append((spreadsheetId, body))
        return FakeExecute({"replies": [{}]})


class FakeSheetsService:
    def __init__(self, row: list[str]):
        self.row = row
        self.batch_updates = []

    def spreadsheets(self):
        return FakeSpreadsheets(self)


def test_brand_industry_parity_report_accepts_company_and_deal_match():
    report = sync_deals.brand_industry_parity_report(
        {
            "UF_CRM_684FE59BA3C8C": "2442",
            "INDUSTRY": "UC_MEDICAL_GOODS_EQUIPMENT",
        },
        {
            "UF_CRM_1721661506": "1820",
            "UF_CRM_6179712C57A4D": "9522",
        },
    )

    assert report["ok"] is True
    assert report["company_brand"] == "Acoola Team"
    assert report["deal_brand"] == "Acoola Team"
    assert report["company_industry"] == "Медицинские товары и оборудование"
    assert report["deal_industry"] == "Медицинские товары и оборудование"


def test_brand_industry_parity_report_accepts_extended_company_industries():
    report = sync_deals.brand_industry_parity_report(
        {
            "UF_CRM_684FE59BA3C8C": "2442",
            "INDUSTRY": "UC_RETAIL_TRADE",
        },
        {
            "UF_CRM_1721661506": "1820",
            "UF_CRM_6179712C57A4D": "9524",
        },
    )

    assert report["ok"] is True
    assert report["company_industry"] == "Розничная торговля"
    assert report["deal_industry"] == "Розничная торговля"


def test_brand_industry_parity_report_rejects_missing_company_brand():
    report = sync_deals.brand_industry_parity_report(
        {"INDUSTRY": "UC_0M5893"},
        {"UF_CRM_1721661506": "1000", "UF_CRM_6179712C57A4D": "9518"},
    )

    assert report["ok"] is False
    assert "company_brand_missing" in report["errors"]


def test_delete_row_guarded_blocks_delete_when_parity_fails():
    service = FakeSheetsService(["domain.ru", "", "", "", "", "", "", "", "200", "", "", "", "100"])
    bx = FakeBitrix(
        company={"ID": "100", "INDUSTRY": "UC_0M5893"},
        deal={"ID": "200", "COMPANY_ID": "100", "UF_CRM_1721661506": "1000", "UF_CRM_6179712C57A4D": "9518"},
    )

    result = sheet_row_guard.delete_row_guarded(
        bx,
        service,
        sheet_id="sheet",
        tab_title="tab",
        sheet_gid=123,
        row_number=57,
        live=True,
    )

    assert result["deleted"] is False
    assert result["error"] == "brand_industry_parity_failed"
    assert service.batch_updates == []


def test_delete_row_guarded_deletes_when_parity_passes_live():
    service = FakeSheetsService(["domain.ru", "", "", "", "", "", "", "", "200", "", "", "", "100"])
    bx = FakeBitrix(
        company={"ID": "100", "UF_CRM_684FE59BA3C8C": "2444", "INDUSTRY": "UC_0M5893"},
        deal={"ID": "200", "COMPANY_ID": "100", "UF_CRM_1721661506": "1000", "UF_CRM_6179712C57A4D": "9518"},
    )

    result = sheet_row_guard.delete_row_guarded(
        bx,
        service,
        sheet_id="sheet",
        tab_title="tab",
        sheet_gid=123,
        row_number=57,
        live=True,
    )

    assert result["deleted"] is True
    assert result["error"] == ""
    assert service.batch_updates
    request = service.batch_updates[0][1]["requests"][0]["deleteDimension"]["range"]
    assert request["startIndex"] == 56
    assert request["endIndex"] == 57
