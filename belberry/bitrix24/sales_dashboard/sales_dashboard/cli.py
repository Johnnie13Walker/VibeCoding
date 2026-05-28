"""CLI entry-point.

    python -m sales_dashboard.cli etl                # инкрементальный ETL
    python -m sales_dashboard.cli etl --full         # полная перезаливка
    python -m sales_dashboard.cli check              # проверка доступа (Bitrix + Sheets)
    python -m sales_dashboard.cli user-sync          # синк прав Looker Studio с Bitrix
    python -m sales_dashboard.cli user-sync --dry-run
"""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    p = argparse.ArgumentParser(prog="sales_dashboard")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_etl = sub.add_parser("etl", help="запустить ETL")
    p_etl.add_argument("--full", action="store_true", help="полная перезаливка")

    sub.add_parser("check", help="проверка доступа к Bitrix и Sheets")

    p_us = sub.add_parser("user-sync", help="синк прав Looker Studio с Bitrix")
    p_us.add_argument("--dry-run", action="store_true")

    args = p.parse_args()

    if args.cmd == "etl":
        from .etl import run_etl, print_run

        run = run_etl(full=args.full)
        print_run(run)
        return 0 if all(r.ok for r in run.results) else 1

    if args.cmd == "check":
        return cmd_check()

    if args.cmd == "user-sync":
        from .user_sync import run_user_sync

        return run_user_sync(dry_run=args.dry_run)

    return 1


def cmd_check() -> int:
    from . import config
    from .bitrix_client import BitrixClient
    from .sheets_client import SheetsClient

    print("== Bitrix ==")
    bx = BitrixClient(log_path=config.LOG_PATH)
    try:
        prof = bx.call("profile")
        u = prof.get("result") or {}
        print(f"  OK: ID={u.get('ID')} {u.get('NAME')} {u.get('LAST_NAME')}")
    except Exception as e:
        print(f"  FAIL: {e}")
        return 1

    print("== Sheets ==")
    if not config.SHEET_ID:
        print("  SKIP: config.SHEET_ID пуст. Создай Sheet и пропиши ID.")
        return 1
    try:
        sh = SheetsClient(config.SHEET_ID, config.SERVICE_ACCOUNT_JSON)
        tabs = sh.get_tabs()
        print(f"  OK: tabs = {list(tabs.keys())}")
    except Exception as e:
        print(f"  FAIL: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
