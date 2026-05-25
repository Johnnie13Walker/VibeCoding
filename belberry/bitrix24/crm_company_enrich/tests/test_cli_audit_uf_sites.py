from __future__ import annotations

import argparse
import json

from crm_company_enrich import cli
from crm_company_enrich.stages import audit_uf_sites
from crm_company_enrich.stages.enrich_web import SiteAliveCheck


class FakeBitrix:
    def __init__(self):
        self.companies = [
            {
                "ID": "1",
                "TITLE": "Alive",
                "UF_CRM_5DEF838D882A2": "https://alive.example",
                "WEB": [],
            },
            {
                "ID": "2",
                "TITLE": "Dead",
                "UF_CRM_5DEF838D882A2": "https://dead.example",
                "WEB": [{"VALUE": "https://vk.com/dead"}],
            },
        ]
        self.update_company_calls: list[tuple[str, dict]] = []

    def list_companies(self, select=None, filter_=None):
        return [dict(company) for company in self.companies]

    def update_company(self, company_id, fields):
        self.update_company_calls.append((str(company_id), dict(fields)))
        return True


def test_audit_uf_sites_dry_run_returns_report(monkeypatch, tmp_path):
    bx = FakeBitrix()
    monkeypatch.setattr(
        audit_uf_sites,
        "is_site_alive",
        lambda url, **kwargs: SiteAliveCheck(url, "alive" in url, 200 if "alive" in url else None, "ok" if "alive" in url else "dns"),
    )

    report_path = tmp_path / "uf_site_audit.json"
    summary = audit_uf_sites.run(bx, dry_run=True, report_path=report_path)

    assert summary["total"] == 2
    assert summary["alive"] == 1
    assert summary["reasons"]["dns"] == 1
    assert bx.update_company_calls == []
    assert json.loads(report_path.read_text(encoding="utf-8"))["total"] == 2


def test_audit_uf_sites_live_rollback_writes_to_bitrix(monkeypatch, tmp_path):
    bx = FakeBitrix()
    monkeypatch.setattr(audit_uf_sites, "LOG_DIR", tmp_path)
    monkeypatch.setattr(cli, "_make_clients", lambda: (bx, None))
    monkeypatch.setattr(
        audit_uf_sites,
        "is_site_alive",
        lambda url, **kwargs: SiteAliveCheck(url, "alive" in url, 200 if "alive" in url else 503, "ok" if "alive" in url else "5xx"),
    )

    code = cli.cmd_audit_uf_sites(
        argparse.Namespace(live=True, rollback_to_vk=True, dry_run=False, from_sheet=False, all=True)
    )

    assert code == 0
    assert bx.update_company_calls == [("2", {"UF_CRM_5DEF838D882A2": "https://vk.com/dead"})]
    assert (tmp_path / "uf_site_audit" / "2.json").exists()
