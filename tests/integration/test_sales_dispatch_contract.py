from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from apps.lev_petrovich.legacy_sales_agent.report_contract import SALES_DISPATCH_SEQUENCE
from cloudbot.bot.telegram.telegram_handler import handle_update


class SalesDispatchContractTests(unittest.TestCase):
    def test_sales_command_returns_three_messages_in_contract_order(self) -> None:
        with patch.dict(os.environ, {"SALES_COPILOT_MOCK": "1"}, clear=False):
            result = handle_update(
                {
                    "message": {
                        "text": "/sales",
                        "chat": {"id": 700700},
                        "from": {"id": 100500},
                    }
                }
            )

        self.assertEqual(result["result"].get("workflow"), "sales_brief")
        self.assertEqual(result["result"].get("report_type"), "sales")
        self.assertEqual(result["result"].get("parse_mode"), "HTML")
        self.assertIn("📊 Sales Copilot", result["reply_text"])
        self.assertEqual(len(result["result"].get("message_chunks") or []), len(SALES_DISPATCH_SEQUENCE))
        self.assertIn("Риски", result["result"]["message_chunks"][1])
        self.assertIn("Фокус РОПа", result["result"]["message_chunks"][2])

    def test_risks_command_returns_only_risks_report(self) -> None:
        with patch.dict(os.environ, {"SALES_COPILOT_MOCK": "1"}, clear=False):
            result = handle_update(
                {
                    "message": {
                        "text": "/risks",
                        "chat": {"id": 700700},
                        "from": {"id": 100500},
                    }
                }
            )

        self.assertEqual(result["result"].get("workflow"), "sales_brief")
        self.assertEqual(result["result"].get("report_type"), "risks")
        self.assertIn("Риски", result["reply_text"])
        self.assertNotIn("message_chunks", result["result"])

    def test_focus_sales_command_returns_only_focus_report(self) -> None:
        with patch.dict(os.environ, {"SALES_COPILOT_MOCK": "1"}, clear=False):
            result = handle_update(
                {
                    "message": {
                        "text": "/focus-sales",
                        "chat": {"id": 700700},
                        "from": {"id": 100500},
                    }
                }
            )

        self.assertEqual(result["result"].get("workflow"), "sales_brief")
        self.assertEqual(result["result"].get("report_type"), "focus")
        self.assertIn("Фокус РОПа", result["reply_text"])
        self.assertNotIn("message_chunks", result["result"])
