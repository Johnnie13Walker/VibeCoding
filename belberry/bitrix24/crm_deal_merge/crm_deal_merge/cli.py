"""CLI для crm_deal_merge."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .bitrix_client import BitrixClient
from .config import LOG_PATH, SERVICE_ACCOUNT_JSON, SHEET_ID, STATE_PATH, SYNC_SCRIPT
from .sheets_client import SheetsClient


def _make_clients(sheet_id: str = SHEET_ID) -> tuple[BitrixClient, SheetsClient]:
    bx = BitrixClient(state_path=STATE_PATH, log_path=LOG_PATH)
    sheets = SheetsClient(sheet_id=sheet_id, service_account_path=SERVICE_ACCOUNT_JSON)
    return bx, sheets


def cmd_discover(args: argparse.Namespace) -> int:
    from .stages import discover
    bx, sheets = _make_clients()
    summary = discover.run(bx, sheets)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("failed", 0) > 0 else 0


def cmd_discover_v2(args: argparse.Namespace) -> int:
    from .stages import discover_v2
    bx, sheets = _make_clients()
    summary = discover_v2.run(bx, sheets)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_inventory(args: argparse.Namespace) -> int:
    from .stages import inventory
    bx, sheets = _make_clients()
    summary = inventory.run(bx, sheets, limit=args.limit, include_sp=args.include_sp)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_inventory_spotcheck(args: argparse.Namespace) -> int:
    from .stages import inventory_spotcheck
    bx, sheets = _make_clients()
    summary = inventory_spotcheck.run(bx, sheets, sample=args.sample, seed=args.seed)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_enrich_sp(args: argparse.Namespace) -> int:
    from .stages import inventory_sp
    bx, sheets = _make_clients()
    summary = inventory_sp.run(bx, sheets, limit=args.limit, statuses=inventory_sp.parse_statuses(args.status))
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
    bx, sheets = _make_clients()
    summary = mark_approved.run(
        sheets,
        bx=bx if args.smart else None,
        all_=args.all,
        smart=args.smart,
        limit=args.limit,
        status=args.status,
        company_id=args.company_id,
        domain=args.domain,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("failed", 0) > 0 else 0


def cmd_transfer(args: argparse.Namespace) -> int:
    from .stages import transfer
    _sync_before_write()
    bx, sheets = _make_clients()
    summary = transfer.run(
        bx, sheets,
        dry_run=args.dry_run,
        limit=args.limit,
        group_key=args.group,
        batch_mode=args.batch_mode,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("failed", 0) > 0 else 0


def cmd_close_loser(args: argparse.Namespace) -> int:
    from .stages import close_loser
    _sync_before_write()
    bx, sheets = _make_clients()
    summary = close_loser.run(bx, sheets, dry_run=args.dry_run, limit=args.limit)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("failed", 0) > 0 else 0


def cmd_verify(args: argparse.Namespace) -> int:
    from .stages import verify
    bx, sheets = _make_clients()
    summary = verify.run(bx, sheets)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("failed", 0) > 0 else 0


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
    from .models import Group
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
    if args.detailed:
        _print_detailed_status([Group.from_sheet_row(r, headers) for r in data if r])
    return 0


def cmd_reclassify_failed(args: argparse.Namespace) -> int:
    from .stages import reclassify_failed
    _, sheets = _make_clients()
    summary = reclassify_failed.run(sheets, reset=args.reset, pattern=args.pattern)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_archive_old_backups(args: argparse.Namespace) -> int:
    from .stages import archive_old_backups
    _, sheets = _make_clients()
    summary = archive_old_backups.run(sheets, before=args.before)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_unapprove(args: argparse.Namespace) -> int:
    from .stages import unapprove
    _, sheets = _make_clients()
    summary = unapprove.run(sheets, company_id=args.company_id, domain=args.domain)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_unfail(args: argparse.Namespace) -> int:
    from .stages import unfail
    _, sheets = _make_clients()
    summary = unfail.run(sheets, company_id=args.company_id, domain=args.domain)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_mark_manual(args: argparse.Namespace) -> int:
    from .stages import mark_manual
    _, sheets = _make_clients()
    summary = mark_manual.run(sheets, company_id=args.company_id, domain=args.domain, reason=args.reason)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_skip_inventory(args: argparse.Namespace) -> int:
    from .stages import skip_inventory
    _, sheets = _make_clients()
    summary = skip_inventory.run(
        sheets,
        entity_type_prefix=args.entity_type_prefix,
        where=skip_inventory.parse_where(args.where),
        all_companies=args.all_companies,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_audit_pilot_sp(args: argparse.Namespace) -> int:
    from .stages import audit_pilot_sp
    bx, sheets = _make_clients()
    summary = audit_pilot_sp.run(bx, sheets, groups_arg=args.groups)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_empty_companies_refresh(args: argparse.Namespace) -> int:
    from .stages import empty_companies
    bx, sheets = _make_clients(sheet_id=empty_companies.TARGET_SHEET_ID)
    summary = empty_companies.run(bx, sheets, write_sheet=args.live)
    payload = json.dumps(summary, indent=2, ensure_ascii=False)
    print(payload)
    if args.summary_json:
        Path(args.summary_json).write_text(payload + "\n", encoding="utf-8")
    if summary["trash_companies"] > args.max_rows:
        print(
            f"STOP: найдено {summary['trash_companies']} пустых компаний, "
            f"лимит безопасности {args.max_rows}",
            file=sys.stderr,
        )
        return 2
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
    sp.add_argument("--include-sp", action="store_true", help="Дополнительно искать smart-process parentId2; медленно на портале")
    sp.set_defaults(func=cmd_inventory)

    sp = sub.add_parser("inventory-spotcheck", help="Read-only sample-проверка smart-process связей LOSER")
    sp.add_argument("--sample", type=int, default=30)
    sp.add_argument("--seed", type=int)
    sp.set_defaults(func=cmd_inventory_spotcheck)

    sp = sub.add_parser("enrich-sp", help="Добрать только smart-process строки в merge_inventory")
    sp.add_argument("--limit", type=int)
    sp.add_argument("--status", help="Статус или список статусов через запятую; по умолчанию PLAN_READY,INVENTORIED")
    sp.set_defaults(func=cmd_enrich_sp)

    sp = sub.add_parser("classify", help="Перевести INVENTORIED группы в PLAN_READY")
    sp.set_defaults(func=cmd_classify)

    sp = sub.add_parser("mark-approved", help="Перевести PLAN_READY группы в APPROVED")
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--smart", action="store_true")
    sp.add_argument("--limit", type=int)
    sp.add_argument("--status", default="PLAN_READY")
    sp.add_argument("--company-id")
    sp.add_argument("--domain")
    sp.set_defaults(func=cmd_mark_approved)

    sp = sub.add_parser("unapprove", help="Снять approval с группы")
    sp.add_argument("--company-id", required=True)
    sp.add_argument("--domain", required=True)
    sp.set_defaults(func=cmd_unapprove)

    sp = sub.add_parser("unfail", help="Вернуть FAILED группу в APPROVED")
    sp.add_argument("--company-id", required=True)
    sp.add_argument("--domain", required=True)
    sp.set_defaults(func=cmd_unfail)

    sp = sub.add_parser("mark-manual", help="Перевести группу в MANUAL")
    sp.add_argument("--company-id", required=True)
    sp.add_argument("--domain", required=True)
    sp.add_argument("--reason", required=True)
    sp.set_defaults(func=cmd_mark_manual)

    sp = sub.add_parser("skip-inventory", help="Пометить inventory-строки как пропущенные")
    sp.add_argument("--entity-type-prefix", required=True)
    sp.add_argument("--where", action="append", help="Фильтр key=value, например company-id=36")
    sp.add_argument("--all-companies", action="store_true")
    sp.set_defaults(func=cmd_skip_inventory)

    sp = sub.add_parser("audit-pilot-sp", help="Read-only аудит бизнес-SP у пилотных групп")
    sp.add_argument("--groups", required=True, help="Список COMPANY_ID:DOMAIN через запятую")
    sp.set_defaults(func=cmd_audit_pilot_sp)

    sp = sub.add_parser("empty-companies-refresh", help="Обновить таб «Пустые компании»")
    mode = sp.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_false", dest="live", help="Read-only расчёт без записи в Sheets")
    mode.add_argument("--live", action="store_true", dest="live", help="WRITE: перезаписать только таб «Пустые компании»")
    sp.set_defaults(live=False)
    sp.add_argument("--max-rows", type=int, default=12000, help="Safety-stop при подозрительно большом снапшоте")
    sp.add_argument("--summary-json", help="Куда записать JSON summary для cron/notify")
    sp.set_defaults(func=cmd_empty_companies_refresh)

    sp = sub.add_parser("transfer", help="WRITE: перенести связи LOSER на WINNER")
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--limit", type=int)
    sp.add_argument("--group", help="COMPANY_ID:DOMAIN")
    sp.add_argument(
        "--batch-mode",
        action="store_true",
        help="Bitrix batch API (~×10 speedup для прода с большим объёмом). "
             "TASKS и SP остаются sequential, остальное батчуется.",
    )
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
    sp.add_argument("--detailed", action="store_true")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("reclassify-failed", help="Сводка FAILED и опциональный reset")
    sp.add_argument("--reset", action="store_true")
    sp.add_argument("--pattern")
    sp.set_defaults(func=cmd_reclassify_failed)

    sp = sub.add_parser("archive-old-backups", help="Архивировать старые backup-листы в локальные JSON")
    sp.add_argument("--before", required=True, help="Архивировать backup-листы старше YYYY-MM-DD")
    sp.set_defaults(func=cmd_archive_old_backups)

    args = p.parse_args()
    sys.exit(args.func(args))


def _sync_before_write() -> None:
    import subprocess

    if not SYNC_SCRIPT.exists():
        raise FileNotFoundError(f"Sync-скрипт не найден: {SYNC_SCRIPT}")
    subprocess.run(["bash", str(SYNC_SCRIPT)], check=True)


def _print_detailed_status(groups) -> None:
    from collections import Counter, defaultdict

    losers_by_status: Counter[str] = Counter()
    failed_errors: list[str] = []
    for group in groups:
        losers_by_status[group.status.value] += len(group.loser_ids)
        if group.status.value == "FAILED" and group.error_message:
            failed_errors.append(group.error_message)

    print("LOSER по статусам:")
    for status, count in losers_by_status.most_common():
        print(f"  {status}: {count}")

    print("Топ-10 групп по n_loser:")
    for group in sorted(groups, key=lambda g: len(g.loser_ids), reverse=True)[:10]:
        print(f"  {group.company_id}:{group.domain or '-'} losers={len(group.loser_ids)} status={group.status.value}")

    print("Топ-10 групп по transferable:")
    for group in sorted(
        groups,
        key=lambda g: g.n_activities_planned + g.n_timeline_planned + g.n_contacts_planned,
        reverse=True,
    )[:10]:
        total = group.n_activities_planned + group.n_timeline_planned + group.n_contacts_planned
        print(f"  {group.company_id}:{group.domain or '-'} total={total} act={group.n_activities_planned} tl={group.n_timeline_planned} cont={group.n_contacts_planned}")

    failed_count = sum(1 for group in groups if group.status.value == "FAILED")
    print(f"FAILED групп: {failed_count}")
    if failed_errors:
        print("Первые 5 error_message:")
        for message in failed_errors[:5]:
            print(f"  {message[:300]}")


if __name__ == "__main__":
    main()
