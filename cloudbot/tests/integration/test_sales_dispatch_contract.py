from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.lev_petrovich.legacy_sales_agent.report_contract import SALES_DISPATCH_SEQUENCE
from cloudbot.bot.telegram.telegram_handler import handle_update


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "bitrix_crm_fixtures.json"


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

    def test_followup_workflow_uses_supported_runtime_report_type(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sales-followup-workflow-") as tmp_dir:
            env = {
                **os.environ,
                "REPORT_DIR": tmp_dir,
                "SALES_LOG_FILE": str(Path(tmp_dir) / "sales_agent.log"),
                "BITRIX_CRM_FIXTURES_FILE": str(FIXTURE),
                "TELEGRAM_DRY_RUN": "1",
                "SALES_TELEGRAM_DRY_RUN": "1",
                "SALES_TELEGRAM_CHAT_ID": "123",
                "TELEGRAM_BOT_TOKEN": "dummy",
            }
            completed = subprocess.run(
                ["bash", "infra/orchestrator/workflows/sales_followup.sh"],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
            reports = sorted(Path(tmp_dir).glob("sales_followup_*.txt"))
            report_text = reports[0].read_text(encoding="utf-8") if reports else ""

        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertEqual(len(reports), 1)
        self.assertIn("Контроль до конца дня", report_text)
        self.assertNotIn("Фокус РОПа", report_text)

    def test_weekly_workflow_passes_dry_run_format_validation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sales-weekly-workflow-") as tmp_dir:
            env = {
                **os.environ,
                "REPORT_DIR": tmp_dir,
                "SALES_LOG_FILE": str(Path(tmp_dir) / "sales_agent.log"),
                "BITRIX_CRM_FIXTURES_FILE": str(FIXTURE),
                "TELEGRAM_DRY_RUN": "1",
                "SALES_TELEGRAM_DRY_RUN": "1",
                "SALES_WEEKLY_TELEGRAM_CHAT_ID": "123",
                "TELEGRAM_BOT_TOKEN": "dummy",
            }
            completed = subprocess.run(
                ["bash", "infra/orchestrator/workflows/sales_weekly_review.sh"],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
