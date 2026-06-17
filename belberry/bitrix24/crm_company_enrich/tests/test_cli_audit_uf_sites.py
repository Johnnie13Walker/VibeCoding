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
        argparse.Namespace(
            live=True,
            rollback_to_vk=True,
            clear_dead=False,
            clear_dead_reasons="",
            force_with_deals=False,
            dry_run=False,
            from_sheet=False,
            all=True,
        )
    )

    assert code == 0
    assert bx.update_company_calls == [("2", {"UF_CRM_5DEF838D882A2": "https://vk.com/dead"})]
    assert (tmp_path / "uf_site_audit" / "2.json").exists()


def test_audit_uf_sites_clear_dead_only_default_reasons(monkeypatch, tmp_path):
    """clear_dead по умолчанию чистит только dns/conn_refused; 5xx остаётся нетронутым."""
    bx = FakeBitrix()
    # Расширим до 3 компаний: 1 alive, 1 dns (чистим), 1 5xx (не чистим).
    bx.companies = [
        {"ID": "1", "TITLE": "Alive", "UF_CRM_5DEF838D882A2": "https://alive.example", "WEB": []},
        {"ID": "2", "TITLE": "DNS dead", "UF_CRM_5DEF838D882A2": "https://dns.example", "WEB": []},
        {"ID": "3", "TITLE": "5xx", "UF_CRM_5DEF838D882A2": "https://flaky.example", "WEB": []},
    ]
    reasons = {"alive": "ok", "dns": "dns", "flaky": "5xx"}
    codes = {"alive": 200, "dns": None, "flaky": 503}

    def fake_check(url, **kwargs):
        for key, reason in reasons.items():
            if key in url:
                return SiteAliveCheck(url, reason == "ok", codes[key], reason)
        return SiteAliveCheck(url, False, None, "bad_url")

    monkeypatch.setattr(audit_uf_sites, "LOG_DIR", tmp_path)
    monkeypatch.setattr(audit_uf_sites, "is_site_alive", fake_check)

    summary = audit_uf_sites.run(bx, dry_run=False, clear_dead=True)

    assert summary["cleared"] == 1
    assert summary["rolled_back"] == 0
    assert bx.update_company_calls == [("2", {"UF_CRM_5DEF838D882A2": ""})]
    assert (tmp_path / "uf_site_clear" / "2.json").exists()
    assert not (tmp_path / "uf_site_clear" / "3.json").exists()


def test_audit_uf_sites_clear_dead_explicit_reasons(monkeypatch, tmp_path):
    """С явным --clear-dead-reasons=5xx чистим только 5xx, не трогая dns."""
    bx = FakeBitrix()
    bx.companies = [
        {"ID": "2", "TITLE": "DNS dead", "UF_CRM_5DEF838D882A2": "https://dns.example", "WEB": []},
        {"ID": "3", "TITLE": "5xx", "UF_CRM_5DEF838D882A2": "https://flaky.example", "WEB": []},
    ]

    def fake_check(url, **kwargs):
        if "dns" in url:
            return SiteAliveCheck(url, False, None, "dns")
        return SiteAliveCheck(url, False, 503, "5xx")

    monkeypatch.setattr(audit_uf_sites, "LOG_DIR", tmp_path)
    monkeypatch.setattr(audit_uf_sites, "is_site_alive", fake_check)

    summary = audit_uf_sites.run(
        bx, dry_run=False, clear_dead=True, clear_dead_reasons=("5xx",)
    )

    assert summary["cleared"] == 1
    assert bx.update_company_calls == [("3", {"UF_CRM_5DEF838D882A2": ""})]


def test_audit_uf_sites_clear_dead_mutually_exclusive_with_rollback():
    bx = FakeBitrix()
    import pytest
    with pytest.raises(ValueError, match="взаимоисключающи"):
        audit_uf_sites.run(bx, dry_run=False, rollback_to_vk=True, clear_dead=True)


def test_audit_uf_sites_cli_rejects_clear_dead_without_live(monkeypatch):
    """--clear-dead без --live → должен по-прежнему запускать dry_run, без exit code 2."""
    bx = FakeBitrix()
    monkeypatch.setattr(cli, "_make_clients", lambda: (bx, None))
    monkeypatch.setattr(
        audit_uf_sites,
        "is_site_alive",
        lambda url, **kwargs: SiteAliveCheck(url, "alive" in url, 200, "ok"),
    )
    code = cli.cmd_audit_uf_sites(
        argparse.Namespace(
            live=False,
            rollback_to_vk=False,
            clear_dead=True,
            clear_dead_reasons="",
            force_with_deals=False,
            dry_run=True,
            from_sheet=False,
            all=True,
        )
    )
    assert code == 0
    assert bx.update_company_calls == []


def test_audit_uf_sites_cli_live_requires_action(monkeypatch):
    """--live без --rollback-to-vk и без --clear-dead → exit 2."""
    bx = FakeBitrix()
    monkeypatch.setattr(cli, "_make_clients", lambda: (bx, None))
    code = cli.cmd_audit_uf_sites(
        argparse.Namespace(
            live=True,
            rollback_to_vk=False,
            clear_dead=False,
            clear_dead_reasons="",
            force_with_deals=False,
            dry_run=False,
            from_sheet=False,
            all=True,
        )
    )
    assert code == 2


class FakeBitrixWithDeals(FakeBitrix):
    """FakeBitrix с поддержкой batch + call (crm.company.list, crm.deal.list)."""

    def __init__(self, deals_per_cid: dict[str, list] | None = None):
        super().__init__()
        self.deals_per_cid = deals_per_cid or {}

    def call(self, method, params):
        params = params or {}
        if method == "crm.company.list":
            start = int(params.get("start") or 0)
            page = [dict(c) for c in self.companies[start:start + 50]]
            return {"result": page, "total": len(self.companies)}
        if method == "crm.deal.list":
            cid = str(params.get("filter", {}).get("COMPANY_ID") or "")
            return {"result": self.deals_per_cid.get(cid, [])}
        return {"result": []}

    def batch(self, commands):
        result = {}
        for key, (method, params) in commands.items():
            resp = self.call(method, params)
            result[key] = resp.get("result", [])
        return result


def test_audit_uf_sites_clear_dead_skips_company_with_deals(monkeypatch, tmp_path):
    """По умолчанию clear_dead НЕ трогает компанию, у которой есть сделки."""
    deals_per_cid = {"2": [{"ID": "100", "CATEGORY_ID": "10", "STAGE_ID": "C10:WON", "CLOSED": "Y"}]}
    bx = FakeBitrixWithDeals(deals_per_cid=deals_per_cid)
    bx.companies = [
        {"ID": "1", "TITLE": "Alive", "UF_CRM_5DEF838D882A2": "https://alive.example", "WEB": []},
        {"ID": "2", "TITLE": "Dead with WON", "UF_CRM_5DEF838D882A2": "https://dns.example", "WEB": []},
        {"ID": "3", "TITLE": "Dead no deals", "UF_CRM_5DEF838D882A2": "https://other-dns.example", "WEB": []},
    ]
    monkeypatch.setattr(audit_uf_sites, "LOG_DIR", tmp_path)
    monkeypatch.setattr(
        audit_uf_sites, "is_site_alive",
        lambda url, **kwargs: SiteAliveCheck(url, "alive" in url, 200 if "alive" in url else None, "ok" if "alive" in url else "dns"),
    )
    summary = audit_uf_sites.run(bx, dry_run=False, clear_dead=True)
    assert summary["cleared"] == 1  # только #3 — без сделок
    assert summary["skipped_has_deals"] == 1  # #2 пропущена защитой
    assert bx.update_company_calls == [("3", {"UF_CRM_5DEF838D882A2": ""})]
    actions_by_id = {r["company_id"]: r["action"] for r in summary["results"]}
    assert actions_by_id["2"] == "skip_has_deals"
    assert actions_by_id["3"] == "clear"


def test_audit_uf_sites_clear_dead_force_with_deals_clears_anyway(monkeypatch, tmp_path):
    """--force-with-deals выключает защиту и чистит UF даже у компаний со сделками."""
    deals_per_cid = {"2": [{"ID": "100", "CATEGORY_ID": "10", "STAGE_ID": "C10:WON", "CLOSED": "Y"}]}
    bx = FakeBitrixWithDeals(deals_per_cid=deals_per_cid)
    bx.companies = [
        {"ID": "2", "TITLE": "Dead with WON", "UF_CRM_5DEF838D882A2": "https://dns.example", "WEB": []},
    ]
    monkeypatch.setattr(audit_uf_sites, "LOG_DIR", tmp_path)
    monkeypatch.setattr(
        audit_uf_sites, "is_site_alive",
        lambda url, **kwargs: SiteAliveCheck(url, False, None, "dns"),
    )
    summary = audit_uf_sites.run(
        bx, dry_run=False, clear_dead=True,
        skip_if_has_deals=False, force_with_deals=True,
    )
    assert summary["cleared"] == 1
    assert summary["skipped_has_deals"] == 0
    assert bx.update_company_calls == [("2", {"UF_CRM_5DEF838D882A2": ""})]
