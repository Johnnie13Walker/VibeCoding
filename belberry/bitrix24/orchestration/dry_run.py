"""Dry-run artifacts и optimistic fingerprint для duplicate merge.

Модуль принимает уже полученный live backup и результаты policy/risk.
Он не читает CRM/Sheet и не выполняет apply.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from belberry.bitrix24.orchestration.run import RunManifest, create_manifest, write_manifest
from belberry.bitrix24.policies.operation_key import POLICY_VERSION

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
FINGERPRINT_SCHEMA_VERSION = f"duplicate-merge-backup-fingerprint:{POLICY_VERSION}"
DRY_RUN_ARTIFACT_FILENAME = "dry_run_plan.json"


@dataclass(frozen=True)
class DryRunArtifact:
    run_id: str
    created_at_msk: str
    policy_version: str
    sheet_id: str
    operation_key: str
    domain: str
    target_id: str
    deal_ids: tuple[str, ...]
    backup_fingerprint: str
    policy_plan: Mapping[str, Any]
    risk: Mapping[str, Any]
    status: str = "dry_run_written"

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["deal_ids"] = list(self.deal_ids)
        return payload


@dataclass(frozen=True)
class DryRunPackage:
    manifest: RunManifest
    manifest_path: Path
    artifact: DryRunArtifact
    artifact_path: Path


def _now_msk() -> str:
    return datetime.now(MOSCOW_TZ).isoformat(timespec="seconds")


def _string_id(value: Any) -> str:
    text = str(value or "").strip()
    return text if text.isdigit() else ""


def _normalize_deal_ids(deal_ids: Sequence[Any]) -> tuple[str, ...]:
    ids = tuple(_string_id(item) for item in deal_ids if _string_id(item))
    if len(ids) < 2:
        raise ValueError("deal_ids must contain at least two numeric ids")
    return ids


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _sort_backup_deals(backup: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(backup)
    deals = backup.get("deals")
    if isinstance(deals, list):
        normalized["deals"] = sorted(
            deals,
            key=lambda item: (
                _string_id(item.get("id")) if isinstance(item, Mapping) else "",
                _canonical_json(item),
            ),
        )
    return normalized


def _normalize_for_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize_for_json(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, (list, tuple)):
        normalized_items = [_normalize_for_json(item) for item in value]
        return sorted(normalized_items, key=_canonical_json)
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(_normalize_for_json(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def backup_fingerprint(backup: Mapping[str, Any]) -> str:
    """Считает sha256 fingerprint live backup для apply-time reconcile."""
    if not isinstance(backup, Mapping):
        raise ValueError("backup must be a mapping")
    payload = {
        "schema": FINGERPRINT_SCHEMA_VERSION,
        "backup": _sort_backup_deals(backup),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def build_dry_run_artifact(
    *,
    run_id: str,
    sheet_id: str,
    operation_key: str,
    domain: str,
    target_id: str,
    deal_ids: Sequence[Any],
    backup: Mapping[str, Any],
    policy_plan: Mapping[str, Any],
    risk: Mapping[str, Any],
    created_at_msk: str | None = None,
    policy_version: str = POLICY_VERSION,
    status: str = "dry_run_written",
) -> DryRunArtifact:
    """Строит видимый dry-run plan без записи на диск."""
    return DryRunArtifact(
        run_id=_required_text(run_id, "run_id"),
        created_at_msk=_required_text(created_at_msk or _now_msk(), "created_at_msk"),
        policy_version=_required_text(policy_version, "policy_version"),
        sheet_id=_required_text(sheet_id, "sheet_id"),
        operation_key=_required_text(operation_key, "operation_key"),
        domain=_required_text(domain, "domain"),
        target_id=_required_text(target_id, "target_id"),
        deal_ids=_normalize_deal_ids(deal_ids),
        backup_fingerprint=backup_fingerprint(backup),
        policy_plan=dict(policy_plan),
        risk=dict(risk),
        status=_required_text(status, "status"),
    )


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def write_dry_run_artifact(artifact_dir: Path, artifact: DryRunArtifact) -> Path:
    """Атомарно пишет dry_run_plan.json с правами 0o600."""
    return _write_json_atomic(Path(artifact_dir) / DRY_RUN_ARTIFACT_FILENAME, artifact.to_json())


def load_dry_run_artifact(artifact_path: Path) -> DryRunArtifact:
    """Читает dry_run_plan.json и проверяет обязательные поля."""
    path = Path(artifact_path)
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as error:
        raise ValueError("dry-run artifact contains invalid JSON") from error
    except OSError as error:
        raise ValueError(f"dry-run artifact cannot be read: {error}") from error
    if not isinstance(payload, Mapping):
        raise ValueError("dry-run artifact must be a JSON object")
    missing = sorted(
        {
            "run_id",
            "created_at_msk",
            "policy_version",
            "sheet_id",
            "operation_key",
            "domain",
            "target_id",
            "deal_ids",
            "backup_fingerprint",
            "policy_plan",
            "risk",
        }
        - set(payload)
    )
    if missing:
        raise ValueError(f"dry-run artifact missing required fields: {', '.join(missing)}")
    deal_ids = payload["deal_ids"]
    if not isinstance(deal_ids, list):
        raise ValueError("deal_ids must be a list")
    return DryRunArtifact(
        run_id=_required_text(payload["run_id"], "run_id"),
        created_at_msk=_required_text(payload["created_at_msk"], "created_at_msk"),
        policy_version=_required_text(payload["policy_version"], "policy_version"),
        sheet_id=_required_text(payload["sheet_id"], "sheet_id"),
        operation_key=_required_text(payload["operation_key"], "operation_key"),
        domain=_required_text(payload["domain"], "domain"),
        target_id=_required_text(payload["target_id"], "target_id"),
        deal_ids=_normalize_deal_ids(deal_ids),
        backup_fingerprint=_required_text(payload["backup_fingerprint"], "backup_fingerprint"),
        policy_plan=dict(payload["policy_plan"]) if isinstance(payload["policy_plan"], Mapping) else {},
        risk=dict(payload["risk"]) if isinstance(payload["risk"], Mapping) else {},
        status=str(payload.get("status", "dry_run_written") or "dry_run_written"),
    )


def _ensure_inside_workspace(path: Path, *, workspace_root: Path) -> Path:
    root = workspace_root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"path outside workspace is forbidden: {path}") from error
    return resolved


def write_dry_run_package(
    *,
    workspace_root: Path,
    run_id: str,
    sheet_id: str,
    operation_key: str,
    domain: str,
    target_id: str,
    deal_ids: Sequence[Any],
    backup: Mapping[str, Any],
    policy_plan: Mapping[str, Any],
    risk: Mapping[str, Any],
    created_at_msk: str | None = None,
) -> DryRunPackage:
    """Пишет dry-run artifact и manifest в стандартные директории workspace."""
    root = Path(workspace_root).resolve()
    if not root.exists():
        raise ValueError(f"workspace_root does not exist: {workspace_root}")
    artifact_dir = _ensure_inside_workspace(root / "outputs" / "runs" / run_id, workspace_root=root)
    manifest_dir = _ensure_inside_workspace(root / "state" / "runs" / run_id, workspace_root=root)
    artifact = build_dry_run_artifact(
        run_id=run_id,
        sheet_id=sheet_id,
        operation_key=operation_key,
        domain=domain,
        target_id=target_id,
        deal_ids=deal_ids,
        backup=backup,
        policy_plan=policy_plan,
        risk=risk,
        created_at_msk=created_at_msk,
    )
    artifact_path = write_dry_run_artifact(artifact_dir, artifact)
    dry_run_artifact = str(artifact_path.relative_to(root))
    manifest = create_manifest(
        run_id=run_id,
        started_at_msk=artifact.created_at_msk,
        sheet_id=sheet_id,
        operation_key=operation_key,
        mode="dry-run",
        dry_run_artifact=dry_run_artifact,
        fingerprint_at_dry_run=artifact.backup_fingerprint,
        status="dry_run_written",
    )
    manifest_path = write_manifest(manifest_dir, manifest)
    return DryRunPackage(
        manifest=manifest,
        manifest_path=manifest_path,
        artifact=artifact,
        artifact_path=artifact_path,
    )
