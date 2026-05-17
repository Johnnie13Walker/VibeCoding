from crm_company_enrich.stages import auto_promote_base as stage


class FakeBitrix:
    def __init__(self, company=None, contacts=None, requisites=None, deals=None):
        self.company = company or {}
        self.contacts = contacts if contacts is not None else []
        self.requisites = requisites if requisites is not None else []
        self.deals = deals if deals is not None else [{"ID": "10", "COMPANY_ID": "1", "STAGE_ID": "C50:UC_1S1KIU", "CLOSED": "N"}]
        self.updated_deals = []

    def list_deals_by_stages(self, *, category_id, stage_ids, closed, select):
        return [
            d for d in self.deals
            if d.get("STAGE_ID") in stage_ids and str(d.get("CLOSED")) == closed
        ]

    def get_company(self, company_id):
        return self.company

    def list_company_contacts_full(self, company_id):
        return self.contacts

    def list_company_requisites(self, company_id):
        return self.requisites

    def update_deal(self, deal_id, fields, *, params=None):
        self.updated_deals.append((deal_id, fields, params))
        return True


def ready_company():
    return {
        "PHONE": [{"VALUE": "+79990000000"}],
        "EMAIL": [{"VALUE": "a@example.com"}],
        "UF_CRM_1584876724": "Москва",
        "UF_CRM_REGION_RF": "9290",
        "UF_CRM_ORG_STATUS": "8850",
    }


def test_ready_company_is_promoted_to_C50_NEW():
    bx = FakeBitrix(company=ready_company(), contacts=[{"ID": "5"}], requisites=[{"RQ_INN": "7700000000"}])

    summary = stage.run(bx, dry_run=False)

    assert summary["promoted"] == 1
    assert bx.updated_deals[0][1]["STAGE_ID"] == "C50:NEW"
    assert bx.updated_deals[0][1]["CLOSED"] == "N"
    assert bx.updated_deals[0][1]["ASSIGNED_BY_ID"] == "2772"


def test_missing_phone_skipped_with_reason():
    company = ready_company()
    company["PHONE"] = []
    bx = FakeBitrix(company=company, contacts=[{"ID": "5"}], requisites=[{"RQ_INN": "7700000000"}])

    summary = stage.run(bx)

    assert summary["skipped"] == 1
    assert "PHONE_PRESENT" in summary["outcomes"][0]["missing_fields"]


def test_missing_email_skipped():
    company = ready_company()
    company["EMAIL"] = []
    bx = FakeBitrix(company=company, contacts=[{"ID": "5"}], requisites=[{"RQ_INN": "7700000000"}])

    assert "EMAIL_PRESENT" in stage.run(bx)["outcomes"][0]["missing_fields"]


def test_missing_inn_skipped():
    bx = FakeBitrix(company=ready_company(), contacts=[{"ID": "5"}], requisites=[])

    assert "INN_PRESENT" in stage.run(bx)["outcomes"][0]["missing_fields"]


def test_missing_city_skipped():
    company = ready_company()
    company["UF_CRM_1584876724"] = ""
    bx = FakeBitrix(company=company, contacts=[{"ID": "5"}], requisites=[{"RQ_INN": "7700000000"}])

    assert "CITY_PRESENT" in stage.run(bx)["outcomes"][0]["missing_fields"]


def test_missing_region_skipped():
    company = ready_company()
    company["UF_CRM_REGION_RF"] = ""
    bx = FakeBitrix(company=company, contacts=[{"ID": "5"}], requisites=[{"RQ_INN": "7700000000"}])

    assert "REGION_PRESENT" in stage.run(bx)["outcomes"][0]["missing_fields"]


def test_liquidated_company_skipped():
    company = ready_company()
    company["UF_CRM_ORG_STATUS"] = "8852"
    bx = FakeBitrix(company=company, contacts=[{"ID": "5"}], requisites=[{"RQ_INN": "7700000000"}])

    assert "ACTIVE_STATUS" in stage.run(bx)["outcomes"][0]["missing_fields"]


def test_no_contacts_skipped():
    bx = FakeBitrix(company=ready_company(), contacts=[], requisites=[{"RQ_INN": "7700000000"}])

    assert "BITRIX_CONTACT" in stage.run(bx)["outcomes"][0]["missing_fields"]


def test_rotation_assigns_dasha_first():
    bx = FakeBitrix(company=ready_company(), contacts=[{"ID": "5"}], requisites=[{"RQ_INN": "7700000000"}])

    summary = stage.run(bx, dry_run=True, rotation_index=0)

    assert summary["outcomes"][0]["new_assignee"] == "2772"


def test_dry_run_does_not_write():
    bx = FakeBitrix(company=ready_company(), contacts=[{"ID": "5"}], requisites=[{"RQ_INN": "7700000000"}])

    summary = stage.run(bx, dry_run=True)

    assert summary["dry_run_promotions"] == 1
    assert bx.updated_deals == []


def test_missing_company_id_zero_skipped_without_get_company():
    class ExplodingCompanyBitrix(FakeBitrix):
        def get_company(self, company_id):
            raise AssertionError("get_company не должен вызываться для COMPANY_ID=0")

    bx = ExplodingCompanyBitrix(deals=[{"ID": "10", "COMPANY_ID": "0", "STAGE_ID": "C50:UC_1S1KIU", "CLOSED": "N"}])

    summary = stage.run(bx)

    assert summary["skipped"] == 1
    assert summary["outcomes"][0]["skipped_reason"] == "missing_company_id"


def test_skipped_company_appended_to_rescan_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    company = ready_company()
    company["PHONE"] = []
    bx = FakeBitrix(company=company, contacts=[{"ID": "5"}], requisites=[{"RQ_INN": "7700000000"}])

    summary = stage.run(bx, dry_run=False)

    assert summary["skipped"] == 1
    csv_path = tmp_path / "auto_promote_skipped.csv"
    assert csv_path.exists()
    content = csv_path.read_text(encoding="utf-8")
    assert "company_id,deal_id,missing_fields" in content
    assert "PHONE_PRESENT" in content


def test_rescan_csv_appended_only_in_live(tmp_path, monkeypatch):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    company = ready_company()
    company["EMAIL"] = []
    bx = FakeBitrix(company=company, contacts=[{"ID": "5"}], requisites=[{"RQ_INN": "7700000000"}])

    summary = stage.run(bx, dry_run=True)

    assert summary["skipped"] == 1
    assert not (tmp_path / "auto_promote_skipped.csv").exists()


def test_failed_update_does_not_consume_rotation():
    class FailingFirstUpdateBitrix(FakeBitrix):
        def update_deal(self, deal_id, fields, *, params=None):
            if deal_id == "10":
                raise RuntimeError("bitrix down")
            return super().update_deal(deal_id, fields, params=params)

    bx = FailingFirstUpdateBitrix(
        company=ready_company(),
        contacts=[{"ID": "5"}],
        requisites=[{"RQ_INN": "7700000000"}],
        deals=[
            {"ID": "10", "COMPANY_ID": "1", "STAGE_ID": "C50:UC_1S1KIU", "CLOSED": "N"},
            {"ID": "11", "COMPANY_ID": "1", "STAGE_ID": "C50:UC_1S1KIU", "CLOSED": "N"},
        ],
    )

    summary = stage.run(bx, dry_run=False, rotation_index=0)

    assert summary["outcomes"][0]["status"] == "FAILED"
    assert summary["outcomes"][1]["new_assignee"] == "2772"
    assert bx.updated_deals[0][0] == "11"
