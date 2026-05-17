from __future__ import annotations

from crm_company_enrich.config import COMPANY_UF_CITY, COMPANY_UF_REGION
from crm_company_enrich.stages import enrich_empty_companies as stage


class FakeBitrix:
    def __init__(self):
        self.update_company_calls: list[tuple[str, dict]] = []

    def update_company(self, company_id, fields):
        self.update_company_calls.append((str(company_id), dict(fields)))
        return True


def test_company_city_filled_from_reg_address_after_bp():
    bx = FakeBitrix()
    company = {COMPANY_UF_CITY: "", "REG_ADDRESS_CITY": "Чебоксары"}

    updates = stage._fill_company_address_fields(bx, "10", company)

    assert updates == {COMPANY_UF_CITY: "Чебоксары"}
    assert bx.update_company_calls == [("10", {COMPANY_UF_CITY: "Чебоксары"})]


def test_company_region_filled_from_reg_address_after_bp(monkeypatch):
    bx = FakeBitrix()
    monkeypatch.setattr(stage, "COMPANY_REGION_ENUM_MAP", {"чувашская": "123"})
    company = {COMPANY_UF_REGION: "", "REG_ADDRESS_REGION": "Чувашская Республика"}

    updates = stage._fill_company_address_fields(bx, "10", company)

    assert updates == {COMPANY_UF_REGION: "123"}
    assert bx.update_company_calls == [("10", {COMPANY_UF_REGION: "123"})]


def test_company_existing_city_not_overwritten():
    bx = FakeBitrix()
    company = {COMPANY_UF_CITY: "Москва", "REG_ADDRESS_CITY": "Питер"}

    updates = stage._fill_company_address_fields(bx, "10", company)

    assert updates == {}
    assert bx.update_company_calls == []


def test_region_enum_normalization_handles_obl_oblast_resp():
    mapping = {
        "московская": "55",
        "татарстан": "60",
        "краснодарский": "70",
    }

    assert stage._resolve_region_enum("Московская область", mapping) == "55"
    assert stage._resolve_region_enum("Респ. Татарстан", mapping) == "60"
    assert stage._resolve_region_enum("Краснодарский край", mapping) == "70"


def test_region_string_field_kept_raw(monkeypatch):
    bx = FakeBitrix()
    monkeypatch.setattr(stage, "COMPANY_REGION_ENUM_MAP", {})
    company = {COMPANY_UF_REGION: "", "REG_ADDRESS_REGION": "Московская область"}

    updates = stage._fill_company_address_fields(bx, "10", company)

    assert updates == {COMPANY_UF_REGION: "Московская область"}
