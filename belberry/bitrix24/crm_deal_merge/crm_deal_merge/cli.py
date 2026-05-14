"""CLI для crm_deal_merge."""
from __future__ import annotations

import argparse
import json
import sys

from .bitrix_client import BitrixClient
from .config import LOG_PATH, SERVICE_ACCOUNT_JSON, SHEET_ID, STATE_PATH, SYNC_SCRIPT
from .sheets_client import SheetsClient


def _make_clients() -> tuple[BitrixClient, SheetsClient]:
    bx = BitrixClient(state_path=STATE_PATH, log_path=LOG_PATH)
    sheets = SheetsClient(sheet_id=SHEET_ID, service_account_path=SERVICE_ACCOUNT_JSON)
    return bx, sheets


def cmd_discover(args: argparse.Namespace) -> int:
    from .stages import discover
    bx, sheets = _make_clients()
    summary = discover.run(bx, sheets)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_discover_v2(args: argparse.Namespace) -> int:
    from .stages import discover_v2
    bx, sheets = _make_clients()
    summary = discover_v2.run(bx, sheets)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_inventory(args: argparse.Namespace) -> int:
    from .stages import inventory
    bx, sheets = _make_clients()
    summary = inventory.run(bx, sheets, limit=args.limit)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_classify(args: argparse.Namespace) -> int:
    from .stages import classify
    _, sheets = _make_clients()
    summary = classify.run(sheets)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_mark_approved(args: argparse.Namespace) -> int:
    from .stages import mark_approved
    _, sheets = _make_clients()
    summary = mark_approved.run(
        sheets,
        all_=args.all,
        status=args.status,
        company_id=args.company_id,
        domain=args.domain,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_transfer(args: argparse.Namespace) -> int:
    from .stages import transfer
    _sync_before_write()
    bx, sheets = _make_clients()
    summary = transfer.run(bx, sheets, dry_run=args.dry_run, limit=args.limit, group_key=args.group)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_close_loser(args: argparse.Namespace) -> int:
    from .stages import close_loser
    _sync_before_write()
    bx, sheets = _make_clients()
    summary = close_loser.run(bx, sheets, dry_run=args.dry_run, limit=args.limit)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from .stages import verify
    bx, sheets = _make_clients()
    summary = verify.run(bx, sheets)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    from .stages import rollback
    _sync_before_write()
    bx, sheets = _make_clients()
    summary = rollback.run(
        bx,
        sheets,
        company_id=args.company_id,
        domain=args.domain,
        confirm_rollback=args.confirm_rollback,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from collections import Counter
    from .config import TAB_GROUPS
    from .models import GROUP_HEADERS, Group
    _, sheets = _make_clients()
    rows = sheets.read(TAB_GROUPS)
    if not rows:
        print("deal_groups: пусто")
        return 0
    headers = rows[0]
    data = rows[1:]
    statuses = Counter()
    approved = 0
    losers = 0
    for r in data:
        g = Group.from_sheet_row(r, headers)
        statuses[g.status.value] += 1
        if g.approved:
            approved += 1
        losers += len(g.loser_ids)
    print(f"Групп: {len(data)}")
    print(f"LOSER сделок: {losers}")
    print(f"Approved: {approved}")
    print("Статусы:")
    for s, c in statuses.most_common():
        print(f"  {s}: {c}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(prog="deal-merge")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("discover", help="Найти cross-funnel дубли [38]↔[50] и записать в Sheets")
    sp.set_defaults(func=cmd_discover)

    sp = sub.add_parser("discover-v2", help="Найти дубли [38]+[50] по (company_id, domain)")
    sp.set_defaults(func=cmd_discover_v2)

    sp = sub.add_parser("inventory", help="Собрать связи LOSER-сделок")
    sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_inventory)

    sp = sub.add_parser("classify", help="Перевести INVENTORIED группы в PLAN_READY")
    sp.set_defaults(func=cmd_classify)

    sp = sub.add_parser("mark-approved", help="Перевести PLAN_READY группы в APPROVED")
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--status", default="PLAN_READY")
    sp.add_argument("--company-id")
    sp.add_argument("--domain")
    sp.set_defaults(func=cmd_mark_approved)

    sp = sub.add_parser("transfer", help="WRITE: перенести связи LOSER на WINNER")
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--limit", type=int)
    sp.add_argument("--group", help="COMPANY_ID:DOMAIN")
    sp.set_defaults(func=cmd_transfer)

    sp = sub.add_parser("close-loser", help="WRITE: закрыть LOSER после transfer")
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_close_loser)

    sp = sub.add_parser("verify", help="Read-only проверка MERGED групп")
    sp.set_defaults(func=cmd_verify)

    sp = sub.add_parser("rollback", help="WRITE: rollback группы из backup-листа")
    sp.add_argument("--company-id", required=True)
    sp.add_argument("--domain", required=True)
    sp.add_argument("--confirm-rollback", action="store_true")
    sp.set_defaults(func=cmd_rollback)

    sp = sub.add_parser("status", help="Сводка по группам")
    sp.set_defaults(func=cmd_status)

    args = p.parse_args()
    sys.exit(args.func(args))


def _sync_before_write() -> None:
    import subprocess

    if not SYNC_SCRIPT.exists():
        raise FileNotFoundError(f"Sync-скрипт не найден: {SYNC_SCRIPT}")
    subprocess.run(["bash", str(SYNC_SCRIPT)], check=True)


if __name__ == "__main__":
    main()
