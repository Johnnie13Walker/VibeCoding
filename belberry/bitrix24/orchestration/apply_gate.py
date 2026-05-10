"""Apply preflight gates перед любыми CRM/Sheet side effects.

Этот модуль проверяет apply-token contract и локальные safety gates.
Он не вызывает Bitrix, Google Sheet и не пишет ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from belberry.bitrix24.orchestration import ledger
from belberry.bitrix24.orchestration.dry_run import DryRunArtifact, load_dry_run_artifact
from belberry.bitrix24.orchestration.run import (
    RUN_ID_PATTERN,
    ApplyForbidden,
    RunManifest,
    load_manifest,
    validate_apply_request,
)


@dataclass(frozen=True)
class ApplyGateDecision:
    allowed: bool
    reasons: tuple[str, ...] = ()
    manifest: RunManifest | None = None
    artifact: DryRunArtifact | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def require_allowed(self) -> None:
        if not self.allowed:
            raise ApplyForbidden("; ".join(self.reasons) or "apply forbidden")


def _path_inside_workspace(path: Path, *, workspace_root: Path) -> Path:
    root = workspace_root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ApplyForbidden(f"path outside workspace is forbidden: {path}") from error
    return resolved


def _resolve_artifact_path(manifest: RunManifest, *, workspace_root: Path) -> Path:
    raw = Path(manifest.dry_run_artifact)
    if raw.is_absolute():
        return _path_inside_workspace(raw, workspace_root=workspace_root)
    return _path_inside_workspace(workspace_root / raw, workspace_root=workspace_root)


def validate_apply_preflight(
    *,
    workspace_root: Path,
    run_id: str,
    provided_token: str,
    current_live_fingerprint: str,
    ledger_path: Path,
    lock_acquired: bool,
    apply_disabled: bool,
) -> ApplyGateDecision:
    """Проверяет 8 apply gates и возвращает решение без side effects."""
    root = Path(workspace_root).resolve()
    if not RUN_ID_PATTERN.fullmatch(str(run_id or "").strip()):
        return ApplyGateDecision(allowed=False, reasons=("invalid_run_id",))
    manifest_path = _path_inside_workspace(root / "state" / "runs" / run_id / "manifest.json", workspace_root=root)
    reasons: list[str] = []
    manifest: RunManifest | None = None
    artifact: DryRunArtifact | None = None

    try:
        manifest = load_manifest(manifest_path)
        validate_apply_request(manifest, provided_token=provided_token, provided_run_id=run_id)
    except (ValueError, ApplyForbidden):
        reasons.append("invalid_apply_token_or_manifest")

    if manifest is not None:
        if not (manifest.mode == "dry-run" or manifest.status == "confirm_pending"):
            reasons.append("manifest_not_confirmable")

        try:
            artifact_path = _resolve_artifact_path(manifest, workspace_root=root)
            artifact = load_dry_run_artifact(artifact_path)
        except (ValueError, ApplyForbidden):
            reasons.append("dry_run_artifact_unreadable")

        expected_fingerprint = str(manifest.fingerprint_at_dry_run or "").strip()
        actual_fingerprint = str(current_live_fingerprint or "").strip()
        if not expected_fingerprint or actual_fingerprint != expected_fingerprint:
            reasons.append("fingerprint_mismatch")

        try:
            ledger_resolved = _path_inside_workspace(Path(ledger_path), workspace_root=root)
        except ApplyForbidden:
            reasons.append("ledger_path_outside_workspace")
        else:
            if ledger.is_operation_already_applied(ledger_resolved, manifest.operation_key):
                reasons.append("operation_already_applied")
            elif ledger.is_operation_locked_for_retry(ledger_resolved, manifest.operation_key):
                reasons.append("operation_locked_for_retry")

        if artifact is not None and artifact.operation_key != manifest.operation_key:
            reasons.append("artifact_operation_key_mismatch")

    if not lock_acquired:
        reasons.append("process_lock_not_acquired")
    if apply_disabled:
        reasons.append("apply_disabled")

    return ApplyGateDecision(
        allowed=not reasons,
        reasons=tuple(reasons),
        manifest=manifest,
        artifact=artifact,
        metadata={"manifest_path": str(manifest_path)},
    )
