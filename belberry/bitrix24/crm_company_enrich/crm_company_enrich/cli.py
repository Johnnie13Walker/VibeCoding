"""CLI для crm_company_enrich.

Exit codes:
  0  — success
  1  — recoverable failure (часть строк failed, см. summary)
  2  — write-stub (apply / merge-dupes / verify / rollback не реализованы)
"""
from __future__ import annotations

import argparse
import json
import sys


def _make_clients():
    """Lazy import чтобы --help работал без googleapiclient/requests в venv."""
    from .bitrix_client import BitrixClient
    from .config import LOG_PATH, SERVICE_ACCOUNT_JSON, SHEET_ID, STATE_PATH
    from .sheets_client import SheetsClient
    bx = BitrixClient(state_path=STATE_PATH, log_path=LOG_PATH)
    sheets = SheetsClient(sheet_id=SHEET_ID, service_account_path=SERVICE_ACCOUNT_JSON)
    return bx, sheets


def cmd_discover(args: argparse.Namespace) -> int:
    from .stages import discover
    bx, sheets = _make_clients()
    summary = discover.run(bx, sheets, limit_companies=args.limit_companies)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_enrich_web(args: argparse.Namespace) -> int:
    from .stages import enrich_web
    _, sheets = _make_clients()
    summary = enrich_web.run(
        sheets,
        limit=args.limit,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("failed", 0) and not summary.get("enriched", 0) else 0


def cmd_classify(args: argparse.Namespace) -> int:
    from .stages import classify
    bx, sheets = _make_clients()
    summary = classify.run(bx, sheets, limit=args.limit)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_mark_approved(args: argparse.Namespace) -> int:
    from .stages import mark_approved
    bx, sheets = _make_clients()
    summary = mark_approved.run(
        sheets,
        bx=bx,
        all_=args.all,
        status=args.status,
        company_id=args.company_id,
        action=args.action,
        target=args.target,
        limit=args.limit,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("errors") else 0


def cmd_status(args: argparse.Namespace) -> int:
    from collections import Counter
    from .sheet_store import read_queue
    _, sheets = _make_clients()
    queue = read_queue(sheets)
    statuses: Counter[str] = Counter()
    actions: Counter[str] = Counter()
    approved = 0
    active_merge = 0
    for _, row in queue:
        statuses[row.status.value] += 1
        if row.target_action:
            actions[row.target_action.value] += 1
        if row.approved:
            approved += 1
        if row.in_active_deal_merge:
            active_merge += 1
    print(f"Очередь company_enrich_queue: {len(queue)} строк")
    print(f"in_active_deal_merge: {active_merge}")
    print(f"approved: {approved}")
    print("Статусы:")
    for status, count in statuses.most_common():
        print(f"  {status}: {count}")
    if args.detailed and actions:
        print("target_action:")
        for action, count in actions.most_common():
            print(f"  {action}: {count}")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    from .stages import apply
    bx, sheets = _make_clients()
    summary = apply.run(bx, sheets, dry_run=args.dry_run, limit=args.limit)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("failed", 0) else 0


def cmd_merge_dupes(args: argparse.Namespace) -> int:
    from .stages import merge_dupes
    try:
        merge_dupes.run(dry_run=args.dry_run, limit=args.limit)
        return 0
    except NotImplementedError as exc:
        print(f"WARN: {exc}", file=sys.stderr)
        return 2


def cmd_verify(args: argparse.Namespace) -> int:
    from .stages import verify
    try:
        verify.run()
        return 0
    except NotImplementedError as exc:
        print(f"WARN: {exc}", file=sys.stderr)
        return 2


def cmd_rollback(args: argparse.Namespace) -> int:
    from .stages import rollback
    try:
        rollback.run(company_id=args.company_id, confirm_rollback=args.confirm_rollback)
        return 0
    except NotImplementedError as exc:
        print(f"WARN: {exc}", file=sys.stderr)
        return 2


def main() -> None:
    p = argparse.ArgumentParser(
        prog="company-enrich",
        description=(
            "Обогащение компаний Bitrix24 ИНН и реквизитами. "
            "READ-only стадии: discover / enrich-web / classify / status. "
            "WRITE-стадии (apply / merge-dupes / verify / rollback) — "
            "stub, exit code 2."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("discover", help="READ: собрать список компаний без валидного ИНН в очередь")
    sp.add_argument("--limit-companies", type=int, help="Ограничить число компаний для теста на dev-портале")
    sp.set_defaults(func=cmd_discover)

    sp = sub.add_parser("enrich-web", help="WEB: обогатить status=NEW строки ИНН через web/uf/title/rusprofile")
    sp.add_argument("--limit", type=int, help="Ограничить число обогащаемых строк")
    sp.add_argument("--sample", action="store_true", help="alias --limit 10")
    sp.set_defaults(func=cmd_enrich_web)

    sp = sub.add_parser("classify", help="READ: для ENRICHED строк определить target_action (CREATE_REQ/MERGE_INTO/SKIP)")
    sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_classify)

    sp = sub.add_parser("mark-approved", help="SHEETS: подтвердить CLASSIFIED строки → APPROVED")
    group = sp.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Массовый approve по --status")
    group.add_argument("--company-id", help="Approve одну строку по company_id")
    sp.add_argument("--status", default="CLASSIFIED", help="Исходный статус (по умолчанию CLASSIFIED)")
    sp.add_argument("--action", help="Принудительно установить target_action (CREATE_REQ/MERGE_INTO/SKIP_ALREADY)")
    sp.add_argument("--target", help="Для --action MERGE_INTO — id компании-приёмника")
    sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_mark_approved)

    sp = sub.add_parser("status", help="Сводка по очереди")
    sp.add_argument("--detailed", action="store_true")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser(
        "apply",
        help=(
            "WRITE: создать реквизиты для APPROVED+CREATE_REQ строк "
            "(--dry-run печатает план без write)"
        ),
    )
    sp.add_argument(
        "--dry-run",
        action="store_true",
        help="Не вызывать Bitrix.add, только напечатать план и payload",
    )
    sp.add_argument(
        "--limit",
        type=int,
        help="Ограничить число обрабатываемых APPROVED строк",
    )
    sp.set_defaults(func=cmd_apply)

    sp = sub.add_parser("merge-dupes", help="STUB: смержить компании с MERGE_INTO target_action (exit 2)")
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_merge_dupes)

    sp = sub.add_parser("verify", help="STUB: read-only проверка APPLIED/MERGED (exit 2)")
    sp.set_defaults(func=cmd_verify)

    sp = sub.add_parser("rollback", help="STUB: откатить write-операцию по company_id (exit 2)")
    sp.add_argument("--company-id", required=True)
    sp.add_argument("--confirm-rollback", action="store_true", required=True)
    sp.set_defaults(func=cmd_rollback)

    args = p.parse_args()
    # --sample alias
    if getattr(args, "sample", False) and not getattr(args, "limit", None):
        args.limit = 10
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
