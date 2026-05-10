from __future__ import annotations

import io
import json
import runpy
import sys
import unittest
import warnings
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from belberry.bitrix24.scripts import scan_reanimation_duplicates


class FakeBitrix:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.categories = [{"id": "7", "name": "Реанимация"}]
        self.deals = [
            {"ID": "1", "TITLE": "ООО Ромашка", "DATE_CREATE": "2026-05-01", "STAGE_ID": "NEW", "ASSIGNED_BY_ID": "10"},
            {"ID": "2", "TITLE": "ооо ромашка", "DATE_CREATE": "2026-05-02", "STAGE_ID": "NEW", "ASSIGNED_BY_ID": "10"},
            {"ID": "3", "TITLE": "Single", "DATE_CREATE": "2026-05-03", "STAGE_ID": "NEW", "ASSIGNED_BY_ID": "11"},
        ]

    def call_payload(self, method, params=None, *, default=None):
        self.calls.append((method, params))
        if method == "crm.category.list":
            return {"result": {"categories": self.categories}}
        raise AssertionError(method)

    def list_method(self, method, params=None, *, limit=None):
        self.calls.append((method, params))
        if method == "crm.deal.list":
            return self.deals[:limit]
        raise AssertionError(method)


class FakeSheets:
    def __init__(self, *, existing=False, fail_on_write=False) -> None:
        self.calls: list[tuple[str, object]] = []
        self.existing = existing
        self.fail_on_write = fail_on_write

    def metadata(self, sheet_id):
        self.calls.append(("metadata", sheet_id))
        sheets = [{"properties": {"title": "Дубликаты 3"}}] if self.existing else []
        return {"sheets": sheets}

    def add_sheet(self, sheet_id, sheet_name):
        self._write("add_sheet", (sheet_id, sheet_name))
        return {"ok": True}

    def write_header(self, sheet_id, sheet_name, header):
        self._write("write_header", (sheet_id, sheet_name, tuple(header)))
        return {"ok": True}

    def append_rows(self, sheet_id, sheet_name, rows):
        self._write("append_rows", (sheet_id, sheet_name, tuple(tuple(row) for row in rows)))
        return {"ok": True}

    def _write(self, name, payload):
        if self.fail_on_write:
            raise AssertionError(f"unexpected write: {name}")
        self.calls.append((name, payload))


class ScanReanimationDuplicatesTests(unittest.TestCase):
    def test_parser_defaults(self) -> None:
        args = scan_reanimation_duplicates.build_parser().parse_args([])

        self.assertEqual(args.mode, "dry-run")
        self.assertEqual(args.funnel_name, "Реанимация")
        self.assertEqual(args.target_sheet, "Дубликаты 3")
        self.assertEqual(args.limit_deals, 10000)

    def test_find_category_id_case_insensitive(self) -> None:
        oauth = FakeBitrix()

        self.assertEqual(scan_reanimation_duplicates.find_category_id(oauth, "реанимация"), "7")

    def test_extract_categories_accepts_list_result_and_ignores_bad_items(self) -> None:
        categories = scan_reanimation_duplicates._extract_categories({"result": [{"ID": "8", "NAME": "Реанимация"}, "bad"]})

        self.assertEqual(categories, [{"ID": "8", "NAME": "Реанимация"}])

    def test_extract_categories_returns_empty_for_bad_shape(self) -> None:
        self.assertEqual(scan_reanimation_duplicates._extract_categories({"result": {"categories": "bad"}}), [])

    def test_find_category_id_rejects_empty_funnel_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "funnel_name"):
            scan_reanimation_duplicates.find_category_id(FakeBitrix(), "")

    def test_find_category_id_raises_when_missing(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "not found"):
            scan_reanimation_duplicates.find_category_id(FakeBitrix(), "Other")

    def test_load_deals_uses_read_only_method_and_limit(self) -> None:
        oauth = FakeBitrix()

        deals = scan_reanimation_duplicates.load_deals(oauth, category_id="7", limit_deals=2)

        self.assertEqual([deal["ID"] for deal in deals], ["1", "2"])
        method, params = oauth.calls[-1]
        self.assertEqual(method, "crm.deal.list")
        self.assertEqual(params["filter"], {"CATEGORY_ID": "7"})
        self.assertIn("TITLE", params["select"])
        self.assertEqual(params["order"], {"DATE_CREATE": "ASC"})

    def test_load_deals_rejects_bad_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            scan_reanimation_duplicates.load_deals(FakeBitrix(), category_id="7", limit_deals=0)

    def test_dry_run_summary_and_no_sheet_writes(self) -> None:
        sheets = FakeSheets(fail_on_write=True)

        summary = scan_reanimation_duplicates.run_scan(
            mode="dry-run",
            confirm_write=False,
            funnel_name="Реанимация",
            target_sheet="Дубликаты 3",
            limit_deals=100,
            oauth=FakeBitrix(),
            sheets=sheets,
            sheet_id="sheet-123",
            portal_base_url="https://portal.example",
        )

        self.assertEqual(summary["mode"], "dry-run")
        self.assertEqual(summary["category_id"], "7")
        self.assertEqual(summary["total_deals"], 3)
        self.assertEqual(summary["total_groups"], 1)
        self.assertEqual(summary["total_duplicate_deals"], 2)
        self.assertEqual(summary["top_groups"][0]["first_deal_id"], "1")
        self.assertEqual(sheets.calls, [])

    def test_write_without_confirm_raises_before_sheet_write(self) -> None:
        sheets = FakeSheets(fail_on_write=True)

        with self.assertRaisesRegex(SystemExit, "confirm-write"):
            scan_reanimation_duplicates.run_scan(
                mode="write",
                confirm_write=False,
                funnel_name="Реанимация",
                target_sheet="Дубликаты 3",
                limit_deals=100,
                oauth=FakeBitrix(),
                sheets=sheets,
                sheet_id="sheet-123",
                portal_base_url="https://portal.example",
            )

        self.assertEqual(sheets.calls, [])

    def test_write_existing_sheet_raises_before_any_write(self) -> None:
        sheets = FakeSheets(existing=True, fail_on_write=True)

        with self.assertRaisesRegex(RuntimeError, "already exists"):
            scan_reanimation_duplicates.run_scan(
                mode="write",
                confirm_write=True,
                funnel_name="Реанимация",
                target_sheet="Дубликаты 3",
                limit_deals=100,
                oauth=FakeBitrix(),
                sheets=sheets,
                sheet_id="sheet-123",
                portal_base_url="https://portal.example",
            )

        self.assertEqual(sheets.calls, [("metadata", "sheet-123")])

    def test_sheet_exists_handles_bad_metadata_shapes(self) -> None:
        self.assertFalse(scan_reanimation_duplicates._sheet_exists({}, "Дубликаты 3"))
        self.assertFalse(scan_reanimation_duplicates._sheet_exists({"sheets": ["bad"]}, "Дубликаты 3"))

    def test_write_creates_sheet_header_and_rows(self) -> None:
        sheets = FakeSheets()

        summary = scan_reanimation_duplicates.run_scan(
            mode="write",
            confirm_write=True,
            funnel_name="Реанимация",
            target_sheet="Дубликаты 3",
            limit_deals=100,
            oauth=FakeBitrix(),
            sheets=sheets,
            sheet_id="sheet-123",
            portal_base_url="https://portal.example",
        )

        self.assertEqual(summary, {"mode": "write", "funnel": "Реанимация", "target_sheet": "Дубликаты 3", "created": True, "total_groups": 1, "total_rows": 2})
        self.assertEqual([call[0] for call in sheets.calls], ["metadata", "add_sheet", "write_header", "append_rows"])
        rows = sheets.calls[-1][1][2]
        self.assertEqual(rows[0][0], "1")
        self.assertEqual(rows[0][1], "ооо ромашка")
        self.assertEqual(rows[0][-1], "https://portal.example/crm/deal/details/1/")

    def test_main_dry_run_prints_sanitized_json(self) -> None:
        config = SimpleNamespace(sheet_id="sheet-123", portal_base_url="https://portal.example")
        output = io.StringIO()

        with (
            patch.object(scan_reanimation_duplicates, "load_config", return_value=config),
            patch.object(scan_reanimation_duplicates.BitrixOAuth, "from_env", return_value=FakeBitrix()),
            patch.object(scan_reanimation_duplicates.GoogleSheetsClient, "from_env", return_value=FakeSheets(fail_on_write=True)),
            redirect_stdout(output),
        ):
            code = scan_reanimation_duplicates.main(["--mode", "dry-run", "--limit-deals", "10"])

        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["mode"], "dry-run")
        self.assertNotIn("access_token", output.getvalue())
        self.assertNotIn("refresh_token", output.getvalue())

    def test_module_entrypoint(self) -> None:
        with (
            patch.object(sys, "argv", ["scan_reanimation_duplicates.py", "--mode", "write"]),
            redirect_stdout(io.StringIO()),
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("ignore", RuntimeWarning)
            with self.assertRaisesRegex(SystemExit, "confirm-write") as caught:
                runpy.run_module("belberry.bitrix24.scripts.scan_reanimation_duplicates", run_name="__main__")

        self.assertNotEqual(caught.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
