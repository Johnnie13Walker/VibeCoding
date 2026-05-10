"""Run manifest и apply-token contract для duplicate merge.

Модуль не выполняет CRM/Sheet apply. Он только создает и валидирует
артефакты, которые позже будут использоваться apply-engine safety gates.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from belberry.bitrix24.policies.operation_key import POLICY_VERSION

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
RUN_ID_PATTERN = re.compile(r"^\d{8}-\d{6}-MSK-[0-9a-f]{8}$")
CONFIRM_TOKEN_PREFIX = "MERGE_REANIMATION_"
MANIFEST_FILENAME = "manifest.json"
ALLOWED_MODES = frozenset({"dry-run", "apply"})


class ApplyForbidden(RuntimeError):
    """Apply запрещен: run_id или confirm-token не совпали с manifest."""


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    started_at_msk: str
    policy_version: str
    sheet_id: str
    operation_key: str
    mode: str
    confirm_token: str
    dry_run_artifact: str
    fingerprint_at_dry_run: str = ""
    status: str = "dry_run_written"

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def _now_msk() -> datetime:
    return datetime.now(MOSCOW_TZ)


def _format_started_at_msk(value: datetime | str | None) -> str:
    if value is None:
        return _now_msk().isoformat(timespec="seconds")
    if isinstance(value, datetime):
        current = value.replace(tzinfo=MOSCOW_TZ) if value.tzinfo is None else value.astimezone(MOSCOW_TZ)
        return current.isoformat(timespec="seconds")
    text = str(value or "").strip()
    if not text:
        raise ValueError("started_at_msk is required")
    return text


def _validate_run_id(run_id: str) -> str:
    text = str(run_id or "").strip()
    if not RUN_ID_PATTERN.fullmatch(text):
        raise ValueError("run_id must match YYYYMMDD-HHMMSS-MSK-<8hex>")
    try:
        datetime.strptime(text[:15], "%Y%m%d-%H%M%S")
    except ValueError as error:
        raise ValueError("run_id contains invalid timestamp") from error
    return text


def _validate_required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _validate_mode(mode: str) -> str:
    text = str(mode or "").strip()
    if text not in ALLOWED_MODES:
        raise ValueError("mode must be dry-run or apply")
    return text


def _validate_manifest(manifest: RunManifest) -> RunManifest:
    run_id = _validate_run_id(manifest.run_id)
    mode = _validate_mode(manifest.mode)
    expected_token = f"{CONFIRM_TOKEN_PREFIX}{run_id}"
    if manifest.confirm_token != expected_token:
        raise ValueError("confirm_token does not match run_id")
    return RunManifest(
        run_id=run_id,
        started_at_msk=_validate_required_text(manifest.started_at_msk, "started_at_msk"),
        policy_version=_validate_required_text(manifest.policy_version, "policy_version"),
        sheet_id=_validate_required_text(manifest.sheet_id, "sheet_id"),
        operation_key=_validate_required_text(manifest.operation_key, "operation_key"),
        mode=mode,
        confirm_token=expected_token,
        dry_run_artifact=_validate_required_text(manifest.dry_run_artifact, "dry_run_artifact"),
        fingerprint_at_dry_run=str(manifest.fingerprint_at_dry_run or ""),
        status=_validate_required_text(manifest.status, "status"),
    )


def generate_run_id(now_msk: datetime | None = None) -> str:
    """Возвращает run_id формата YYYYMMDD-HHMMSS-MSK-<8hex>."""
    current = now_msk if now_msk is not None else _now_msk()
    current = current.replace(tzinfo=MOSCOW_TZ) if current.tzinfo is None else current.astimezone(MOSCOW_TZ)
    return f"{current:%Y%m%d-%H%M%S}-MSK-{secrets.token_hex(4)}"


def create_manifest(
    *,
    run_id: str,
    sheet_id: str,
    operation_key: str,
    mode: str,
    dry_run_artifact: str,
    started_at_msk: datetime | str | None = None,
    policy_version: str = POLICY_VERSION,
    fingerprint_at_dry_run: str = "",
    status: str = "dry_run_written",
) -> RunManifest:
    """Создает manifest и заполняет confirm_token из run_id."""
    normalized_run_id = _validate_run_id(run_id)
    manifest = RunManifest(
        run_id=normalized_run_id,
        started_at_msk=_format_started_at_msk(started_at_msk),
        policy_version=str(policy_version or "").strip(),
        sheet_id=str(sheet_id or "").strip(),
        operation_key=str(operation_key or "").strip(),
        mode=str(mode or "").strip(),
        confirm_token=f"{CONFIRM_TOKEN_PREFIX}{normalized_run_id}",
        dry_run_artifact=str(dry_run_artifact or "").strip(),
        fingerprint_at_dry_run=str(fingerprint_at_dry_run or ""),
        status=str(status or "").strip(),
    )
    return _validate_manifest(manifest)


def write_manifest(manifest_dir: Path, manifest: RunManifest) -> Path:
    """Атомарно пишет manifest.json в manifest_dir с правами 0o600."""
    target_dir = Path(manifest_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / MANIFEST_FILENAME
    validated = _validate_manifest(manifest)
    payload = json.dumps(validated.to_json(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(tmp, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
        os.chmod(target, 0o600)
    finally:
        tmp.unlink(missing_ok=True)
    return target


def _manifest_from_payload(payload: Mapping[str, Any]) -> RunManifest:
    required = {
        "run_id",
        "started_at_msk",
        "policy_version",
        "sheet_id",
        "operation_key",
        "mode",
        "confirm_token",
        "dry_run_artifact",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"manifest missing required fields: {', '.join(missing)}")
    return RunManifest(
        run_id=str(payload["run_id"]),
        started_at_msk=str(payload["started_at_msk"]),
        policy_version=str(payload["policy_version"]),
        sheet_id=str(payload["sheet_id"]),
        operation_key=str(payload["operation_key"]),
        mode=str(payload["mode"]),
        confirm_token=str(payload["confirm_token"]),
        dry_run_artifact=str(payload["dry_run_artifact"]),
        fingerprint_at_dry_run=str(payload.get("fingerprint_at_dry_run", "")),
        status=str(payload.get("status", "dry_run_written")),
    )


def load_manifest(manifest_path: Path) -> RunManifest:
    """Читает manifest JSON и валидирует apply-token contract."""
    path = Path(manifest_path)
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as error:
        raise ValueError("manifest contains invalid JSON") from error
    except OSError as error:
        raise ValueError(f"manifest cannot be read: {error}") from error
    if not isinstance(payload, Mapping):
        raise ValueError("manifest must be a JSON object")
    return _validate_manifest(_manifest_from_payload(payload))


def validate_apply_request(
    manifest: RunManifest,
    *,
    provided_token: str,
    provided_run_id: str,
) -> None:
    """Проверяет explicit apply token и run_id перед любым CRM/Sheet apply."""
    validated = _validate_manifest(manifest)
    if str(provided_run_id or "").strip() != validated.run_id:
        raise ApplyForbidden("provided run_id does not match manifest")
    if str(provided_token or "").strip() != validated.confirm_token:
        raise ApplyForbidden("provided confirm token does not match manifest")
