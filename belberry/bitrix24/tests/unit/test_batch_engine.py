from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from belberry.bitrix24.config.loader import load_config
from belberry.bitrix24.orchestration.batch_engine import (
    BatchEngineDeps,
    _log,
    _workspace_root,
    parse_groups,
    run_apply_batch,
    run_dry_run_batch,
)
from belberry.bitrix24.orchestration.ledger import MergeLedgerRecord, append_record
from belberry.bitrix24.policies.operation_key import build_operation_key
from belberry.bitrix24.providers.bitrix_reconciler import ReconcileSettings
from belberry.bitrix24.providers.google_sheets import SheetSnapshot


def _valid_env(workspace_root: Path) -> dict[str, str]:
    return {
        "BELBERRY_BITRIX24_TIMEZONE": "Europe/Moscow",
        "BELBERRY_BITRIX24_PORTAL_BASE_URL": "https://portal.example",
        "BELBERRY_BITRIX24_DEFAULT_MODE": "dry-run",
        "BELBERRY_BITRIX24_REQUIRE_APPLY_CONFIRMATION": "true",
        "BELBERRY_BITRIX24_PROCESS_LOCK_PATH": "state/duplicate-merge.lock",
        "BELBERRY_BITRIX24_LEDGER_PATH": "state/duplicate-merge-ledger.jsonl",
        "BELBERRY_BITRIX24_DUPLICATES_SHEET_ID": "sheet-123",
        "BELBERRY_BITRIX24_DUPLICATES_WORK_SHEET": "Дубли",
        "BELBERRY_BITRIX24_DUPLICATES_ARCHIVE_SHEET": "Объединено",
        "BELBERRY_BITRIX24_DUPLICATES_SOURCE_SHEET": "Источник",
        "BELBERRY_BITRIX24_GOOGLE_SERVICE_ACCOUNT_JSON": "state/google-sa.json",
        "BELBERRY_BITRIX24_APP_STATE_DIR": "state/bitrix-oauth",
    }


class FakeSheets:
    def __init__(self, rows=()) -> None:
        self.calls: list[tuple[str, str]] = []
        self.snapshot = SheetSnapshot(
            sheet_id="sheet-123",
            sheet_name="Источник",
            header=("Домен", "Сделки", "Основная сделка"),
            rows=tuple(rows)
            or (
                ("example.ru", "10,20", "10"),
                ("second.ru", "30,40", "30"),
            ),
            fetched_at_msk="2026-05-10T12:30:00+03:00",
        )

    def read_snapshot(self, sheet_id: str, sheet_name: str) -> SheetSnapshot:
        self.calls.append((sheet_id, sheet_name))
        return self.snapshot


class FakeBitrix:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.fail_deal = ""
        self.fail_method = ""

    def call_method(self, method, params=None, *, default=None):
        self.calls.append((method, params))
        params = dict(params or {})
        deal_id = str(params.get("id") or params.get("filter", {}).get("ENTITY_ID") or params.get("filter", {}).get("OWNER_ID") or "")
        if self.fail_method == method and self.fail_deal and deal_id == self.fail_deal:
            raise RuntimeError("boom https://secret.example/path")
        if method == "crm.deal.get":
            return {
                "ID": deal_id,
                "TITLE": f"Deal {deal_id}",
                "COMPANY_ID": "777",
                "CONTACT_ID": "500",
                "DATE_CREATE": f"2026-05-{int(deal_id) % 28 + 1:02d}T10:00:00+03:00",
                "STAGE_ID": "NEW",
                "ASSIGNED_BY_ID": "1",
                "BEGINDATE": "2026-05-10",
                "CLOSEDATE": "2026-05-20",
                "OPENED": "Y",
                "TYPE_ID": "SALE",
            }
        if method in {"crm.deal.productrows.get", "crm.timeline.comment.list", "crm.status.list"}:
            return []
        if method == "crm.deal.contact.items.get":
            return [{"CONTACT_ID": "500", "SORT": "10", "ROLE_ID": "0"}]
        raise AssertionError(method)

    def call_payload(self, method, params=None, *, default=None):
        self.calls.append((method, params))
        if method == "crm.category.list":
            return {"result": {"categories": []}}
        raise AssertionError(method)

    def list_method(self, method, params=None, *, limit=None):
        self.calls.append((method, params))
        if method == "crm.activity.list":
            return []
        raise AssertionError(method)


class BatchEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
        (self.root / "state").mkdir()
        self.config = load_config(_valid_env(self.root), workspace_root=self.root)
        self.now = datetime(2026, 5, 10, 9, 30, tzinfo=timezone.utc)

    def deps(self, sheets=None, oauth=None) -> BatchEngineDeps:
        return BatchEngineDeps(
            config=self.config,
            sheets=sheets or FakeSheets(),
            oauth=oauth or FakeBitrix(),
            reconciler_settings=ReconcileSettings(portal_base_url=self.config.portal_base_url),
            now_utc=lambda: self.now,
        )

    def test_parse_groups_accepts_ru_headers_and_normalizes(self) -> None:
        groups = parse_groups(
            ("Домен", "Сделки", "Основная сделка"),
            (("https://www.Example.ru/", "20, 10", "10"),),
        )

        self.assertEqual(groups[0].domain, "example.ru")
        self.assertEqual(groups[0].deal_ids, ("20", "10"))
        self.assertEqual(groups[0].target_id, "10")

    def test_parse_groups_rejects_missing_columns_and_partial_rows(self) -> None:
        with self.assertRaisesRegex(ValueError, "target_id"):
            parse_groups(("domain", "deal_ids"), ())
        with self.assertRaisesRegex(ValueError, "row 2"):
            parse_groups(("domain", "deal_ids", "target_id"), (("example.ru", "", "10"),))

    def test_parse_groups_skips_empty_rows(self) -> None:
        groups = parse_groups(
            ("domain", "deal_ids", "target_id"),
            (("", "", ""), ("example.ru", "10,20", "10")),
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].row_number, 3)

    def test_workspace_root_prefers_belberry_bitrix24_path(self) -> None:
        root = self.root / "belberry" / "bitrix24"
        state = root / "state"
        state.mkdir(parents=True)
        cfg = load_config(_valid_env(root), workspace_root=root)

        self.assertEqual(_workspace_root(cfg), root.resolve())

    def test_log_dispatches_all_levels(self) -> None:
        class Logger:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str]] = []

            def info(self, event, **fields):
                self.calls.append(("info", event))

            def warn(self, event, **fields):
                self.calls.append(("warn", event))

            def error(self, event, **fields):
                self.calls.append(("error", event))

        logger = Logger()
        _log(logger, "info", "started")
        _log(logger, "warn", "careful")
        _log(logger, "error", "failed")

        self.assertEqual(logger.calls, [("info", "started"), ("warn", "careful"), ("error", "failed")])

    def test_run_dry_run_batch_default_processes_one_group(self) -> None:
        result = run_dry_run_batch(deps=self.deps())

        self.assertEqual(result.mode, "dry-run")
        self.assertEqual(len(result.packages), 1)
        self.assertEqual(result.packages[0].artifact.domain, "example.ru")
        self.assertEqual(result.errors, ())
        self.assertTrue(result.packages[0].artifact_path.exists())
        self.assertFalse(self.config.process_lock_path.exists())

    def test_group_domain_and_max_groups_filter_selection(self) -> None:
        result = run_dry_run_batch(deps=self.deps(), group_domain="second.ru", max_groups=2)

        self.assertEqual(len(result.packages), 1)
        self.assertEqual(result.packages[0].artifact.domain, "second.ru")

    def test_skips_already_applied_operation_key(self) -> None:
        operation_key = build_operation_key(
            sheet_id=self.config.sheet_id,
            domain="example.ru",
            target_id="10",
            deal_ids=("10", "20"),
        )
        append_record(
            self.config.ledger_path,
            MergeLedgerRecord(
                operation_key=operation_key,
                sheet_id=self.config.sheet_id,
                domain="example.ru",
                target_id="10",
                deal_ids=("10", "20"),
                policy_version="2026.05.10",
                status="crm_applied_sheet_archived",
                crm_status="applied",
                sheet_status="archived",
            ),
        )

        result = run_dry_run_batch(deps=self.deps())

        self.assertEqual(result.packages, ())
        self.assertEqual(result.skipped_groups[0]["operation_key"], operation_key)
        self.assertEqual(result.skipped_groups[0]["reason"], "operation_already_applied")

    def test_group_errors_are_structured_and_sanitized(self) -> None:
        bitrix = FakeBitrix()
        bitrix.fail_deal = "10"
        bitrix.fail_method = "crm.timeline.comment.list"

        result = run_dry_run_batch(deps=self.deps(oauth=bitrix))

        self.assertEqual(result.packages, ())
        self.assertEqual(result.errors[0]["group"]["domain"], "example.ru")
        self.assertEqual(result.errors[0]["exception_type"], "BitrixReconcileError")
        self.assertEqual(result.errors[0]["message"], "child read failed: crm.timeline.comment.list for deal 10")

    def test_source_read_error_returns_result_error(self) -> None:
        class BrokenSheets(FakeSheets):
            def read_snapshot(self, sheet_id, sheet_name):
                raise RuntimeError("sheet unavailable")

        result = run_dry_run_batch(deps=self.deps(sheets=BrokenSheets()))

        self.assertEqual(result.packages, ())
        self.assertEqual(result.errors[0]["exception_type"], "RuntimeError")

    def test_invalid_max_groups_rejected_before_lock(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_groups"):
            run_dry_run_batch(deps=self.deps(), max_groups=0)

    def test_apply_branch_is_not_implemented(self) -> None:
        with self.assertRaises(NotImplementedError):
            run_apply_batch(deps=self.deps(), run_id="run", provided_token="token")

    def test_run_id_generation_is_patchable_for_result(self) -> None:
        with patch(
            "belberry.bitrix24.orchestration.batch_engine.generate_run_id",
            side_effect=("20260510-123000-MSK-aaaaaaaa", "20260510-123001-MSK-bbbbbbbb"),
        ):
            result = run_dry_run_batch(deps=self.deps())

        self.assertEqual(result.run_id, "20260510-123001-MSK-bbbbbbbb")


if __name__ == "__main__":
    unittest.main()
