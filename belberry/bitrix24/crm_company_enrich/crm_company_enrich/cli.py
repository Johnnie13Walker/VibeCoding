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
from dataclasses import asdict


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
        validate_uf_site=not args.skip_uf_site_validation,
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
        validate_uf_site=not args.skip_uf_site_validation,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("failed") else 0


def cmd_delete_sheet_row_guarded(args: argparse.Namespace) -> int:
    from .stages import sheet_row_guard
    bx, sheets = _make_clients()
    summary = sheet_row_guard.delete_row_guarded(
        bx,
        sheets.service,
        sheet_id=args.sheet_id,
        tab_title=args.tab,
        sheet_gid=args.gid,
        row_number=args.row_number,
        deal_id=args.deal_id or "",
        company_id=args.company_id or "",
        live=args.live,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("error") else 0


def cmd_auto_reject_telemarketing(args: argparse.Namespace) -> int:
    from .stages import auto_reject_telemarketing
    bx, _ = _make_clients()
    summary = auto_reject_telemarketing.run(
        bx,
        dry_run=not args.live,
        limit=args.limit,
        stages=args.stage,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not summary.get("failed") else 1


def cmd_enrich_company_full(args: argparse.Namespace) -> int:
    from .stages import enrich_company_full

    bx, _ = _make_clients()
    outcome = enrich_company_full.run(
        bx,
        company_id=args.company_id or "",
        deal_id=args.deal_id or "",
        inn=args.inn or "",
        url=args.url or "",
        create_if_missing=args.create_if_missing,
        dry_run=not args.live,
        skip_bp=args.skip_bp,
        skip_dedupe_contacts=args.skip_dedupe_contacts,
        skip_director_inn=args.skip_director_inn,
        skip_telemarketing_dedupe=args.skip_telemarketing_dedupe,
        skip_auto_reject=args.skip_auto_reject,
        no_create_deal=args.no_create_deal,
        no_touch_existing_deals=args.no_touch_existing_deals,
        skip_cross_category_dup_check=args.skip_cross_category_dup_check,
        skip_on_closed_dup=args.skip_on_closed_dup,
        skip_uf_site_validation=args.skip_uf_site_validation,
        bizproc_wait_s=args.bizproc_wait_s,
    )
    print(json.dumps(asdict(outcome), indent=2, ensure_ascii=False, default=str))
    return 1 if outcome.final_status == "FAILED" else 0


def cmd_rebind_orphan_deal(args: argparse.Namespace) -> int:
    from .stages import rebind_orphan_deal

    bx, _ = _make_clients()
    summary = rebind_orphan_deal.run(
        bx,
        deal_id=args.deal_id,
        url=args.url,
        dry_run=not args.live,
        allow_live_company=args.allow_live_company,
        allow_liquidated=args.allow_liquidated,
        bizproc_wait_s=args.bizproc_wait_s,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 1 if summary.get("status") == "FAILED" else 0


def cmd_enrich_from_sheet(args: argparse.Namespace) -> int:
    from .stages import enrich_from_sheet

    if not (args.from_sheet or args.from_bitrix_filter or args.from_file):
        print("Нужен хотя бы один источник: --from-sheet, --from-bitrix-filter или --from-file", file=sys.stderr)
        return 2
    if args.from_sheet and (not args.tab or not args.id_column):
        print("Для --from-sheet обязательны --tab и --id-column", file=sys.stderr)
        return 2
    if args.skip_bp and args.full_bp:
        print("--skip-bp и --full-bp нельзя указывать одновременно", file=sys.stderr)
        return 2

    bx, sheets = _make_clients()
    inputs = []
    if args.from_sheet:
        inputs += enrich_from_sheet.load_inputs_from_sheet(
            sheets,
            args.from_sheet,
            args.tab,
            args.id_column,
        )
    if args.from_bitrix_filter:
        inputs += enrich_from_sheet.load_inputs_from_bitrix_filter(
            bx,
            json.loads(args.from_bitrix_filter),
        )
    if args.from_file:
        inputs += enrich_from_sheet.load_inputs_from_file(args.from_file)

    inputs = enrich_from_sheet.deduplicate_inputs(inputs)
    summary = enrich_from_sheet.run(
        bx,
        sheets,
        inputs=inputs,
        output_sheet_id=args.output_sheet or "auto",
        output_tab=args.output_tab or "results",
        dry_run=not args.live,
        skip_bp=True if args.skip_bp else None,
        full_bp=args.full_bp,
        max_duration_min=args.max_duration_min,
        limit=args.limit,
        cron_mode=args.cron,
        skip_cross_category_dup_check=args.skip_cross_category_dup_check,
        skip_on_closed_dup=args.skip_on_closed_dup,
        skip_uf_site_validation=args.skip_uf_site_validation,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not summary.get("failed") else 1


def cmd_enrich_from_sheet_inplace(args: argparse.Namespace) -> int:
    from .stages import enrich_from_sheet_inplace

    if args.skip_bp and args.full_bp:
        print("--skip-bp и --full-bp нельзя указывать одновременно", file=sys.stderr)
        return 2

    bx, sheets = _make_clients()
    summary = enrich_from_sheet_inplace.run_in_place(
        bx,
        sheets.service,
        sheet_id=args.sheet_id,
        tab_title=args.tab,
        dry_run=not args.live,
        skip_bp=True if args.skip_bp else None,
        full_bp=args.full_bp,
        max_duration_min=args.max_duration_min,
        limit=args.limit,
        cron_mode=args.cron,
        skip_already_processed=not args.no_skip_processed,
        skip_cross_category_dup_check=args.skip_cross_category_dup_check,
        skip_on_closed_dup=args.skip_on_closed_dup,
        skip_uf_site_validation=args.skip_uf_site_validation,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not summary.get("failed") else 1


def cmd_audit_uf_sites(args: argparse.Namespace) -> int:
    from .stages import audit_uf_sites

    if args.live and not args.rollback_to_vk and not args.clear_dead:
        print(
            "Для live cleanup нужен --live --rollback-to-vk или --live --clear-dead",
            file=sys.stderr,
        )
        return 2
    if args.rollback_to_vk and args.clear_dead:
        print("--rollback-to-vk и --clear-dead взаимоисключающи", file=sys.stderr)
        return 2

    raw_reasons = (args.clear_dead_reasons or "").strip()
    if raw_reasons:
        clear_reasons = tuple(
            reason.strip()
            for reason in raw_reasons.split(",")
            if reason.strip()
        )
    else:
        clear_reasons = audit_uf_sites.DEFAULT_CLEAR_DEAD_REASONS

    bx, _ = _make_clients()
    summary = audit_uf_sites.run(
        bx,
        dry_run=not args.live,
        rollback_to_vk=args.rollback_to_vk,
        clear_dead=args.clear_dead,
        clear_dead_reasons=clear_reasons,
        skip_if_has_deals=not args.force_with_deals,
        force_with_deals=args.force_with_deals,
    )
    printable = dict(summary)
    printable["result_count"] = len(printable.pop("results", []) or [])
    print(json.dumps(printable, indent=2, ensure_ascii=False, default=str))
    return 0


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


def cmd_rebind_orphan_contacts(args: argparse.Namespace) -> int:
    from .stages import rebind_orphan_contacts
    bx, _ = _make_clients()
    summary = rebind_orphan_contacts.run_batch(
        bx,
        dry_run=not args.live,
        limit=args.limit,
        sources=(args.sources.split(",") if args.sources else None),
    )
    # Не печатаем per-contact outcomes для 3.7k строк — только агрегат.
    summary.pop("outcomes", None)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


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


def cmd_telemarketing_stuck_alerts(args: argparse.Namespace) -> int:
    from datetime import datetime

    from .stages import telemarketing_stuck_alerts

    bx, _ = _make_clients()
    today = datetime.fromisoformat(args.today).date() if args.today else None
    summary = telemarketing_stuck_alerts.run(bx, today=today)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


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


def cmd_contact_personal_inn_field(args: argparse.Namespace) -> int:
    from .stages import contact_personal_inn_field
    bx, _ = _make_clients()
    summary = contact_personal_inn_field.run(
        bx,
        apply=args.apply,
        verify=not args.skip_verify,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    verification = summary.get("verification")
    if verification and not verification.get("ok"):
        return 1
    return 0


def cmd_enrich_director_inn(args: argparse.Namespace) -> int:
    from .stages import enrich_director_inn
    bx, _ = _make_clients()
    summary = enrich_director_inn.run_company(
        bx,
        company_id=args.company_id,
        dry_run=not args.live,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary.get("failed") else 0


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
    sp.add_argument("--skip-uf-site-validation", action="store_true", help="Emergency-обход pre-validation UF site")
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
    sp.add_argument("--skip-uf-site-validation", action="store_true", help="Emergency-обход pre-validation UF site")
    sp.set_defaults(func=cmd_sync_company)

    sp = sub.add_parser(
        "delete-sheet-row-guarded",
        help="SHEETS/WRITE: удалить строку только после brand/industry parity read-back",
    )
    sp.add_argument("--row-number", type=int, required=True, help="1-based номер строки в Google Sheets")
    sp.add_argument("--deal-id", help="Bitrix deal_id; если пусто, берётся из колонки I")
    sp.add_argument("--company-id", help="Bitrix company_id; если пусто, берётся из колонки M или сделки")
    sp.add_argument("--sheet-id", default="13L0gqwkNzrWacYeI5TzkOxZuRuXn5bBCtfxx-uzHH_4")
    sp.add_argument("--tab", default="Телемаркетинг без реквизитов")
    sp.add_argument("--gid", type=int, default=1318170868)
    sp.add_argument("--live", action="store_true", help="Реально удалить строку; без флага только проверка")
    sp.set_defaults(func=cmd_delete_sheet_row_guarded)

    sp = sub.add_parser(
        "auto-reject-telemarketing",
        help=(
            "WRITE: автоматически закрыть сделки в C50:UC_1S1KIU/NEW по причинам "
            "Ликвидирована (8538) или Выручка <30M (8542). По умолчанию dry-run."
        ),
    )
    sp.add_argument("--live", action="store_true")
    sp.add_argument("--limit", type=int, help="Ограничить число обработанных сделок")
    sp.add_argument(
        "--stage",
        action="append",
        help="Конкретные стадии для скана (по умолчанию UC_1S1KIU,NEW)",
    )
    sp.set_defaults(func=cmd_auto_reject_telemarketing)

    sp = sub.add_parser(
        "enrich-company-full",
        help=(
            "WRITE: главный orchestrator — обогащение одной компании "
            "end-to-end. По умолчанию dry-run."
        ),
    )
    input_group = sp.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--company-id")
    input_group.add_argument("--deal-id")
    input_group.add_argument("--inn")
    input_group.add_argument("--url")
    sp.add_argument("--live", action="store_true", help="Реально писать в Bitrix")
    sp.add_argument("--create-if-missing", action="store_true", help="Создать компанию в Bitrix, если не найдена")
    sp.add_argument("--skip-bp", action="store_true", help="Не запускать BP 5938+8612")
    sp.add_argument("--skip-dedupe-contacts", action="store_true")
    sp.add_argument("--skip-director-inn", action="store_true")
    sp.add_argument("--skip-telemarketing-dedupe", action="store_true")
    sp.add_argument("--skip-auto-reject", action="store_true")
    sp.add_argument("--no-create-deal", action="store_true", help="Не создавать новую сделку в CREATE_DEAL")
    sp.add_argument(
        "--no-touch-existing-deals",
        action="store_true",
        help="Не искать и не менять существующие сделки компании",
    )
    sp.add_argument(
        "--skip-cross-category-dup-check",
        action="store_true",
        help="Emergency-обход защиты от дублей C50/C10 по домену",
    )
    sp.add_argument(
        "--skip-on-closed-dup",
        action="store_true",
        help="Блокировать создание даже если найден только закрытый дубль C50/C10",
    )
    sp.add_argument("--bizproc-wait-s", type=int)
    sp.add_argument("--skip-uf-site-validation", action="store_true", help="Emergency-обход pre-validation UF site")
    sp.set_defaults(func=cmd_enrich_company_full)

    sp = sub.add_parser(
        "rebind-orphan-deal",
        help=(
            "WRITE: обогатить/создать компанию по сайту и перевязать "
            "существующую orphan-сделку без создания дубля. По умолчанию dry-run."
        ),
    )
    sp.add_argument("--deal-id", required=True, help="ID существующей orphan-сделки")
    sp.add_argument("--url", required=True, help="Сайт/домен для поиска ИНН и компании")
    sp.add_argument("--live", action="store_true", help="Реально писать в Bitrix")
    sp.add_argument(
        "--allow-live-company",
        action="store_true",
        help="Разрешить rebind, даже если старый COMPANY_ID сделки всё ещё открывается",
    )
    sp.add_argument(
        "--allow-liquidated",
        action="store_true",
        help="Разрешить rebind на компанию со статусом ликвидации",
    )
    sp.add_argument("--bizproc-wait-s", type=int)
    sp.set_defaults(func=cmd_rebind_orphan_deal)

    sp = sub.add_parser(
        "enrich-from-sheet",
        help="WRITE: batch-обогащение компаний через enrich-company-full. По умолчанию dry-run.",
    )
    sp.add_argument("--from-sheet", help="ID Google Sheet-источника")
    sp.add_argument("--from-bitrix-filter", help="JSON filter для crm.company.list")
    sp.add_argument("--from-file", help="Путь к txt-файлу с company_id/inn/url")
    sp.add_argument("--tab", help="Вкладка source Sheet")
    sp.add_argument("--id-column", help="Название source-колонки с company_id/inn/url")
    sp.add_argument("--output-sheet", help="ID или 'auto' для создания нового")
    sp.add_argument("--output-tab", default="results")
    sp.add_argument("--live", action="store_true", help="Реально писать в Bitrix")
    sp.add_argument("--skip-bp", action="store_true", help="Принудительно пропустить BP")
    sp.add_argument("--full-bp", action="store_true", help="Принудительно запускать BP")
    sp.add_argument("--cron", action="store_true", help="cron-режим с проверкой окна 00:00-08:00 МСК")
    sp.add_argument("--max-duration-min", type=int, default=480)
    sp.add_argument("--limit", type=int)
    sp.add_argument(
        "--skip-cross-category-dup-check",
        action="store_true",
        help="Emergency-обход защиты от дублей C50/C10 по домену",
    )
    sp.add_argument(
        "--skip-on-closed-dup",
        action="store_true",
        help="Блокировать создание даже если найден только закрытый дубль C50/C10",
    )
    sp.add_argument("--skip-uf-site-validation", action="store_true", help="Emergency-обход pre-validation UF site")
    sp.set_defaults(func=cmd_enrich_from_sheet)

    sp = sub.add_parser(
        "enrich-from-sheet-inplace",
        help=(
            "WRITE: batch-обогащение по списку сделок в табе Google Sheets, "
            "запись результатов и раскраска в исходный таб (cols I-U). "
            "Resume-safe (пропускает строки с заполненным status). По умолчанию dry-run."
        ),
    )
    sp.add_argument("--sheet-id", required=True, help="ID Google Sheets с табом-источником")
    sp.add_argument("--tab", required=True, help="Название таба (например 'Телемаркетинг без реквизитов')")
    sp.add_argument("--live", action="store_true", help="Реально писать в Bitrix")
    sp.add_argument("--skip-bp", action="store_true", help="Принудительно пропустить BP")
    sp.add_argument("--full-bp", action="store_true", help="Принудительно запускать BP")
    sp.add_argument("--cron", action="store_true", help="cron-режим с проверкой окна 00:00-08:00 МСК")
    sp.add_argument("--max-duration-min", type=int, default=480)
    sp.add_argument("--limit", type=int, help="Обработать не более N строк")
    sp.add_argument("--no-skip-processed", action="store_true",
                    help="Не пропускать строки с уже заполненным status (col K)")
    sp.add_argument(
        "--skip-cross-category-dup-check",
        action="store_true",
        help="Emergency-обход защиты от дублей C50/C10 по домену",
    )
    sp.add_argument(
        "--skip-on-closed-dup",
        action="store_true",
        help="Блокировать создание даже если найден только закрытый дубль C50/C10",
    )
    sp.add_argument("--skip-uf-site-validation", action="store_true", help="Emergency-обход pre-validation UF site")
    sp.set_defaults(func=cmd_enrich_from_sheet_inplace)

    sp = sub.add_parser(
        "audit-uf-sites",
        help=(
            "READ/WRITE: проверить живость UF site; live cleanup только с "
            "--live --rollback-to-vk или --live --clear-dead"
        ),
    )
    src = sp.add_mutually_exclusive_group()
    src.add_argument("--from-sheet", action="store_true", help="Зарезервировано; сейчас audit идёт по Bitrix")
    src.add_argument("--all", action="store_true", help="Проверить все компании с UF site (default)")
    sp.add_argument("--rollback-to-vk", action="store_true", help="Для dead UF вернуть VK/2gis из WEB[]")
    sp.add_argument(
        "--clear-dead",
        action="store_true",
        help="Для dead UF очистить поле (по умолчанию только reasons из --clear-dead-reasons)",
    )
    sp.add_argument(
        "--clear-dead-reasons",
        default="",
        help=(
            "Через запятую: какие reasons чистить в --clear-dead режиме. "
            "По умолчанию: dns,conn_refused (надёжно мёртвые). "
            "Допустимо: dns,conn_refused,5xx,timeout,ssl_error,bad_url,4xx_blocked"
        ),
    )
    sp.add_argument(
        "--force-with-deals",
        action="store_true",
        help=(
            "ОПАСНО: чистить UF и у компаний, где есть сделки (любые, включая WON). "
            "По умолчанию такие компании пропускаются — защита от потери истории "
            "клиента, у которого просто умер домен. Используй только если ты уверен."
        ),
    )
    sp.add_argument("--dry-run", action="store_true", help="Явный read-only режим (default)")
    sp.add_argument(
        "--live",
        action="store_true",
        help="Реально обновить Bitrix; требует --rollback-to-vk или --clear-dead",
    )
    sp.set_defaults(func=cmd_audit_uf_sites)

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
        "rebind-orphan-contacts",
        help=(
            "WRITE: привязать контакты-сироты (импорт «Вернувшийся клиент») "
            "к компаниям/сделкам по телефону. По умолчанию dry-run + отчёт в "
            "Sheets (contact_rebind_plan); --live для записи в Bitrix."
        ),
    )
    sp.add_argument("--live", action="store_true")
    sp.add_argument("--limit", type=int, help="Ограничить число контактов (для smoke)")
    sp.add_argument(
        "--sources",
        help="SOURCE_ID сирот через запятую (по умолчанию из конфига: 5)",
    )
    sp.set_defaults(func=cmd_rebind_orphan_contacts)

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
        "telemarketing-stuck-alerts",
        help="READ: найти застрявшие C50:PREPARATION и C50:UC_WZ4KQE сделки",
    )
    sp.add_argument("--today", help="ISO date YYYY-MM-DD для тестового расчёта")
    sp.set_defaults(func=cmd_telemarketing_stuck_alerts)

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
        "contact-personal-inn-field",
        help=(
            "WRITE: проверить/создать UF контакта для ИНН физлица. "
            "По умолчанию dry-run; запись только с --apply."
        ),
    )
    sp.add_argument("--apply", action="store_true", help="Реально создать или обновить поле в Bitrix24")
    sp.add_argument("--skip-verify", action="store_true", help="Не читать поле повторно после --apply")
    sp.set_defaults(func=cmd_contact_personal_inn_field)

    sp = sub.add_parser(
        "enrich-director-inn",
        help=(
            "WRITE: записать ИНН физлица директора в Bitrix-контакт по "
            "данным rusprofile (только ЮЛ; ИП пропускаются). По умолчанию dry-run."
        ),
    )
    sp.add_argument("--company-id", required=True)
    sp.add_argument("--live", action="store_true")
    sp.set_defaults(func=cmd_enrich_director_inn)

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
