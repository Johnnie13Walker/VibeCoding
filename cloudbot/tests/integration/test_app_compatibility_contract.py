from __future__ import annotations

import importlib
import unittest


class AppCompatibilityContractTests(unittest.TestCase):
    def test_canonical_app_imports_are_available(self) -> None:
        for module_name in (
            "apps.larisa_ivanovna",
            "apps.larisa_ivanovna.agent",
            "apps.finansist",
            "apps.finansist.agent",
            "apps.lev_petrovich",
            "apps.lev_petrovich.agent",
            "apps.lev_petrovich.legacy_sales_agent",
            "apps.lev_petrovich.legacy_sales_agent.sales_agent",
            "apps.lev_petrovich.legacy_sales_agent.report_contract",
        ):
            with self.subTest(module_name=module_name):
                self.assertIsNotNone(importlib.import_module(module_name))

    def test_legacy_agent_shims_still_resolve(self) -> None:
        for module_name in (
            "agents.larisa_ivanovna",
            "agents.larisa_ivanovna.agent",
            "agents.finansist",
            "agents.finansist.agent",
            "agents.lev_petrovich",
            "agents.lev_petrovich.agent",
            "agents.sales_agent",
            "agents.sales_agent.sales_agent",
            "agents.sales_agent.report_contract",
        ):
            with self.subTest(module_name=module_name):
                self.assertIsNotNone(importlib.import_module(module_name))

    def test_sales_agent_shim_points_to_canonical_sales_agent_class(self) -> None:
        canonical = importlib.import_module("apps.lev_petrovich.legacy_sales_agent.sales_agent")
        shim = importlib.import_module("agents.sales_agent.sales_agent")

        self.assertIs(shim.SalesAgent, canonical.SalesAgent)
        self.assertIs(shim.SalesAgentError, canonical.SalesAgentError)

    def test_lev_petrovich_entrypoint_uses_canonical_sales_agent_class(self) -> None:
        canonical = importlib.import_module("apps.lev_petrovich.legacy_sales_agent.sales_agent")
        lev_agent = importlib.import_module("apps.lev_petrovich.agent")

        self.assertIs(lev_agent.LevPetrovichAgent, canonical.SalesAgent)
        self.assertIs(lev_agent.LevPetrovichAgentError, canonical.SalesAgentError)
