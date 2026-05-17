from __future__ import annotations

import pytest

from crm_company_enrich.config import (
    COMPANY_INDUSTRY_STATUS,
    COMPANY_ORGANIZATION_STATUS_ENUM,
    COMPANY_UF_CITY,
    COMPANY_UF_ORGANIZATION_STATUS,
    COMPANY_UF_REGION,
    COMPANY_UF_RUSPROFILE_CHECKO_URL,
    DEAL_UF_BRAND_PROJECT,
    DEAL_UF_CITY,
    DEAL_UF_REGION,
    DEAL_UF_INDUSTRY,
    DEAL_UF_INN,
    DEAL_UF_REVENUE_MONEY,
    DEAL_UF_REVENUE_NUMBER,
    DEAL_UF_REVENUE_TEXT,
    DEAL_UF_RUSPROFILE_URL,
    DEAL_UF_SITE_MULTI,
    DEAL_UF_SITE_PRIMARY,
    HOLD_REASON_FIELD,
)
from crm_company_enrich.stages import sync_deals

ORIG_VERIFIED_SITE = sync_deals._verified_site


@pytest.fixture(autouse=True)
def no_live_rusprofile(monkeypatch):
    monkeypatch.setattr(sync_deals, "_organization_status_from_inn", lambda inn: "")
    monkeypatch.setattr(sync_deals, "_industry_from_inn", lambda inn: "")
    monkeypatch.setattr(
        sync_deals,
        "_verified_site",
        lambda site, company, inn="": sync_deals.SiteVerification(site, True, True, ["test"]),
    )


class FakeBitrix:
    def __init__(
        self,
        *,
        companies: dict[str, dict],
        deals_by_company: dict[str, list[dict]] | None = None,
        deals_by_id: dict[str, dict] | None = None,
        company_contacts: dict[str, list[str]] | None = None,
        deal_contacts: dict[str, list[dict]] | None = None,
        contacts: dict[str, dict] | None = None,
    ):
        self.companies = companies
        self.deals_by_company = deals_by_company or {}
        self.deals_by_id = deals_by_id or {}
        self.company_contacts = company_contacts or {}
        self.deal_contacts = deal_contacts or {}
        self.contacts = contacts or {}
        self.update_deal_calls: list[tuple[str, dict]] = []
        self.update_company_calls: list[tuple[str, dict]] = []
        self.add_deal_contact_calls: list[tuple[str, str]] = []
        self.update_contact_calls: list[tuple[str, dict]] = []

    def get_company(self, company_id: str) -> dict | None:
        return self.companies.get(str(company_id))

    def list_company_deals(self, company_id: str, select: list[str] | None = None) -> list[dict]:
        return list(self.deals_by_company.get(str(company_id), []))

    def get_deal(self, deal_id: str) -> dict | None:
        return self.deals_by_id.get(str(deal_id))

    def update_deal(self, deal_id: str, fields: dict, *, params: dict | None = None) -> bool:
        self.update_deal_calls.append((str(deal_id), dict(fields)))
        if str(deal_id) in self.deals_by_id:
            self.deals_by_id[str(deal_id)].update(fields)
        for deals in self.deals_by_company.values():
            for deal in deals:
                if str(deal.get("ID")) == str(deal_id):
                    deal.update(fields)
        return True

    def update_company(self, company_id: str, fields: dict) -> bool:
        self.update_company_calls.append((str(company_id), dict(fields)))
        if str(company_id) in self.companies:
            self.companies[str(company_id)].update(fields)
        return True

    def get_company_contacts(self, company_id: str) -> list[str]:
        return list(self.company_contacts.get(str(company_id), []))

    def list_deal_contacts(self, deal_id: str) -> list[dict]:
        return list(self.deal_contacts.get(str(deal_id), []))

    def list_deal_activities(self, deal_id: str) -> list[dict]:
        return []

    def list_active_users(self) -> set[str]:
        return {"2772", "2832"}

    def add_deal_contact(self, deal_id: str, contact_id: str) -> bool:
        self.add_deal_contact_calls.append((str(deal_id), str(contact_id)))
        self.deal_contacts.setdefault(str(deal_id), []).append({"CONTACT_ID": str(contact_id)})
        return True

    def add_timeline_comment(self, *, owner_type_id: int, owner_id: str, text: str) -> str:
        return "timeline-1"

    def get_contact(self, contact_id: str) -> dict | None:
        return self.contacts.get(str(contact_id))

    def update_contact(self, contact_id: str, fields: dict) -> bool:
        self.update_contact_calls.append((str(contact_id), dict(fields)))
        if str(contact_id) in self.contacts:
            self.contacts[str(contact_id)].update(fields)
        return True

    def call(self, method: str, params: dict | None = None) -> dict:
        if method == "crm.deal.list":
            did = str((params or {}).get("filter", {}).get("ID") or "")
            return {"result": [self.deals_by_id[did]] if did in self.deals_by_id else []}
        raise AssertionError(f"unexpected call: {method}")


def _company(**overrides) -> dict:
    data = {
        "ID": "100",
        "TITLE": "ООО МИЛБЭГ",
        "UF_CRM_5DEF838D882A2": "https://milbag.ru",
        "WEB": [{"VALUE": "https://moskva.milbag.ru"}],
        "UF_CRM_1584876724": "Новосибирск",
        "UF_CRM_1735331882180": "5406990573",
        "UF_CRM_1737098549301": "139866000",
        "UF_CRM_1737098525088": "milbag.ru; moskva.milbag.ru",
        "UF_CRM_1737100327954": "47.72 Торговля розничная обувью и изделиями из кожи",
        "UF_CRM_1737098476975": "Acoola Team",
        COMPANY_UF_RUSPROFILE_CHECKO_URL: "https://www.rusprofile.ru/search?query=5406990573",
        "INDUSTRY": "UC_QOXULA",
    }
    data.update(overrides)
    return data


def _deal(**overrides) -> dict:
    data = {
        "ID": "200",
        "TITLE": "milbag.ru",
        "COMPANY_ID": "100",
        "CLOSED": "N",
        DEAL_UF_SITE_PRIMARY: "",
        DEAL_UF_SITE_MULTI: [],
        DEAL_UF_BRAND_PROJECT: "",
        DEAL_UF_CITY: "",
        DEAL_UF_REGION: "",
        DEAL_UF_INN: "",
        DEAL_UF_REVENUE_TEXT: "",
        DEAL_UF_REVENUE_MONEY: "",
        DEAL_UF_REVENUE_NUMBER: "0",
        DEAL_UF_INDUSTRY: "",
        DEAL_UF_RUSPROFILE_URL: "",
    }
    data.update(overrides)
    return data


def test_build_deal_fields_from_company_maps_known_fields():
    fields = sync_deals.build_deal_fields_from_company(_company())

    assert fields[DEAL_UF_SITE_PRIMARY] == "https://milbag.ru"
    assert fields[DEAL_UF_SITE_MULTI] == [
        "https://milbag.ru",
        "https://moskva.milbag.ru",
    ]
    assert fields[DEAL_UF_CITY] == "Новосибирск"
    assert fields[DEAL_UF_INN] == "5406990573"
    assert fields[DEAL_UF_REVENUE_TEXT] == "139866000"
    assert fields[DEAL_UF_REVENUE_NUMBER] == 139866000
    assert fields[DEAL_UF_REVENUE_MONEY] == "139866000|RUB"
    assert fields[DEAL_UF_RUSPROFILE_URL] == "https://www.rusprofile.ru/search?query=5406990573"
    assert fields[DEAL_UF_BRAND_PROJECT] == "1820"
    assert fields[DEAL_UF_INDUSTRY] == "456"

    company_fields = sync_deals.build_company_fields_from_company(_company())
    assert company_fields == {
        "INDUSTRY": COMPANY_INDUSTRY_STATUS["E-commerce"],
        COMPANY_UF_RUSPROFILE_CHECKO_URL: "https://www.rusprofile.ru/search?query=5406990573",
    }

    company_fields = sync_deals.build_company_fields_from_company(
        _company(),
        organization_status="Действующая",
    )
    assert company_fields[COMPANY_UF_ORGANIZATION_STATUS] == COMPANY_ORGANIZATION_STATUS_ENUM["Действующая"]


def test_deal_city_overwritten_when_differs_from_company():
    desired = sync_deals.build_deal_fields_from_company(_company(**{COMPANY_UF_CITY: "Москва"}))
    fields, skipped = sync_deals._filter_existing_fields(
        _deal(**{DEAL_UF_CITY: "Питер"}),
        desired,
        overwrite=False,
    )

    assert fields[DEAL_UF_CITY] == "Москва"
    assert DEAL_UF_CITY not in skipped


def test_deal_region_overwritten_when_differs_from_company():
    desired = sync_deals.build_deal_fields_from_company(
        _company(**{COMPANY_UF_REGION: "Московская область"})
    )
    fields, skipped = sync_deals._filter_existing_fields(
        _deal(**{DEAL_UF_REGION: "Ленинградская область"}),
        desired,
        overwrite=False,
    )

    assert fields[DEAL_UF_REGION] == "Московская область"
    assert DEAL_UF_REGION not in skipped


def test_deal_region_string_gets_label_from_company_region_enum_id():
    fields = sync_deals.build_deal_fields_from_company(
        _company(**{COMPANY_UF_REGION: "9234"})
    )

    assert fields[DEAL_UF_REGION] == "Москва"


def test_deal_city_unchanged_when_matches_company():
    desired = sync_deals.build_deal_fields_from_company(_company(**{COMPANY_UF_CITY: "Москва"}))
    fields, skipped = sync_deals._filter_existing_fields(
        _deal(**{DEAL_UF_CITY: "Москва"}),
        desired,
        overwrite=False,
    )

    assert DEAL_UF_CITY not in fields
    assert skipped[DEAL_UF_CITY] == "mandatory_already_synced"


def test_deal_region_skipped_when_field_undefined(monkeypatch):
    monkeypatch.setattr(sync_deals, "DEAL_UF_REGION", None)
    desired = sync_deals.build_deal_fields_from_company(
        _company(**{COMPANY_UF_REGION: "Московская область"})
    )

    assert None not in desired
    assert "UF_CRM_5E79DD26F08C9" not in desired


def test_non_mandatory_field_still_respects_overwrite_off():
    desired = {DEAL_UF_INN: "5406990573"}
    fields, skipped = sync_deals._filter_existing_fields(
        _deal(**{DEAL_UF_INN: "1111111111"}),
        desired,
        overwrite=False,
    )

    assert fields == {}
    assert skipped[DEAL_UF_INN] == "already_filled"


def test_dry_run_does_not_update_deal():
    bx = FakeBitrix(
        companies={"100": _company()},
        deals_by_company={"100": [_deal()]},
    )

    summary = sync_deals.run(bx, company_id="100", dry_run=True)

    assert summary["dry_run_updates"] == 1
    assert summary["company_dry_run_updates"] == 0
    assert summary["updated"] == 0
    assert bx.update_deal_calls == []
    assert bx.update_company_calls == []
    assert summary["outcomes"][0]["fields"][DEAL_UF_SITE_PRIMARY] == "https://milbag.ru"


def test_live_updates_only_empty_fields_by_default():
    bx = FakeBitrix(
        companies={"100": _company()},
        deals_by_company={
            "100": [
                _deal(
                    **{
                        DEAL_UF_SITE_PRIMARY: "https://old.example/",
                        DEAL_UF_BRAND_PROJECT: "1000",
                    }
                )
            ]
        },
    )

    summary = sync_deals.run(bx, company_id="100", dry_run=False)

    assert summary["updated"] == 1
    _, fields = bx.update_deal_calls[0]
    assert DEAL_UF_CITY in fields
    assert DEAL_UF_INN in fields
    assert DEAL_UF_SITE_PRIMARY not in fields
    assert DEAL_UF_BRAND_PROJECT not in fields
    assert summary["outcomes"][0]["skipped"][DEAL_UF_SITE_PRIMARY] == "already_filled"
    assert summary["outcomes"][0]["skipped"][DEAL_UF_BRAND_PROJECT] == "already_filled"


def test_live_adds_company_contacts_to_deal_without_field_updates():
    filled_deal = _deal(
        **{
            DEAL_UF_SITE_PRIMARY: "https://milbag.ru",
            DEAL_UF_SITE_MULTI: ["https://milbag.ru"],
            DEAL_UF_BRAND_PROJECT: "1820",
            DEAL_UF_CITY: "Новосибирск",
            DEAL_UF_INN: "5406990573",
            DEAL_UF_REVENUE_TEXT: "139866000",
            DEAL_UF_REVENUE_MONEY: "139866000|RUB",
            DEAL_UF_REVENUE_NUMBER: 139866000,
            DEAL_UF_INDUSTRY: "456",
            DEAL_UF_RUSPROFILE_URL: "https://www.rusprofile.ru/search?query=5406990573",
        }
    )
    bx = FakeBitrix(
        companies={"100": _company()},
        deals_by_company={"100": [filled_deal]},
        company_contacts={"100": ["10", "20"]},
        deal_contacts={"200": [{"CONTACT_ID": "10"}]},
    )

    summary = sync_deals.run(bx, company_id="100", dry_run=False)

    assert summary["updated"] == 0
    assert summary["contacts_added"] == 1
    assert summary["noop"] == 0
    assert bx.update_deal_calls == []
    assert bx.add_deal_contact_calls == [("200", "20")]
    assert summary["outcomes"][0]["contacts_added"] == ["20"]
    assert summary["outcomes"][0]["contacts_skipped"] == {"10": "already_linked"}


def test_dry_run_reports_missing_company_contacts_without_writing():
    filled_deal = _deal(
        **{
            DEAL_UF_SITE_PRIMARY: "https://milbag.ru",
            DEAL_UF_SITE_MULTI: ["https://milbag.ru"],
            DEAL_UF_BRAND_PROJECT: "1820",
            DEAL_UF_CITY: "Новосибирск",
            DEAL_UF_INN: "5406990573",
            DEAL_UF_REVENUE_TEXT: "139866000",
            DEAL_UF_REVENUE_MONEY: "139866000|RUB",
            DEAL_UF_REVENUE_NUMBER: 139866000,
            DEAL_UF_INDUSTRY: "456",
            DEAL_UF_RUSPROFILE_URL: "https://www.rusprofile.ru/search?query=5406990573",
        }
    )
    bx = FakeBitrix(
        companies={"100": _company()},
        deals_by_company={"100": [filled_deal]},
        company_contacts={"100": ["10"]},
    )

    summary = sync_deals.run(bx, company_id="100", dry_run=True)

    assert summary["contacts_dry_run_adds"] == 1
    assert bx.add_deal_contact_calls == []
    assert summary["outcomes"][0]["status"] == "DRY_RUN"
    assert summary["outcomes"][0]["contacts_added"] == ["10"]


def test_live_fills_empty_contact_communications_from_company():
    filled_deal = _deal(
        **{
            DEAL_UF_SITE_PRIMARY: "https://milbag.ru",
            DEAL_UF_SITE_MULTI: ["https://milbag.ru"],
            DEAL_UF_BRAND_PROJECT: "1820",
            DEAL_UF_CITY: "Новосибирск",
            DEAL_UF_INN: "5406990573",
            DEAL_UF_REVENUE_TEXT: "139866000",
            DEAL_UF_REVENUE_MONEY: "139866000|RUB",
            DEAL_UF_REVENUE_NUMBER: 139866000,
            DEAL_UF_INDUSTRY: "456",
            DEAL_UF_RUSPROFILE_URL: "https://www.rusprofile.ru/search?query=5406990573",
        }
    )
    company = _company(
        PHONE=[{"VALUE": "+7 812 300-56-49", "VALUE_TYPE": "WORK", "TYPE_ID": "PHONE"}],
        EMAIL=[{"VALUE": "info@milbag.ru", "VALUE_TYPE": "WORK", "TYPE_ID": "EMAIL"}],
    )
    bx = FakeBitrix(
        companies={"100": company},
        deals_by_company={"100": [filled_deal]},
        company_contacts={"100": ["10"]},
        deal_contacts={"200": [{"CONTACT_ID": "10"}]},
        contacts={"10": {"ID": "10", "PHONE": [], "EMAIL": []}},
    )

    summary = sync_deals.run(bx, company_id="100", dry_run=False)

    assert summary["contact_communications_updated"] == 1
    assert bx.update_contact_calls == [
        (
            "10",
            {
                "PHONE": [{"VALUE": "+7 812 300-56-49", "VALUE_TYPE": "WORK", "TYPE_ID": "PHONE"}],
                "EMAIL": [{"VALUE": "info@milbag.ru", "VALUE_TYPE": "WORK", "TYPE_ID": "EMAIL"}],
            },
        )
    ]
    assert summary["outcomes"][0]["contact_communications"] == {
        "10": {
            "PHONE": [{"VALUE": "+7 812 300-56-49", "VALUE_TYPE": "WORK", "TYPE_ID": "PHONE"}],
            "EMAIL": [{"VALUE": "info@milbag.ru", "VALUE_TYPE": "WORK", "TYPE_ID": "EMAIL"}],
        }
    }


def test_does_not_overwrite_existing_contact_communications():
    filled_deal = _deal(
        **{
            DEAL_UF_SITE_PRIMARY: "https://milbag.ru",
            DEAL_UF_SITE_MULTI: ["https://milbag.ru"],
            DEAL_UF_BRAND_PROJECT: "1820",
            DEAL_UF_CITY: "Новосибирск",
            DEAL_UF_INN: "5406990573",
            DEAL_UF_REVENUE_TEXT: "139866000",
            DEAL_UF_REVENUE_MONEY: "139866000|RUB",
            DEAL_UF_REVENUE_NUMBER: 139866000,
            DEAL_UF_INDUSTRY: "456",
            DEAL_UF_RUSPROFILE_URL: "https://www.rusprofile.ru/search?query=5406990573",
        }
    )
    company = _company(
        PHONE=[{"VALUE": "+7 812 300-56-49", "VALUE_TYPE": "WORK", "TYPE_ID": "PHONE"}],
        EMAIL=[{"VALUE": "info@milbag.ru", "VALUE_TYPE": "WORK", "TYPE_ID": "EMAIL"}],
    )
    bx = FakeBitrix(
        companies={"100": company},
        deals_by_company={"100": [filled_deal]},
        company_contacts={"100": ["10"]},
        deal_contacts={"200": [{"CONTACT_ID": "10"}]},
        contacts={
            "10": {
                "ID": "10",
                "PHONE": [{"VALUE": "+7 999 000-00-00", "VALUE_TYPE": "WORK", "TYPE_ID": "PHONE"}],
                "EMAIL": [{"VALUE": "person@example.com", "VALUE_TYPE": "WORK", "TYPE_ID": "EMAIL"}],
            }
        },
    )

    summary = sync_deals.run(bx, company_id="100", dry_run=False)

    assert summary["contact_communications_updated"] == 0
    assert bx.update_contact_calls == []


def test_live_reconciles_company_industry_even_when_deal_industry_is_filled():
    bx = FakeBitrix(
        companies={"100": _company(INDUSTRY="UC_0M5893")},
        deals_by_company={"100": [_deal(**{DEAL_UF_INDUSTRY: "456"})]},
    )

    summary = sync_deals.run(bx, company_id="100", dry_run=False)

    assert summary["company_updated"] == 1
    assert bx.update_company_calls == [("100", {"INDUSTRY": "UC_QOXULA"})]
    assert bx.companies["100"]["INDUSTRY"] == "UC_QOXULA"


def test_live_reconciles_company_rusprofile_link_even_when_deal_is_filled():
    bx = FakeBitrix(
        companies={"100": _company(**{COMPANY_UF_RUSPROFILE_CHECKO_URL: ""})},
        deals_by_company={
            "100": [
                _deal(
                    **{
                        DEAL_UF_INDUSTRY: "456",
                        DEAL_UF_RUSPROFILE_URL: "https://www.rusprofile.ru/search?query=5406990573",
                    }
                )
            ]
        },
    )

    summary = sync_deals.run(bx, company_id="100", dry_run=False)

    assert summary["company_updated"] == 1
    assert bx.update_company_calls == [
        ("100", {COMPANY_UF_RUSPROFILE_CHECKO_URL: "https://www.rusprofile.ru/search?query=5406990573"})
    ]


def test_live_reconciles_company_organization_status(monkeypatch):
    monkeypatch.setattr(sync_deals, "_organization_status_from_inn", lambda inn: "Действующая")
    bx = FakeBitrix(
        companies={"100": _company(**{COMPANY_UF_ORGANIZATION_STATUS: ""})},
        deals_by_company={
            "100": [
                _deal(
                    **{
                        DEAL_UF_INDUSTRY: "456",
                        DEAL_UF_RUSPROFILE_URL: "https://www.rusprofile.ru/search?query=5406990573",
                    }
                )
            ]
        },
    )

    summary = sync_deals.run(bx, company_id="100", dry_run=False)

    assert summary["company_updated"] == 1
    assert bx.update_company_calls == [
        ("100", {COMPANY_UF_ORGANIZATION_STATUS: COMPANY_ORGANIZATION_STATUS_ENUM["Действующая"]})
    ]


def test_organization_status_parses_rusprofile_html(monkeypatch):
    assert sync_deals._parse_organization_status("<span>Действующая организация</span>") == "Действующая"

    assert sync_deals._parse_organization_status("<span>Организация ликвидирована</span>") == "Ликвидирована"

    assert sync_deals._parse_organization_status("<h1>Организация в процессе банкротства</h1>") == "Ликвидирована"


def test_brand_defaults_to_belberry_when_company_brand_is_empty():
    bx = FakeBitrix(
        companies={"100": _company(UF_CRM_1737098476975="")},
        deals_by_company={"100": [_deal()]},
    )

    summary = sync_deals.run(bx, company_id="100", dry_run=False)

    assert summary["updated"] == 1
    _, fields = bx.update_deal_calls[0]
    assert fields[DEAL_UF_BRAND_PROJECT] == "1000"


def test_medical_company_gets_belberry_brand_when_company_brand_is_empty():
    bx = FakeBitrix(
        companies={
            "100": _company(
                TITLE="Стоматология SmileLab",
                UF_CRM_1737098414068="Медицинская клиника стоматологии",
                UF_CRM_1737098476975="",
                UF_CRM_1737100327954="86.23 Стоматологическая практика",
            )
        },
        deals_by_company={"100": [_deal()]},
    )

    summary = sync_deals.run(bx, company_id="100", dry_run=False)

    assert summary["updated"] == 1
    _, fields = bx.update_deal_calls[0]
    assert fields[DEAL_UF_BRAND_PROJECT] == "1000"


def test_unknown_company_gets_belberry_brand_by_default():
    bx = FakeBitrix(
        companies={
            "100": _company(
                TITLE="ООО Ромашка",
                UF_CRM_1737098414068="",
                UF_CRM_1737098476975="",
                UF_CRM_1737100327954="",
                UF_CRM_5DEF838D882A2="",
                WEB=[],
                UF_CRM_1737098525088="",
            )
        },
        deals_by_company={"100": [_deal()]},
    )

    summary = sync_deals.run(bx, company_id="100", dry_run=False)

    assert summary["updated"] == 1
    _, fields = bx.update_deal_calls[0]
    assert fields[DEAL_UF_BRAND_PROJECT] == "1000"


def test_baggage_store_is_ecommerce_not_tourism():
    fields = sync_deals.build_deal_fields_from_company(
        _company(
            TITLE="Интернет-магазин сумок и чемоданов",
            UF_CRM_1737100327954="Продажа багажа, сумок и чемоданов",
        )
    )

    assert fields[DEAL_UF_INDUSTRY] == "456"


def test_site_primary_is_filled_only_when_site_identity_verified(monkeypatch):
    monkeypatch.setattr(
        sync_deals,
        "_verified_site",
        lambda site, company, inn="": sync_deals.SiteVerification(
            site,
            site == "https://good.example/",
            site == "https://good.example/",
            ["test"] if site == "https://good.example/" else [],
        ),
    )

    fields = sync_deals.build_deal_fields_from_company(
        _company(
            UF_CRM_5DEF838D882A2="https://bad.example/",
            WEB=[{"VALUE": "https://good.example/"}],
            UF_CRM_1737098525088="",
        )
    )

    assert fields[DEAL_UF_SITE_PRIMARY] == "https://good.example"


def test_site_primary_is_not_filled_when_site_not_working(monkeypatch):
    monkeypatch.setattr(
        sync_deals,
        "_verified_site",
        lambda site, company, inn="": sync_deals.SiteVerification(site, False, False, []),
    )

    fields = sync_deals.build_deal_fields_from_company(
        _company(
            UF_CRM_5DEF838D882A2="https://bad.example/",
            WEB=[{"VALUE": "https://also-bad.example/"}],
            UF_CRM_1737098525088="",
        )
    )

    assert DEAL_UF_SITE_PRIMARY not in fields


def test_site_key_normalizes_http_https_www_trailing_slash():
    expected = sync_deals._site_key("https://kadis.org/")

    assert sync_deals._site_key("http://kadis.org") == expected
    assert sync_deals._site_key("kadis.org") == expected
    assert sync_deals._site_key("https://www.kadis.org/") == expected
    assert sync_deals._site_key("https://kadis.org") == expected


def test_site_key_collapses_subpages_of_same_host():
    expected = sync_deals._site_key("https://kadis.org/")

    assert sync_deals._site_key("https://kadis.org/contacts") == expected
    assert sync_deals._site_key("https://www.kadis.org/requisites/") == expected


def test_site_key_rejects_mailto_and_tel():
    assert sync_deals._site_key("mailto:info@example.com") == ""
    assert sync_deals._site_key("tel:+74951234567") == ""


def test_normalize_site_url_forces_https():
    assert sync_deals._normalize_site_url("http://kadis.org/") == "https://kadis.org"
    assert sync_deals._normalize_site_url("https://kadis.org/") == "https://kadis.org"
    assert sync_deals._normalize_site_url("kadis.org/") == "https://kadis.org"


def test_site_values_dedups_company_with_http_and_bare_host(monkeypatch):
    monkeypatch.setattr(sync_deals, "_verified_site", ORIG_VERIFIED_SITE)
    monkeypatch.setattr(sync_deals, "_is_working_site", lambda site: True)
    monkeypatch.setattr(sync_deals, "_site_identity_evidence", lambda site, company, inn="": [])

    fields = sync_deals.build_deal_fields_from_company(
        _company(
            UF_CRM_5DEF838D882A2="",
            WEB=[
                {"VALUE": "https://kadis.org/", "VALUE_TYPE": "WORK"},
                {"VALUE": "kadis.org", "VALUE_TYPE": "WORK"},
                {"VALUE": "https://kadis.ru/", "VALUE_TYPE": "WORK"},
            ],
            UF_CRM_1737098525088="",
        )
    )

    assert fields[DEAL_UF_SITE_MULTI] == ["https://kadis.org", "https://kadis.ru"]


def test_site_values_skips_non_working_site(monkeypatch):
    monkeypatch.setattr(sync_deals, "_verified_site", ORIG_VERIFIED_SITE)
    monkeypatch.setattr(
        sync_deals,
        "_is_working_site",
        lambda site: "working.example" in site,
    )
    monkeypatch.setattr(sync_deals, "_site_identity_evidence", lambda site, company, inn="": [])

    fields = sync_deals.build_deal_fields_from_company(
        _company(
            UF_CRM_5DEF838D882A2="",
            WEB=[
                {"VALUE": "https://broken.example/", "VALUE_TYPE": "WORK"},
                {"VALUE": "https://working.example/", "VALUE_TYPE": "WORK"},
            ],
            UF_CRM_1737098525088="",
        )
    )

    assert fields[DEAL_UF_SITE_MULTI] == ["https://working.example"]


def test_primary_falls_back_to_working_when_no_identity(monkeypatch):
    monkeypatch.setattr(sync_deals, "_verified_site", ORIG_VERIFIED_SITE)
    monkeypatch.setattr(sync_deals, "_is_working_site", lambda site: True)
    monkeypatch.setattr(sync_deals, "_site_identity_evidence", lambda site, company, inn="": [])

    fields = sync_deals.build_deal_fields_from_company(
        _company(
            UF_CRM_5DEF838D882A2="example.com",
            WEB=[],
            UF_CRM_1737098525088="",
        )
    )

    assert fields[DEAL_UF_SITE_PRIMARY] == "https://example.com"


def test_primary_prefers_identity_verified_over_working_fallback(monkeypatch):
    monkeypatch.setattr(
        sync_deals,
        "_verified_site",
        lambda site, company, inn="": sync_deals.SiteVerification(
            site,
            True,
            site == "https://identity.example/",
            ["test"] if site == "https://identity.example/" else [],
        ),
    )

    fields = sync_deals.build_deal_fields_from_company(
        _company(
            UF_CRM_5DEF838D882A2="https://working.example/",
            WEB=[{"VALUE": "https://identity.example/", "VALUE_TYPE": "WORK"}],
            UF_CRM_1737098525088="",
        )
    )

    assert fields[DEAL_UF_SITE_PRIMARY] == "https://identity.example"


def test_rusprofile_main_activity_fills_other_industry(monkeypatch):
    monkeypatch.setattr(sync_deals, "_industry_from_inn", lambda inn: "Другое")
    bx = FakeBitrix(
        companies={
            "100": _company(
                TITLE="ООО ОБЕРКРАФТ",
                INDUSTRY="",
                UF_CRM_1737100327954="",
            )
        },
        deals_by_company={"100": [_deal()]},
    )

    summary = sync_deals.run(bx, company_id="100", dry_run=False)

    assert summary["updated"] == 1
    assert summary["company_updated"] == 1
    _, deal_fields = bx.update_deal_calls[0]
    assert deal_fields[DEAL_UF_INDUSTRY] == "2122"
    assert bx.update_company_calls[0][1]["INDUSTRY"] == COMPANY_INDUSTRY_STATUS["Другое"]


def test_parse_main_activity_from_rusprofile_text():
    html = (
        'Основной вид деятельности "Оберкрафт" - '
        "Оптовая торговля автомобильными деталями, узлами и принадлежностями "
        "и 2 дополнительных вида. Состоит на учете"
    )

    activity = sync_deals._parse_main_activity(html)

    assert activity == "Оптовая торговля автомобильными деталями, узлами и принадлежностями"
    assert sync_deals._industry_from_text(activity, fallback_other=True) == "Другое"


def test_run_company_fills_company_without_deals(monkeypatch):
    monkeypatch.setattr(sync_deals, "_organization_status_from_inn", lambda inn: "Действующая")
    monkeypatch.setattr(sync_deals, "_industry_from_inn", lambda inn: "Медицина")
    bx = FakeBitrix(
        companies={
            "1144": _company(
                ID="1144",
                TITLE="медскан.рф",
                UF_CRM_5DEF838D882A2="медскан.рф",
                WEB=[{"VALUE": "медскан.рф"}],
                UF_CRM_1737098525088="медскан.рф",
                INDUSTRY="",
                UF_CRM_1735331882180="",
                UF_CRM_1737098476975="",
                UF_CRM_RUSPROFILE_CHECKO_URL="",
                UF_CRM_ORG_STATUS="",
                UF_CRM_1737100327954="",
            )
        },
        deals_by_company={"1144": []},
    )

    summary = sync_deals.run_company(
        bx,
        company_id="1144",
        inn="7725819008",
        dry_run=False,
    )

    assert summary["updated"] == 1
    assert bx.update_company_calls == [
        (
            "1144",
            {
                "INDUSTRY": COMPANY_INDUSTRY_STATUS["Медицина"],
                COMPANY_UF_RUSPROFILE_CHECKO_URL: "https://www.rusprofile.ru/search?query=7725819008",
                COMPANY_UF_ORGANIZATION_STATUS: COMPANY_ORGANIZATION_STATUS_ENUM["Действующая"],
                "UF_CRM_1735331882180": "7725819008",
                "UF_CRM_1737098476975": "Belberry",
            },
        )
    ]


def test_run_company_replaces_dead_site_with_explicit_working_site(monkeypatch):
    monkeypatch.setattr(sync_deals, "_organization_status_from_inn", lambda inn: "")
    monkeypatch.setattr(sync_deals, "_industry_from_inn", lambda inn: "")
    monkeypatch.setattr(
        sync_deals,
        "_verified_site",
        lambda site, company, inn="": sync_deals.SiteVerification(
            site,
            site == "medscannet.ru",
            site == "medscannet.ru",
            ["site_contains_inn:7725819008"] if site == "medscannet.ru" else [],
        ),
    )
    bx = FakeBitrix(
        companies={
            "1144": _company(
                ID="1144",
                UF_CRM_5DEF838D882A2="медскан.рф",
                UF_CRM_1735331882180="7725819008",
                UF_CRM_RUSPROFILE_CHECKO_URL="https://www.rusprofile.ru/search?query=7725819008",
                UF_CRM_ORG_STATUS="8850",
                UF_CRM_1737098476975="Belberry",
            )
        }
    )

    summary = sync_deals.run_company(
        bx,
        company_id="1144",
        site="medscannet.ru",
        dry_run=False,
    )

    assert summary["updated"] == 1
    assert bx.update_company_calls == [("1144", {"UF_CRM_5DEF838D882A2": "medscannet.ru"})]


def test_deal_replaces_dead_site_primary_with_working_company_site(monkeypatch):
    monkeypatch.setattr(
        sync_deals,
        "_verified_site",
        lambda site, company, inn="": sync_deals.SiteVerification(
            site,
            site == "https://good.example/",
            site == "https://good.example/",
            ["test"] if site == "https://good.example/" else [],
        ),
    )
    bx = FakeBitrix(
        companies={
            "100": _company(
                UF_CRM_5DEF838D882A2="https://good.example/",
                WEB=[],
                UF_CRM_1737098525088="",
            )
        },
        deals_by_company={"100": [_deal(**{DEAL_UF_SITE_PRIMARY: "https://dead.example/"})]},
    )

    summary = sync_deals.run(bx, company_id="100", dry_run=False)

    assert summary["updated"] == 1
    assert bx.update_deal_calls[0][1][DEAL_UF_SITE_PRIMARY] == "https://good.example"


def test_site_identity_evidence_accepts_inn(monkeypatch):
    monkeypatch.setattr(
        sync_deals,
        "_site_identity_text",
        lambda site: 'Реквизиты ООО "МЕДСКАН": ИНН / КПП 7725819008 / 772801001',
    )

    evidence = sync_deals._site_identity_evidence(
        "medscannet.ru",
        _company(TITLE="медскан.рф"),
        "7725819008",
    )

    assert "site_contains_inn:7725819008" in evidence


def test_verified_site_rejects_working_but_unrelated_site(monkeypatch):
    monkeypatch.setattr(sync_deals, "_verified_site", ORIG_VERIFIED_SITE)
    monkeypatch.setattr(sync_deals, "_is_working_site", lambda site: True)
    monkeypatch.setattr(sync_deals, "_site_identity_text", lambda site: "Чужая компания без реквизитов")

    verification = sync_deals._verified_site(
        "example.ru",
        _company(TITLE="медскан.рф"),
        "7725819008",
    )

    assert verification.working is True
    assert verification.identity_verified is False


def test_new_telemarketing_deal_assignee_rotates_between_daria_and_arkady():
    assert sync_deals.telemarketing_assignee_for_new_deal(rotation_index=0) == "2772"
    assert sync_deals.telemarketing_assignee_for_new_deal(rotation_index=1) == "2832"
    assert sync_deals.telemarketing_assignee_for_new_deal(rotation_index=2) == "2772"


def test_refusal_deal_on_daria_returns_to_arkady():
    fields, skipped = sync_deals.build_telemarketing_existing_deal_fields(
        _deal(STAGE_ID="C50:APOLOGY", ASSIGNED_BY_ID="2772", CLOSED="Y"),
    )

    assert fields["CATEGORY_ID"] == "50"
    assert fields["STAGE_ID"] == "C50:NEW"
    assert fields["SOURCE_ID"] == "12"
    assert fields["CLOSED"] == "N"
    assert fields["ASSIGNED_BY_ID"] == "2832"
    assert "ASSIGNED_BY_ID" not in skipped


def test_apology_stage_on_arkady_returns_to_daria():
    fields, _ = sync_deals.build_telemarketing_existing_deal_fields(
        _deal(STAGE_ID="C50:APOLOGY", ASSIGNED_BY_ID="2832", CLOSED="Y"),
    )

    assert fields["ASSIGNED_BY_ID"] == "2772"


def test_refusal_deal_on_other_assignee_uses_rotation():
    fields, _ = sync_deals.build_telemarketing_existing_deal_fields(
        _deal(STAGE_ID="C50:LOSE", ASSIGNED_BY_ID="686", CLOSED="Y"),
        rotation_index=1,
    )

    assert fields["ASSIGNED_BY_ID"] == "2832"


def test_non_refusal_existing_deal_is_not_reassigned_by_telemarketing_workflow():
    fields, skipped = sync_deals.build_telemarketing_existing_deal_fields(
        _deal(STAGE_ID="C50:NEW", ASSIGNED_BY_ID="2772", CLOSED="N"),
        rotation_index=1,
    )

    assert "ASSIGNED_BY_ID" not in fields
    assert skipped["ASSIGNED_BY_ID"] == "not_refusal_deal"


def test_base_stage_C50_UC_1S1KIU_is_not_refusal():
    assert sync_deals._is_refusal_deal({"STAGE_ID": "C50:UC_1S1KIU"}) is False


def test_apology_stage_is_refusal_regression():
    assert sync_deals._is_refusal_deal({"STAGE_ID": "C50:APOLOGY"}) is True


def test_lose_stage_is_refusal_regression():
    assert sync_deals._is_refusal_deal({"STAGE_ID": "C50:LOSE"}) is True


def test_unknown_stage_with_semantic_F_is_refusal():
    assert sync_deals._is_refusal_deal(
        {"STAGE_ID": "C50:NEW_LOSE_VARIANT", "STAGE_SEMANTIC_ID": "F"}
    ) is True


def test_open_stage_with_semantic_P_is_not_refusal():
    assert sync_deals._is_refusal_deal(
        {"STAGE_ID": "C50:UC_1S1KIU", "STAGE_SEMANTIC_ID": "P"}
    ) is False


def test_base_stage_telemarketing_workflow_does_not_reassign_assignee():
    fields, skipped = sync_deals.build_telemarketing_existing_deal_fields(
        _deal(STAGE_ID="C50:UC_1S1KIU", ASSIGNED_BY_ID="2832", CLOSED="N"),
        rotation_index=0,
    )

    assert "ASSIGNED_BY_ID" not in fields
    assert skipped["ASSIGNED_BY_ID"] == "not_refusal_deal"


def test_run_telemarketing_workflow_returns_refusal_deal_to_other_assignee():
    bx = FakeBitrix(
        companies={"100": _company()},
        deals_by_company={
            "100": [
                _deal(
                    STAGE_ID="C50:APOLOGY",
                    ASSIGNED_BY_ID="2772",
                    CLOSED="Y",
                    CATEGORY_ID="50",
                    SOURCE_ID="UC_4E1HRV",
                )
            ]
        },
    )

    summary = sync_deals.run(
        bx,
        company_id="100",
        dry_run=False,
        active_only=False,
        telemarketing_workflow=True,
    )

    assert summary["updated"] == 1
    _, fields = bx.update_deal_calls[0]
    assert fields["STAGE_ID"] == "C50:NEW"
    assert fields["SOURCE_ID"] == "12"
    assert fields["CLOSED"] == "N"
    assert fields["ASSIGNED_BY_ID"] == "2832"


def _tm_deal(deal_id: str, *, company_id: str = "20606", stage_id: str = "C50:NEW") -> dict:
    return _deal(
        ID=deal_id,
        COMPANY_ID=company_id,
        CATEGORY_ID="50",
        STAGE_ID=stage_id,
        CLOSED="N",
        ASSIGNED_BY_ID="2772",
        DATE_MODIFY="2026-05-17T10:00:00+03:00",
    )


def test_sync_deals_can_run_scoped_telemarketing_dedupe_after_company_sync():
    deals = [
        _tm_deal("17904", stage_id="C50:NEW"),
        _tm_deal("21588", stage_id="C50:UC_1S1KIU"),
    ]
    bx = FakeBitrix(
        companies={"20606": _company(ID="20606")},
        deals_by_company={"20606": deals},
        deals_by_id={deal["ID"]: deal for deal in deals},
    )

    summary = sync_deals.run(
        bx,
        company_id="20606",
        dry_run=False,
        dedupe_telemarketing=True,
    )

    close_calls = [
        fields for deal_id, fields in bx.update_deal_calls
        if deal_id == "21588" and fields.get("STAGE_ID") == "C50:APOLOGY"
    ]
    assert close_calls
    assert close_calls[0]["CLOSED"] == "Y"
    assert close_calls[0][HOLD_REASON_FIELD] == "8544"
    assert summary["telemarketing_dedupe"]["merged"] == 1


def test_sync_deals_dedupe_not_called_without_flag():
    deals = [
        _tm_deal("17904", stage_id="C50:NEW"),
        _tm_deal("21588", stage_id="C50:UC_1S1KIU"),
    ]
    bx = FakeBitrix(
        companies={"20606": _company(ID="20606")},
        deals_by_company={"20606": deals},
        deals_by_id={deal["ID"]: deal for deal in deals},
    )

    summary = sync_deals.run(bx, company_id="20606", dry_run=False)

    assert "telemarketing_dedupe" not in summary
    assert not any(fields.get("STAGE_ID") == "C50:APOLOGY" for _, fields in bx.update_deal_calls)


def test_sync_deals_dedupe_dry_run_does_not_write():
    deals = [
        _tm_deal("17904", stage_id="C50:NEW"),
        _tm_deal("21588", stage_id="C50:UC_1S1KIU"),
    ]
    bx = FakeBitrix(
        companies={"20606": _company(ID="20606")},
        deals_by_company={"20606": deals},
        deals_by_id={deal["ID"]: deal for deal in deals},
    )

    summary = sync_deals.run(
        bx,
        company_id="20606",
        dry_run=True,
        dedupe_telemarketing=True,
    )

    assert not any(fields.get("STAGE_ID") == "C50:APOLOGY" for _, fields in bx.update_deal_calls)
    assert summary["telemarketing_dedupe"]["dry_run_merged"] == 1


def test_sync_deals_can_run_scoped_auto_reject_after_company_sync():
    deal = _tm_deal("20872", company_id="12282", stage_id="C50:NEW")
    bx = FakeBitrix(
        companies={"12282": _company(ID="12282", UF_CRM_1737098549301="6672000")},
        deals_by_company={"12282": [deal]},
        deals_by_id={"20872": deal},
    )

    summary = sync_deals.run(
        bx,
        company_id="12282",
        dry_run=False,
        auto_reject_telemarketing=True,
    )

    close_calls = [
        fields for deal_id, fields in bx.update_deal_calls
        if deal_id == "20872" and fields.get("STAGE_ID") == "C50:APOLOGY"
    ]
    assert close_calls
    assert close_calls[0][HOLD_REASON_FIELD] == "8542"
    assert summary["auto_reject_telemarketing"]["rejected_8542"] == 1


def test_sync_deals_auto_reject_not_called_without_flag():
    deal = _tm_deal("20872", company_id="12282", stage_id="C50:NEW")
    bx = FakeBitrix(
        companies={"12282": _company(ID="12282", UF_CRM_1737098549301="6672000")},
        deals_by_company={"12282": [deal]},
        deals_by_id={"20872": deal},
    )

    summary = sync_deals.run(bx, company_id="12282", dry_run=False)

    assert "auto_reject_telemarketing" not in summary
    assert not any(fields.get("STAGE_ID") == "C50:APOLOGY" for _, fields in bx.update_deal_calls)


def test_sync_deals_auto_reject_dry_run_does_not_write():
    deal = _tm_deal("20872", company_id="12282", stage_id="C50:NEW")
    bx = FakeBitrix(
        companies={"12282": _company(ID="12282", UF_CRM_1737098549301="6672000")},
        deals_by_company={"12282": [deal]},
        deals_by_id={"20872": deal},
    )

    summary = sync_deals.run(
        bx,
        company_id="12282",
        dry_run=True,
        auto_reject_telemarketing=True,
    )

    assert not any(fields.get("STAGE_ID") == "C50:APOLOGY" for _, fields in bx.update_deal_calls)
    assert summary["auto_reject_telemarketing"]["dry_run_8542"] == 1


def test_sync_deals_combines_dedupe_and_auto_reject():
    winner = _tm_deal("20872", company_id="12282", stage_id="C50:NEW")
    loser = _tm_deal("21588", company_id="12282", stage_id="C50:UC_1S1KIU")
    bx = FakeBitrix(
        companies={"12282": _company(ID="12282", UF_CRM_1737098549301="6672000")},
        deals_by_company={"12282": [winner, loser]},
        deals_by_id={"20872": winner, "21588": loser},
    )

    summary = sync_deals.run(
        bx,
        company_id="12282",
        dry_run=False,
        dedupe_telemarketing=True,
        auto_reject_telemarketing=True,
    )

    assert summary["telemarketing_dedupe"]["merged"] == 1
    assert summary["auto_reject_telemarketing"]["rejected_8542"] >= 1
    assert any(
        deal_id == "21588" and fields.get(HOLD_REASON_FIELD) == "8544"
        for deal_id, fields in bx.update_deal_calls
    )
    assert any(
        deal_id == "20872" and fields.get(HOLD_REASON_FIELD) == "8542"
        for deal_id, fields in bx.update_deal_calls
    )
