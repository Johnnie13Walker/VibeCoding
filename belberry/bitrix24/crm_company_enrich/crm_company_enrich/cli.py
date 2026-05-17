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


def cmd_promote(args: argparse.Namespace) -> int:
    """Промоушн MANUAL_REVIEW → ENRICHED после ручной проверки.

    Только Sheets-write; никаких Bitrix-вызовов. На следующем запуске classify
    подберёт строку и проставит target_action.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from .sheet_store import read_queue, replace_row, update_row
    from .state import Status

    _, sheets = _make_clients()
    queue = read_queue(sheets)
    now = datetime.now(ZoneInfo("Europe/Moscow"))
    promoted = 0
    not_found = True
    for row_number, row in queue:
        if str(row.company_id) != str(args.company_id):
            continue
        not_found = False
        if row.status != Status.MANUAL_REVIEW:
            print(
                f"[promote] company {row.company_id}: status={row.status.value} "
                f"(ожидался MANUAL_REVIEW) — пропускаю"
            )
            break
        updated = replace_row(
            row,
            status=Status.ENRICHED,
            last_action_at=now,
            error_message=f"promoted from MANUAL_REVIEW at {now.isoformat(timespec='seconds')}",
        )
        update_row(sheets, row_number, updated)
        promoted += 1
        print(f"[promote] company {row.company_id}: MANUAL_REVIEW → ENRICHED")
        break
    if not_found:
        print(f"[promote] company {args.company_id}: строка не найдена в очереди", file=sys.stderr)
        return 1
    summary = {"promoted": promoted, "company_id": args.company_id}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if promoted else 1


def cmd_apply(args: argparse.Namespace) -> int:
    from .stages import apply
    bx, sheets = _make_clients()
    summary = apply.run(bx, sheets, dry_run=args.dry_run, limit=args.limit, action=args.action)
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
    bx, sheets = _make_clients()
    summary = verify.run(bx, sheets, limit=args.limit)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_sync_deals(args: argparse.Namespace) -> int:
    from .stages import sync_deals
    bx, _ = _make_clients()
    summary = sync_deals.run(
        bx,
        company_id=args.company_id,
        deal_id=args.deal_id,
        dry_run=not args.live,
        overwrite=args.overwrite,
        active_only=not args.include_closed,
        limit=args.limit,
        telemarketing_workflow=args.telemarketing_workflow,
        rotation_index=args.rotation_index,
        dedupe_telemarketing=args.dedupe_telemarketing,
        auto_reject_telemarketing=args.auto_reject_telemarketing,
        dedupe_contacts=args.dedupe_contacts,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("failed") else 0


def cmd_sync_company(args: argparse.Namespace) -> int:
    from .stages import sync_deals
    bx, _ = _make_clients()
    summary = sync_deals.run_company(
        bx,
        company_id=args.company_id,
        inn=args.inn or "",
        site=args.site or "",
        dry_run=not args.live,
        overwrite=args.overwrite,
        dedupe_telemarketing=args.dedupe_telemarketing,
        auto_reject_telemarketing=args.auto_reject_telemarketing,
        dedupe_contacts=args.dedupe_contacts,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("failed") else 0


def cmd_dedupe_contacts(args: argparse.Namespace) -> int:
    from .stages import dedupe_contacts
    bx, _ = _make_clients()
    summary = dedupe_contacts.run_company(
        bx,
        company_id=args.company_id,
        dry_run=not args.live,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("failed") else 0


def cmd_telemarketing_digest(args: argparse.Namespace) -> int:
    from .stages import telemarketing_digest
    bx, _ = _make_clients()
    summary = telemarketing_digest.run(
        bx,
        dry_run=not args.live,
        since=args.since,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    telegram_result = summary.get("telegram") or {}
    if telegram_result.get("skipped"):
        print(
            f"WARN: telegram message skipped: {telegram_result.get('reason')}. "
            "Set LARISA_BOT_TOKEN and LARISA_CHAT_ID_LARISA env to enable.",
            file=sys.stderr,
        )
    return 1 if telegram_result.get("ok") is False else 0


def cmd_auto_promote_base(args: argparse.Namespace) -> int:
    from .stages import auto_promote_base
    bx, _ = _make_clients()
    summary = auto_promote_base.run(
        bx,
        dry_run=not args.live,
        limit=args.limit,
        rotation_index=args.rotation_index,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("failed") else 0


def cmd_telemarketing_stuck_alerts(args: argparse.Namespace) -> int:
    from datetime import datetime

    from .stages import telemarketing_stuck_alerts

    bx, _ = _make_clients()
    today = datetime.fromisoformat(args.today).date() if args.today else None
    summary = telemarketing_stuck_alerts.run(bx, today=today)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_reactivation_apology(args: argparse.Namespace) -> int:
    from datetime import datetime

    from .stages import reactivation_apology

    bx, _ = _make_clients()
    today = datetime.fromisoformat(args.today).date() if args.today else None
    summary = reactivation_apology.run(
        bx,
        dry_run=not args.live,
        limit=args.limit,
        today=today,
        rotation_index=args.rotation_index,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("failed") else 0


def cmd_auto_reject_telemarketing(args: argparse.Namespace) -> int:
    from .stages import auto_reject_telemarketing
    bx, _ = _make_clients()
    if args.deal_id:
        summary = auto_reject_telemarketing.run_deal(
            bx,
            deal_id=args.deal_id,
            dry_run=not args.live,
        )
    elif args.company_id:
        summary = auto_reject_telemarketing.run_company(
            bx,
            company_id=args.company_id,
            dry_run=not args.live,
        )
    else:
        summary = auto_reject_telemarketing.run(
            bx,
            dry_run=not args.live,
            limit=args.limit,
            stages=args.stage,
        )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not summary.get("failed") else 1


def cmd_enrich_from_sheet(args: argparse.Namespace) -> int:
    from .bitrix_client import BitrixClient
    from .config import (
        LOG_PATH,
        SERVICE_ACCOUNT_JSON,
        STATE_PATH,
        TM_NO_REQUISITES_SHEET_ID,
        TM_NO_REQUISITES_TAB_GID,
    )
    from .sheets_client import SheetsClient
    from .stages import enrich_from_sheet

    bx = BitrixClient(state_path=STATE_PATH, log_path=LOG_PATH)
    sheets = SheetsClient(
        sheet_id=args.sheet_id or TM_NO_REQUISITES_SHEET_ID,
        service_account_path=SERVICE_ACCOUNT_JSON,
    )
    summary = enrich_from_sheet.run(
        bx,
        sheets,
        sheet_id=args.sheet_id,
        tab_gid=args.tab_gid or TM_NO_REQUISITES_TAB_GID,
        dry_run=not args.live,
        limit=args.limit,
        skip_already_enriched=not args.no_skip_already_enriched,
        enable_auto_reject=not args.no_auto_reject,
        enable_dedupe_contacts=not args.no_dedupe_contacts,
        enable_enrich_director_inn=not args.no_enrich_director_inn,
        trigger_bp=not args.no_trigger_bp,
        resume=args.resume,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("failed") else 0


def cmd_auto_revive_lose(args: argparse.Namespace) -> int:
    from .stages import auto_revive_lose
    bx, _ = _make_clients()
    summary = auto_revive_lose.run(
        bx,
        dry_run=not args.live,
        due_before=args.due_before,
        limit=args.limit,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not summary.get("failed") else 1


def cmd_telemarketing_dedupe(args: argparse.Namespace) -> int:
    from .stages import telemarketing_dedupe
    bx, _ = _make_clients()
    summary = telemarketing_dedupe.run(
        bx,
        dry_run=not args.live,
        limit=args.limit,
        rotation_index=args.rotation_index,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not summary.get("unresolved") else 1


def cmd_company_region_field(args: argparse.Namespace) -> int:
    from .stages import company_region_field
    bx, _ = _make_clients()
    summary = company_region_field.run(
        bx,
        apply=args.apply,
        verify=not args.skip_verify,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    verification = summary.get("verification")
    if verification and not verification.get("ok"):
        return 1
    return 0


def cmd_deal_revive_count_field(args: argparse.Namespace) -> int:
    from .stages import deal_revive_count_field
    bx, _ = _make_clients()
    summary = deal_revive_count_field.run(
        bx,
        apply=args.apply,
        verify=not args.skip_verify,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    verification = summary.get("verification")
    if verification and not verification.get("ok"):
        return 1
    return 0


def cmd_deal_reactivation_count_field(args: argparse.Namespace) -> int:
    from .stages import deal_reactivation_count_field
    bx, _ = _make_clients()
    summary = deal_reactivation_count_field.run(
        bx,
        apply=args.apply,
        verify=not args.skip_verify,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    verification = summary.get("verification")
    if verification and not verification.get("ok"):
        return 1
    return 0


def cmd_migrate_region_enum_ids(args: argparse.Namespace) -> int:
    from .stages import migrate_region_enum_ids
    bx, _ = _make_clients()
    summary = migrate_region_enum_ids.run(
        bx,
        dry_run=not args.live,
        limit=args.limit,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not summary.get("failed") else 1


def cmd_migrate_revive_count_to_uf(args: argparse.Namespace) -> int:
    from .stages import migrate_revive_count_to_uf
    bx, _ = _make_clients()
    summary = migrate_revive_count_to_uf.run(
        bx,
        dry_run=not args.live,
        limit=args.limit,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not summary.get("failed") else 1


def cmd_empty_discover(args: argparse.Namespace) -> int:
    from .stages import enrich_empty_companies
    summary = enrich_empty_companies.run_discover(limit=args.limit)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_empty_enrich(args: argparse.Namespace) -> int:
    from .stages import enrich_empty_companies
    summary = enrich_empty_companies.run_enrich(limit=args.limit, throttle_s=args.throttle)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_empty_upload_plan(args: argparse.Namespace) -> int:
    from .stages import enrich_empty_companies
    summary = enrich_empty_companies.run_upload_plan()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_empty_report(args: argparse.Namespace) -> int:
    from .stages import enrich_empty_companies
    summary = enrich_empty_companies.run_report(top=args.top)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_empty_manual_site(args: argparse.Namespace) -> int:
    from .stages import enrich_empty_companies
    summary = enrich_empty_companies.run_manual_site_sheet(limit=args.limit)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_empty_manual_site_promote(args: argparse.Namespace) -> int:
    from .stages import enrich_empty_companies
    if args.live and not args.confirm_promote:
        print("Для реального promote нужны --live и --confirm-promote. Без --live выполняется dry-run.", file=sys.stderr)
        return 2
    summary = enrich_empty_companies.run_manual_site_promote(
        dry_run=not args.live,
        limit=args.limit,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("invalid") else 0


def cmd_empty_reconcile(args: argparse.Namespace) -> int:
    from .stages import enrich_empty_companies
    summary = enrich_empty_companies.run_reconcile_existing(limit=args.limit, throttle_s=args.throttle)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("errors") else 0


def cmd_empty_apply(args: argparse.Namespace) -> int:
    from .stages import enrich_empty_companies
    dry_run = not args.live
    if args.live and not args.confirm_apply:
        print("Для реального apply нужны --live и --confirm-apply. Без --live выполняется dry-run.", file=sys.stderr)
        return 2
    summary = enrich_empty_companies.run_apply(
        dry_run=dry_run,
        limit=args.limit,
        throttle_s=args.throttle,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("failed") else 0


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
    sp.add_argument(
        "--action",
        choices=["CREATE_REQ", "MERGE_INTO", "SKIP_ALREADY"],
        help="Обрабатывать только APPROVED строки с указанным target_action",
    )
    sp.set_defaults(func=cmd_apply)

    sp = sub.add_parser(
        "promote",
        help="SHEETS: перевести строку MANUAL_REVIEW → ENRICHED после ручной проверки",
    )
    sp.add_argument("--company-id", required=True, help="Bitrix company_id строки в очереди")
    sp.set_defaults(func=cmd_promote)

    sp = sub.add_parser("merge-dupes", help="STUB: смержить компании с MERGE_INTO target_action (exit 2)")
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_merge_dupes)

    sp = sub.add_parser(
        "verify",
        help=(
            "READ: проверить APPLIED_PENDING_BP строки — если bizproc подтянул "
            "OGRN/КПП после wait-окна, перевести в APPLIED"
        ),
    )
    sp.add_argument("--limit", type=int, help="Ограничить число проверяемых строк")
    sp.set_defaults(func=cmd_verify)

    sp = sub.add_parser(
        "sync-deals",
        help=(
            "WRITE: дозаполнить поля сделок из обогащённой компании "
            "(по умолчанию dry-run; запись только с --live)"
        ),
    )
    group = sp.add_mutually_exclusive_group(required=True)
    group.add_argument("--company-id", help="Синхронизировать активные сделки этой компании")
    group.add_argument("--deal-id", help="Синхронизировать одну сделку")
    sp.add_argument("--live", action="store_true", help="Реально записать поля сделки")
    sp.add_argument("--overwrite", action="store_true", help="Перезаписывать уже заполненные поля")
    sp.add_argument("--include-closed", action="store_true", help="Не пропускать закрытые сделки")
    sp.add_argument(
        "--telemarketing-workflow",
        action="store_true",
        help="Вернуть отказную сделку в C50:NEW и выбрать ответственного по правилам телемаркетинга",
    )
    sp.add_argument(
        "--rotation-index",
        type=int,
        default=0,
        help="Индекс ротации для новых/чужих отказных сделок: 0=Дарья, 1=Аркадий",
    )
    sp.add_argument("--limit", type=int)
    sp.add_argument(
        "--dedupe-telemarketing",
        action="store_true",
        help="После sync-deals запустить scoped dedupe для этой компании",
    )
    sp.add_argument(
        "--auto-reject-telemarketing",
        action="store_true",
        help="После sync-deals запустить scoped auto-reject для этой компании/сделки",
    )
    sp.add_argument(
        "--dedupe-contacts",
        action="store_true",
        help="После sync-deals запустить scoped dedupe контактов компании",
    )
    sp.set_defaults(func=cmd_sync_deals)

    sp = sub.add_parser(
        "sync-company",
        help=(
            "WRITE: дозаполнить поля компании без сделок "
            "(Rusprofile/Checko, статус, сфера, бренд, ИНН; по умолчанию dry-run)"
        ),
    )
    sp.add_argument("--company-id", required=True, help="Bitrix company_id")
    sp.add_argument("--inn", help="ИНН, если в карточке компании он ещё пустой")
    sp.add_argument("--site", help="Рабочий сайт, если текущий сайт компании пустой или не отвечает")
    sp.add_argument("--live", action="store_true", help="Реально записать поля компании")
    sp.add_argument("--overwrite", action="store_true", help="Перезаписывать уже заполненные поля")
    sp.add_argument(
        "--dedupe-telemarketing",
        action="store_true",
        help="После sync-company запустить scoped dedupe для этой компании",
    )
    sp.add_argument(
        "--auto-reject-telemarketing",
        action="store_true",
        help="После sync-company запустить scoped auto-reject для этой компании",
    )
    sp.add_argument(
        "--dedupe-contacts",
        action="store_true",
        help="После sync-company запустить scoped dedupe контактов компании",
    )
    sp.set_defaults(func=cmd_sync_company)

    sp = sub.add_parser(
        "dedupe-contacts",
        help=(
            "WRITE: scoped dedupe контактов компании + re-attach в сделки. "
            "По умолчанию dry-run."
        ),
    )
    sp.add_argument("--company-id", required=True)
    sp.add_argument("--live", action="store_true")
    sp.set_defaults(func=cmd_dedupe_contacts)

    sp = sub.add_parser(
        "telemarketing-digest",
        help=(
            "TG: собрать дневной дайджест Ларисы. По умолчанию dry-run; "
            "отправка только с --live."
        ),
    )
    sp.add_argument("--live", action="store_true")
    sp.add_argument("--since", help="ISO date YYYY-MM-DD, по умолчанию вчера по МСК")
    sp.set_defaults(func=cmd_telemarketing_digest)

    sp = sub.add_parser(
        "auto-promote-base",
        help=(
            "WRITE: перевести готовые сделки из C50:UC_1S1KIU в C50:NEW. "
            "По умолчанию dry-run."
        ),
    )
    sp.add_argument("--live", action="store_true")
    sp.add_argument("--limit", type=int)
    sp.add_argument("--rotation-index", type=int, default=0)
    sp.set_defaults(func=cmd_auto_promote_base)

    sp = sub.add_parser(
        "telemarketing-stuck-alerts",
        help="READ: найти застрявшие C50:PREPARATION и C50:UC_WZ4KQE сделки",
    )
    sp.add_argument("--today", help="ISO date YYYY-MM-DD для тестового расчёта")
    sp.set_defaults(func=cmd_telemarketing_stuck_alerts)

    sp = sub.add_parser(
        "reactivation-apology",
        help="WRITE: re-open C50:APOLOGY по cooldown matrix. По умолчанию dry-run.",
    )
    sp.add_argument("--live", action="store_true")
    sp.add_argument("--limit", type=int)
    sp.add_argument("--today", help="ISO date YYYY-MM-DD для тестового расчёта")
    sp.add_argument("--rotation-index", type=int, default=0)
    sp.set_defaults(func=cmd_reactivation_apology)

    sp = sub.add_parser(
        "auto-reject-telemarketing",
        help=(
            "WRITE: автоматически закрыть сделки в C50:UC_1S1KIU/NEW по причинам "
            "Ликвидирована (8538) или Выручка <30M (8542). По умолчанию dry-run."
        ),
    )
    sp.add_argument("--live", action="store_true")
    sp.add_argument("--limit", type=int, help="Ограничить число обработанных сделок")
    ar_group = sp.add_mutually_exclusive_group()
    ar_group.add_argument("--deal-id", help="Точечный auto-reject одной сделки")
    ar_group.add_argument("--company-id", help="Auto-reject сканируемых сделок одной компании")
    sp.add_argument(
        "--stage",
        action="append",
        help="Конкретные стадии для скана (по умолчанию UC_1S1KIU,NEW)",
    )
    sp.set_defaults(func=cmd_auto_reject_telemarketing)

    sp = sub.add_parser(
        "enrich-from-sheet",
        help=(
            "WRITE: обогатить сделки из Google Sheets и обновить лист. "
            "По умолчанию dry-run."
        ),
    )
    sp.add_argument("--sheet-id", default=None, help="Override sheet_id, по умолчанию TM_NO_REQUISITES_SHEET_ID")
    sp.add_argument("--tab-gid", type=int, default=None, help="Override tab gid, по умолчанию TM_NO_REQUISITES_TAB_GID")
    sp.add_argument("--live", action="store_true", help="Реально обогащать и писать в лист")
    sp.add_argument("--limit", type=int, help="Ограничить число сделок")
    sp.add_argument("--no-skip-already-enriched", action="store_true", help="Не пропускать недавно обогащённые")
    sp.add_argument("--no-auto-reject", action="store_true")
    sp.add_argument("--no-dedupe-contacts", action="store_true")
    sp.add_argument("--no-enrich-director-inn", action="store_true")
    sp.add_argument("--no-trigger-bp", action="store_true")
    sp.add_argument("--resume", action="store_true", help="Продолжить с checkpoint enrich_from_sheet_progress.json")
    sp.set_defaults(func=cmd_enrich_from_sheet)

    sp = sub.add_parser(
        "auto-revive-lose",
        help=(
            "WRITE: вернуть LOSE-сделки в NEW по дате UF_CRM_1770901971. "
            "По умолчанию dry-run."
        ),
    )
    sp.add_argument("--live", action="store_true")
    sp.add_argument("--due-before", help="ISO date, по умолчанию сегодня (МСК)")
    sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_auto_revive_lose)

    sp = sub.add_parser(
        "telemarketing-dedupe",
        help=(
            "WRITE: объединить дубли сделок в воронке телемаркетинга. "
            "По умолчанию dry-run; --live для записи в Bitrix."
        ),
    )
    sp.add_argument("--live", action="store_true")
    sp.add_argument(
        "--limit",
        type=int,
        help="Ограничить число компаний (не сделок) для обработки",
    )
    sp.add_argument(
        "--rotation-index",
        type=int,
        default=0,
        help="Стартовый индекс ротации для переназначения winner с уволенного",
    )
    sp.set_defaults(func=cmd_telemarketing_dedupe)

    sp = sub.add_parser(
        "company-region-field",
        help=(
            "WRITE: создать/синхронизировать enum-поле компании «Область». "
            "По умолчанию dry-run; запись только с --apply."
        ),
    )
    sp.add_argument("--apply", action="store_true", help="Реально создать или обновить поле в Bitrix24")
    sp.add_argument("--skip-verify", action="store_true", help="Не читать поле повторно после --apply")
    sp.set_defaults(func=cmd_company_region_field)

    sp = sub.add_parser(
        "deal-revive-count-field",
        help=(
            "WRITE: idempotent create/sync UF_CRM_REVIVE_COUNT. "
            "По умолчанию dry-run; запись только с --apply."
        ),
    )
    sp.add_argument("--apply", action="store_true", help="Реально создать или обновить поле в Bitrix24")
    sp.add_argument("--skip-verify", action="store_true", help="Не читать поле повторно после --apply")
    sp.set_defaults(func=cmd_deal_revive_count_field)

    sp = sub.add_parser(
        "deal-reactivation-count-field",
        help=(
            "WRITE: idempotent create/sync UF_CRM_REACTIVATION_COUNT. "
            "По умолчанию dry-run; запись только с --apply."
        ),
    )
    sp.add_argument("--apply", action="store_true", help="Реально создать или обновить поле в Bitrix24")
    sp.add_argument("--skip-verify", action="store_true", help="Не читать поле повторно после --apply")
    sp.set_defaults(func=cmd_deal_reactivation_count_field)

    sp = sub.add_parser(
        "migrate-region-enum-ids",
        help=(
            "WRITE: одноразовая миграция UF_CRM_REGION_RF — перенести orphan-ID "
            "8962-9064 на актуальный enum после обновления поля. По умолчанию dry-run."
        ),
    )
    sp.add_argument("--live", action="store_true", help="Реально записать в Bitrix")
    sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_migrate_region_enum_ids)

    sp = sub.add_parser(
        "migrate-revive-count-to-uf",
        help=(
            "WRITE: перенести исторический auto-revive #N из строкового "
            "поля в UF_CRM_REVIVE_COUNT. По умолчанию dry-run."
        ),
    )
    sp.add_argument("--live", action="store_true", help="Реально записать в Bitrix")
    sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_migrate_revive_count_to_uf)

    sp = sub.add_parser(
        "empty-discover",
        help="READ/SHEETS: собрать pool пустых компаний, исключив 'Не трогать' и уже имеющие ИНН",
    )
    sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_empty_discover)

    sp = sub.add_parser(
        "empty-enrich",
        help="READ/HTTP: lookup ИНН + бренд-классификация для isolated empty-company pool",
    )
    sp.add_argument("--limit", type=int)
    sp.add_argument("--throttle", type=float, default=0.1)
    sp.set_defaults(func=cmd_empty_enrich)

    sp = sub.add_parser(
        "empty-upload-plan",
        help="SHEETS: перезаписать вкладку 'Enrich empty — план' текущим plan-state",
    )
    sp.set_defaults(func=cmd_empty_upload_plan)

    sp = sub.add_parser(
        "empty-report",
        help="READ: checkpoint-сводка по isolated empty-company enrichment",
    )
    sp.add_argument("--top", type=int, default=10)
    sp.set_defaults(func=cmd_empty_report)

    sp = sub.add_parser(
        "empty-manual-site",
        help="SHEETS: сформировать вкладку ручного поиска актуального сайта/ИНН",
    )
    sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_empty_manual_site)

    sp = sub.add_parser(
        "empty-manual-site-promote",
        help="SHEETS/WRITE: принять approve=да из ручной вкладки и подготовить к empty-apply",
    )
    sp.add_argument("--live", action="store_true", help="Реально обновить state/сайт в Б24")
    sp.add_argument("--confirm-promote", action="store_true")
    sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_empty_manual_site_promote)

    sp = sub.add_parser(
        "empty-reconcile",
        help="READ/WRITE: убрать из плана компании, уже обогащённые verified-реквизитами в Б24, и проставить бренд",
    )
    sp.add_argument("--limit", type=int)
    sp.add_argument("--throttle", type=float, default=0.1)
    sp.set_defaults(func=cmd_empty_reconcile)

    sp = sub.add_parser(
        "empty-apply",
        help="WRITE: apply READY_TO_APPLY из isolated plan; реальный write требует --live --confirm-apply",
    )
    sp.add_argument("--live", action="store_true", help="Выполнить реальные Bitrix write-операции")
    sp.add_argument("--confirm-apply", action="store_true")
    sp.add_argument("--limit", type=int)
    sp.add_argument("--throttle", type=float, default=0.5)
    sp.set_defaults(func=cmd_empty_apply)

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
