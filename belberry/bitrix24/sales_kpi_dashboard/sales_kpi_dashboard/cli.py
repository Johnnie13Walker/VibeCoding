from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from google.oauth2.service_account import Credentials

from sales_dashboard.bitrix_client import BitrixClient
from sales_dashboard.sheets_client import SheetsClient

from .aggregator import aggregate
from .alerts import append_sync_error, check_and_alert
from .config import GOOGLE_SA_KEY, MOSCOW_TZ, OUTPUT_SHEET_ID
from .sheet_schema import bootstrap_schema
from .writer import SheetsWriter

PROBE_TAB = "_write_probe_tmp"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sales_kpi_dashboard")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check")
    refresh = subparsers.add_parser("refresh")
    refresh.add_argument("--dry-run", action="store_true")
    bootstrap = subparsers.add_parser("bootstrap-schema")
    bootstrap.add_argument("--dry-run", action="store_true")
    alert_check = subparsers.add_parser("alert-check")
    alert_check.add_argument("--threshold", type=int, default=2)
    sync_error = subparsers.add_parser("sync-log-error")
    sync_error.add_argument("--phase", default="phase 4")
    sync_error.add_argument("--error", required=True)
    return parser


def run_check() -> int:
    try:
        bitrix = BitrixClient()
        profile = bitrix.call("profile").get("result") or {}
        print(f"Bitrix: OK ID={profile.get('ID')} NAME={profile.get('NAME')}")

        creds = Credentials.from_service_account_file(
            str(GOOGLE_SA_KEY),
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"],
        )
        service_account_email = getattr(creds, "service_account_email", "")
        print(f"Service account: OK {service_account_email}")

        sheets = SheetsClient(OUTPUT_SHEET_ID, GOOGLE_SA_KEY)
        meta = sheets._execute(
            sheets.service.spreadsheets().get(spreadsheetId=OUTPUT_SHEET_ID)
        )
        timezone = meta.get("properties", {}).get("timeZone", "")
        probe_sheet_id = _create_probe_tab(sheets)
        _delete_probe_tab(sheets, probe_sheet_id)
        if timezone == "Europe/Moscow":
            print("Sheet: OK TZ=Europe/Moscow Editor=Yes")
        else:
            print(f"Sheet: WARN TZ={timezone} Editor=Yes (нужно Europe/Moscow)")
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI должен дать понятный smoke-ответ
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def _create_probe_tab(sheets: SheetsClient) -> int:
    tabs = sheets.get_tabs()
    if PROBE_TAB in tabs:
        _delete_probe_tab(sheets, tabs[PROBE_TAB])
    response = sheets._execute(
        sheets.service.spreadsheets().batchUpdate(
            spreadsheetId=OUTPUT_SHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": PROBE_TAB}}}]},
        )
    )
    return int(response["replies"][0]["addSheet"]["properties"]["sheetId"])


def _delete_probe_tab(sheets: SheetsClient, sheet_id: int) -> None:
    sheets._execute(
        sheets.service.spreadsheets().batchUpdate(
            spreadsheetId=OUTPUT_SHEET_ID,
            body={"requests": [{"deleteSheet": {"sheetId": sheet_id}}]},
        )
    )


def run_refresh(dry_run: bool) -> int:
    result = aggregate()
    if dry_run:
        payload = {
            "ts": datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
            "dry_run": True,
            "tabs": {
                name: {
                    "row_count": max(len(rows) - 1, 0) if rows and isinstance(rows[0], list) else len(rows),
                    "preview": rows[:4],
                }
                for name, rows in result.items()
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    writer = SheetsWriter()
    for tab_name, rows in result.items():
        writer.write_tab(tab_name, rows)
    print("Refresh: OK")
    return 0


def run_bootstrap_schema(dry_run: bool) -> int:
    report = bootstrap_schema(dry_run=dry_run)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def run_alert_check(threshold: int) -> int:
    failures = check_and_alert(threshold=threshold)
    print(json.dumps({"consecutive_failures": failures, "threshold": threshold}, ensure_ascii=False))
    return 0


def run_sync_log_error(phase: str, error: str) -> int:
    append_sync_error(error=error, phase=phase)
    print("sync_log error: OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "check":
        return run_check()
    if args.command == "refresh":
        return run_refresh(args.dry_run)
    if args.command == "bootstrap-schema":
        return run_bootstrap_schema(args.dry_run)
    if args.command == "alert-check":
        return run_alert_check(args.threshold)
    if args.command == "sync-log-error":
        return run_sync_log_error(args.phase, args.error)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
