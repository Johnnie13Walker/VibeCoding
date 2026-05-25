from __future__ import annotations

from crm_company_enrich.stages import sync_deals
from crm_company_enrich.stages.enrich_web import SiteAliveCheck


class FakeBitrix:
    def __init__(self):
        self.company = {
            "ID": "100",
            "TITLE": "ООО Тест",
            "UF_CRM_5DEF838D882A2": "",
            "WEB": [],
            "UF_CRM_1737098476975": "Belberry",
            "UF_CRM_684FE59BA3C8C": "2444",
        }
        self.update_company_calls: list[tuple[str, dict]] = []

    def get_company(self, company_id):
        return dict(self.company)

    def update_company(self, company_id, fields):
        self.update_company_calls.append((str(company_id), dict(fields)))
        self.company.update(fields)
        return True


def test_sync_company_skips_dead_uf_site(monkeypatch):
    monkeypatch.setattr(
        sync_deals,
        "_verified_site",
        lambda site, company, inn="": sync_deals.SiteVerification(site, True, True, ["test"]),
    )
    monkeypatch.setattr(
        sync_deals,
        "is_site_alive",
        lambda url: SiteAliveCheck(url, False, 503, "5xx"),
    )
    bx = FakeBitrix()

    summary = sync_deals.run_company(
        bx,
        company_id="100",
        site="https://dead.example",
        dry_run=False,
    )

    assert summary["uf_site_dead"] == 1
    assert not any("UF_CRM_5DEF838D882A2" in fields for _, fields in bx.update_company_calls)
    outcome = summary["outcomes"][0]
    assert "uf_site_dead_skipped" in outcome["flags"]
    assert outcome["skipped"]["UF_CRM_5DEF838D882A2"] == "dead_site:5xx"


def test_sync_company_writes_uf_when_alive(monkeypatch):
    monkeypatch.setattr(
        sync_deals,
        "_verified_site",
        lambda site, company, inn="": sync_deals.SiteVerification(site, True, True, ["test"]),
    )
    monkeypatch.setattr(
        sync_deals,
        "is_site_alive",
        lambda url: SiteAliveCheck(url, True, 200, "ok"),
    )
    bx = FakeBitrix()

    summary = sync_deals.run_company(
        bx,
        company_id="100",
        site="https://alive.example",
        dry_run=False,
    )

    assert summary["uf_site_dead"] == 0
    assert bx.update_company_calls[0][1]["UF_CRM_5DEF838D882A2"] == "https://alive.example"


def test_cce_validate_uf_site_env_false_skips_validation(monkeypatch):
    monkeypatch.setenv("CCE_VALIDATE_UF_SITE", "0")
    monkeypatch.setattr(
        sync_deals,
        "_verified_site",
        lambda site, company, inn="": sync_deals.SiteVerification(site, True, True, ["test"]),
    )
    monkeypatch.setattr(
        sync_deals,
        "is_site_alive",
        lambda url: (_ for _ in ()).throw(AssertionError("validation must be skipped")),
    )
    bx = FakeBitrix()

    summary = sync_deals.run_company(
        bx,
        company_id="100",
        site="https://unchecked.example",
        dry_run=False,
    )

    assert summary["uf_site_dead"] == 0
    assert bx.update_company_calls[0][1]["UF_CRM_5DEF838D882A2"] == "https://unchecked.example"
