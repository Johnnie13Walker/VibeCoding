from __future__ import annotations

import unittest

from apps.finansist.agent import FinansistAgent, FinansistDependencies
from apps.finansist.config import DEFAULT_CONFIG
from apps.finansist.providers import FinanceSourceProvider
from cloudbot.orchestrator.orchestrator import handle_incoming_message
from cloudbot.bot.telegram.commands import extract_command
from cloudbot.orchestrator.router import COMMAND_ROUTES, select_workflow


class FinansistAgentTests(unittest.TestCase):
    def _build_agent(self, *, env_data: dict[str, str] | None = None) -> FinansistAgent:
        return FinansistAgent(
            config=DEFAULT_CONFIG,
            dependencies=FinansistDependencies(
                source_provider=FinanceSourceProvider(env_data=env_data or {}),
            ),
        )

    def test_registry_contains_finance_commands(self) -> None:
        agent = self._build_agent()
        for key in (
            "get_finance_summary",
            "get_pnl_analysis",
            "get_cashflow_analysis",
            "get_expense_structure_analysis",
            "get_client_profitability_analysis",
            "/finance",
            "/pnl",
            "/cashflow",
            "/runway",
            "/expenses",
            "/clients-profit",
            "/ar",
            "/ap",
            "/finance-risks",
        ):
            self.assertIn(key, agent.registry)

    def test_google_docs_and_sheets_detected_via_url(self) -> None:
        provider = FinanceSourceProvider(
            env_data={
                "GOOGLE_SERVICE_ACCOUNT_JSON": "/tmp/google.json",
            }
        )
        snapshot = provider.build_snapshot(
            (
                "https://docs.google.com/document/d/doc-id/edit",
                "https://docs.google.com/spreadsheets/d/sheet-id/edit#gid=0",
            )
        )
        source_types = {item.source_type for item in snapshot.sources}
        self.assertIn("google_doc", source_types)
        self.assertIn("google_sheet", source_types)
        self.assertTrue(snapshot.google_docs_access_ready)
        self.assertTrue(snapshot.google_sheets_access_ready)

    def test_finance_summary_reports_missing_google_credentials(self) -> None:
        agent = self._build_agent()
        result = agent.execute(
            "get_finance_summary",
            {
                "question": "Проверь это https://docs.google.com/document/d/doc-id/edit",
                "sources": ["https://docs.google.com/spreadsheets/d/sheet-id/edit#gid=0"],
                "metrics": {},
            },
        )
        text = result["text"]
        self.assertIn("Google Docs", text)
        self.assertIn("credential path не подтвержден", text)
        self.assertIn("Нет метрики `revenue_current`", text)

    def test_finance_summary_highlights_cash_gap_and_margin_drop(self) -> None:
        agent = self._build_agent(
            env_data={
                "GOOGLE_SERVICE_ACCOUNT_JSON": "/tmp/google.json",
            }
        )
        result = agent.execute(
            "get_finance_summary",
            {
                "question": "Что с финансами?",
                "sources": [
                    "https://docs.google.com/document/d/doc-id/edit",
                    "https://docs.google.com/spreadsheets/d/sheet-id/edit#gid=0",
                ],
                "metrics": {
                    "revenue_current": 1000000,
                    "revenue_previous": 1000000,
                    "gross_profit_current": 250000,
                    "gross_profit_previous": 350000,
                    "payroll_current": 420000,
                    "payroll_previous": 330000,
                    "cash_balance_current": 150000,
                    "cash_in_4w": 350000,
                    "cash_out_4w": 700000,
                    "client_profitability": [
                        {"name": "Клиент А", "profit_margin": -0.05},
                    ],
                    "receivables_total": 600000,
                    "receivables_overdue": 210000,
                },
            },
        )
        text = result["text"]
        self.assertIn("Маржа просела", text)
        self.assertIn("ФОТ перегрет", text)
        self.assertIn("Риск кассового разрыва", text)
        self.assertIn("Клиент А", text)

    def test_router_and_telegram_command_support_finance_paths(self) -> None:
        self.assertEqual(extract_command("финансы"), "/finance")
        self.assertEqual(extract_command("/pnl"), "/pnl")
        self.assertEqual(COMMAND_ROUTES["/finance"], "finance_summary")
        self.assertEqual(
            select_workflow({"text": "/finance", "intent": ""}),
            "finance_summary",
        )
        self.assertEqual(
            select_workflow({"text": "/cashflow", "intent": ""}),
            "cashflow_analysis",
        )

    def test_orchestrator_finance_summary_uses_message_metrics(self) -> None:
        result = handle_incoming_message(
            {
                "text": "/finance",
                "command": "/finance",
                "metrics": {
                    "revenue_current": 1000000,
                    "revenue_previous": 1000000,
                    "gross_profit_current": 250000,
                    "gross_profit_previous": 350000,
                    "payroll_current": 420000,
                    "payroll_previous": 330000,
                    "cash_balance_current": 150000,
                    "cash_in_4w": 350000,
                    "cash_out_4w": 700000,
                },
                "sources": [
                    "https://docs.google.com/document/d/doc-id/edit",
                    "https://docs.google.com/spreadsheets/d/sheet-id/edit#gid=0",
                ],
            }
        )
        self.assertEqual(result.get("workflow"), "finance_summary")
        self.assertIn("Маржа просела", str(result.get("text") or ""))
