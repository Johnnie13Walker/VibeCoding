"""Dry-run batch engine для duplicate merge pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from belberry.bitrix24.config.loader import BatchLimits, DuplicateMergeConfig
from belberry.bitrix24.orchestration.dry_run import DryRunPackage, write_dry_run_package
from belberry.bitrix24.orchestration.ledger import is_operation_already_applied
from belberry.bitrix24.orchestration.lock import process_lock
from belberry.bitrix24.orchestration.run import generate_run_id
from belberry.bitrix24.policies.merge_policy import build_policy_plan
from belberry.bitrix24.policies.operation_key import build_operation_key, normalize_domain
from belberry.bitrix24.policies.risk import RiskThresholds, preflight_high_conflict_risk
from belberry.bitrix24.providers.bitrix_oauth import BitrixOAuth
from belberry.bitrix24.providers.bitrix_reconciler import ReconcileSettings, live_reconcile
from belberry.bitrix24.providers.google_sheets import GoogleSheetsClient
from belberry.bitrix24.providers.logging import JsonlLogger, sanitize

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True)
class BatchEngineDeps:
    config: DuplicateMergeConfig
    sheets: GoogleSheetsClient
    oauth: BitrixOAuth
    reconciler_settings: ReconcileSettings
    logger: JsonlLogger | None = None
    now_utc: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


@dataclass(frozen=True)
class BatchEngineResult:
    run_id: str
    mode: str
    packages: tuple[DryRunPackage, ...]
    skipped_groups: tuple[dict[str, Any], ...]
    errors: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ParsedGroup:
    domain: str
    deal_ids: tuple[str, ...]
    target_id: str
    row_number: int


def _now_msk(now_utc: Callable[[], datetime]) -> datetime:
    current = now_utc()
    current = current.replace(tzinfo=timezone.utc) if current.tzinfo is None else current.astimezone(timezone.utc)
    return current.astimezone(MOSCOW_TZ)


def _workspace_root(config: DuplicateMergeConfig) -> Path:
    candidates = (
        config.process_lock_path,
        config.ledger_path,
        config.google_service_account_json,
        config.bitrix_app_state_dir,
    )
    for path in candidates:
        resolved = Path(path).resolve()
        parts = resolved.parts
        for index in range(len(parts) - 1, 1, -1):
            if parts[index - 1:index + 1] == ("belberry", "bitrix24"):
                return Path(*parts[: index + 1]).resolve()
    return Path(config.ledger_path).resolve().parent.parent


def _limits_to_thresholds(limits: BatchLimits) -> RiskThresholds:
    return RiskThresholds(
        max_group_size=limits.max_group_size,
        max_contact_additions=limits.max_contact_additions,
        max_deal_updates=limits.max_deal_updates,
        max_activities=limits.max_activities,
        max_timeline_comments=limits.max_timeline_comments,
        max_product_signatures=limits.max_product_signatures,
    )


def _header_index(header: Sequence[str]) -> dict[str, int]:
    aliases = {
        "domain": {"domain", "домен", "сайт", "site", "url"},
        "deal_ids": {"deal_ids", "deal ids", "ids", "id", "сделки", "ids сделок", "id сделок"},
        "target_id": {"target_id", "target id", "target", "основная сделка", "основная", "цель"},
    }
    result: dict[str, int] = {}
    for index, raw in enumerate(header):
        name = str(raw or "").strip().lower()
        for key, labels in aliases.items():
            if key not in result and name in labels:
                result[key] = index
    return result


def _digits_from_text(value: Any) -> tuple[str, ...]:
    current = ""
    result: list[str] = []
    for char in str(value or ""):
        if char.isdigit():
            current += char
        elif current:
            result.append(current)
            current = ""
    if current:
        result.append(current)
    return tuple(dict.fromkeys(result))


def _cell(row: Sequence[str], index: int) -> str:
    return str(row[index] if index < len(row) else "").strip()


def parse_groups(header: Sequence[str], rows: Sequence[Sequence[str]]) -> tuple[ParsedGroup, ...]:
    indexes = _header_index(header)
    missing = sorted({"domain", "deal_ids", "target_id"} - set(indexes))
    if missing:
        raise ValueError(f"source sheet missing required columns: {', '.join(missing)}")
    groups: list[ParsedGroup] = []
    for offset, row in enumerate(rows, start=2):
        domain = normalize_domain(_cell(row, indexes["domain"]))
        target_id = _digits_from_text(_cell(row, indexes["target_id"]))
        deal_ids = _digits_from_text(_cell(row, indexes["deal_ids"]))
        if not domain and not deal_ids and not target_id:
            continue
        if not domain or not deal_ids or not target_id:
            raise ValueError(f"row {offset}: domain, deal_ids and target_id are required")
        groups.append(ParsedGroup(domain=domain, deal_ids=deal_ids, target_id=target_id[0], row_number=offset))
    return tuple(groups)


def _error_payload(group: ParsedGroup | None, error: Exception) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "exception_type": type(error).__name__,
        "message": str(error),
    }
    if group is not None:
        payload["group"] = {
            "domain": group.domain,
            "deal_ids": list(group.deal_ids),
            "target_id": group.target_id,
            "row_number": group.row_number,
        }
    return sanitize(payload)


def _log(logger: JsonlLogger | None, level: str, event: str, **fields: Any) -> None:
    if logger is None:
        return
    if level == "error":
        logger.error(event, **fields)
    elif level == "warn":
        logger.warn(event, **fields)
    else:
        logger.info(event, **fields)


def run_dry_run_batch(
    *,
    deps: BatchEngineDeps,
    group_domain: str | None = None,
    max_groups: int = 1,
) -> BatchEngineResult:
    """Read-only batch pipeline: CRM/Sheet apply/write не выполняются."""
    if max_groups < 1:
        raise ValueError("max_groups must be positive")
    batch_run_id = generate_run_id(_now_msk(deps.now_utc))
    packages: list[DryRunPackage] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    domain_filter = normalize_domain(group_domain or "")
    thresholds = _limits_to_thresholds(deps.config.batch_limits)

    with process_lock(deps.config.process_lock_path, now_msk=_now_msk(deps.now_utc)):
        _log(deps.logger, "info", "batch_started", run_id=batch_run_id, max_groups=max_groups)
        try:
            snapshot = deps.sheets.read_snapshot(deps.config.sheet_id, deps.config.source_sheet)
            groups = parse_groups(snapshot.header, snapshot.rows)
        except Exception as error:  # noqa: BLE001
            errors.append(_error_payload(None, error))
            _log(deps.logger, "error", "batch_source_read_failed", error=errors[-1])
            return BatchEngineResult(batch_run_id, "dry-run", tuple(), tuple(), tuple(errors))

        selected = [group for group in groups if not domain_filter or group.domain == domain_filter][:max_groups]
        for group in selected:
            try:
                backup = live_reconcile(
                    oauth=deps.oauth,
                    deal_ids=group.deal_ids,
                    target_id=group.target_id,
                    settings=deps.reconciler_settings,
                )
                policy_plan = build_policy_plan(backup, target_id=group.target_id)
                risk = preflight_high_conflict_risk(backup, policy_plan, thresholds=thresholds)
                operation_key = build_operation_key(
                    sheet_id=deps.config.sheet_id,
                    domain=group.domain,
                    target_id=group.target_id,
                    deal_ids=group.deal_ids,
                )
                if is_operation_already_applied(deps.config.ledger_path, operation_key):
                    skipped_group = {
                        "domain": group.domain,
                        "deal_ids": list(group.deal_ids),
                        "target_id": group.target_id,
                        "operation_key": operation_key,
                        "reason": "operation_already_applied",
                    }
                    skipped.append(skipped_group)
                    _log(deps.logger, "info", "batch_group_skipped", **skipped_group)
                    continue
                package = write_dry_run_package(
                    workspace_root=_workspace_root(deps.config),
                    run_id=generate_run_id(_now_msk(deps.now_utc)),
                    sheet_id=deps.config.sheet_id,
                    operation_key=operation_key,
                    domain=group.domain,
                    target_id=group.target_id,
                    deal_ids=group.deal_ids,
                    backup=backup,
                    policy_plan=policy_plan,
                    risk=risk,
                )
                packages.append(package)
                _log(deps.logger, "info", "batch_group_dry_run_written", domain=group.domain, run_id=package.manifest.run_id)
            except Exception as error:  # noqa: BLE001
                errors.append(_error_payload(group, error))
                _log(deps.logger, "error", "batch_group_failed", error=errors[-1])

    result_run_id = packages[0].manifest.run_id if packages else batch_run_id
    return BatchEngineResult(
        run_id=result_run_id,
        mode="dry-run",
        packages=tuple(packages),
        skipped_groups=tuple(skipped),
        errors=tuple(errors),
    )


def run_apply_batch(*, deps, run_id, provided_token):
    """Apply branch появится после R4 executor."""
    raise NotImplementedError("apply branch требует R4 executor")
