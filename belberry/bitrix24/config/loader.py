"""Config loader для duplicate merge platform.

Защищает от:
- legacy env namespace (BITRIX_*, OPENCLAW_*, MARKETING_*) — отвергаются жестко;
- путей вне workspace `belberry/bitrix24/`;
- случайного включения apply без явного `BELBERRY_BITRIX24_APPLY_DISABLED=false`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

REQUIRED_PREFIX = "BELBERRY_BITRIX24_"
LEGACY_PREFIXES = ("BITRIX_", "OPENCLAW_", "MARKETING_")
DEFAULT_TIMEZONE = "Europe/Moscow"
DEFAULT_WORKSPACE_ROOT = Path("belberry/bitrix24")

REQUIRED_KEYS = (
    "BELBERRY_BITRIX24_PORTAL_BASE_URL",
    "BELBERRY_BITRIX24_PROCESS_LOCK_PATH",
    "BELBERRY_BITRIX24_LEDGER_PATH",
    "BELBERRY_BITRIX24_DUPLICATES_SHEET_ID",
    "BELBERRY_BITRIX24_DUPLICATES_WORK_SHEET",
    "BELBERRY_BITRIX24_DUPLICATES_ARCHIVE_SHEET",
    "BELBERRY_BITRIX24_DUPLICATES_SOURCE_SHEET",
    "BELBERRY_BITRIX24_GOOGLE_SERVICE_ACCOUNT_JSON",
    "BELBERRY_BITRIX24_APP_STATE_DIR",
)


class ConfigError(ValueError):
    """Безопасная ошибка валидации config: не содержит секретов."""


@dataclass(frozen=True)
class BatchLimits:
    max_group_size: int
    max_contact_additions: int
    max_deal_updates: int
    max_activities: int
    max_timeline_comments: int
    max_product_signatures: int
    request_pause_sec: float


@dataclass(frozen=True)
class DuplicateMergeConfig:
    timezone: str
    portal_base_url: str
    default_mode: str
    require_apply_confirmation: bool
    apply_disabled: bool
    process_lock_path: Path
    ledger_path: Path
    sheet_id: str
    work_sheet: str
    archive_sheet: str
    source_sheet: str
    google_service_account_json: Path
    bitrix_app_state_dir: Path
    bitrix_app_install_state_file: Path | None
    bitrix_oauth_token_url: str
    bitrix_timeout_sec: int
    batch_limits: BatchLimits


def assert_no_legacy_env(env: Mapping[str, str]) -> None:
    leaked = sorted(
        key
        for key in env
        if any(key.startswith(prefix) for prefix in LEGACY_PREFIXES) and not key.startswith(REQUIRED_PREFIX)
    )
    if leaked:
        raise ConfigError(
            "Legacy env namespace запрещен в этом workspace. "
            f"Удалите ключи: {', '.join(leaked)}"
        )


def enforce_path_inside_workspace(path: Path, *, workspace_root: Path) -> Path:
    resolved_root = workspace_root.resolve()
    candidate = path.expanduser()
    resolved = (resolved_root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise ConfigError(f"Путь вне workspace запрещен: {path}") from error
    if any(part == ".." for part in candidate.parts):
        raise ConfigError(f"Относительный путь с .. запрещен: {path}")
    return resolved


def is_apply_disabled(env: Mapping[str, str]) -> bool:
    raw = str(env.get("BELBERRY_BITRIX24_APPLY_DISABLED", "")).strip().lower()
    return raw != "false"


def _require(env: Mapping[str, str], key: str) -> str:
    value = str(env.get(key, "")).strip()
    if not value:
        raise ConfigError(f"Отсутствует обязательная переменная {key}")
    return value


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = str(env.get(key, "")).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as error:
        raise ConfigError(f"Переменная {key} должна быть целым числом") from error


def _float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = str(env.get(key, "")).strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as error:
        raise ConfigError(f"Переменная {key} должна быть числом") from error


def _bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = str(env.get(key, "")).strip().lower()
    if not raw:
        return default
    return raw in {"true", "1", "yes", "on"}


def load_config(
    env: Mapping[str, str] | None = None,
    *,
    workspace_root: Path | None = None,
) -> DuplicateMergeConfig:
    env = dict(os.environ if env is None else env)
    assert_no_legacy_env(env)

    workspace_root = (workspace_root or DEFAULT_WORKSPACE_ROOT).resolve()
    if not workspace_root.exists():
        raise ConfigError(f"workspace_root не существует: {workspace_root}")

    for key in REQUIRED_KEYS:
        _require(env, key)

    timezone = str(env.get("BELBERRY_BITRIX24_TIMEZONE") or DEFAULT_TIMEZONE).strip()
    if timezone != DEFAULT_TIMEZONE:
        raise ConfigError(f"timezone должен быть {DEFAULT_TIMEZONE}")

    default_mode = str(env.get("BELBERRY_BITRIX24_DEFAULT_MODE") or "dry-run").strip().lower()
    if default_mode not in {"dry-run", "apply"}:
        raise ConfigError("BELBERRY_BITRIX24_DEFAULT_MODE должен быть dry-run или apply")

    install_state_raw = str(env.get("BELBERRY_BITRIX24_APP_INSTALL_STATE_FILE", "")).strip()
    install_state = (
        enforce_path_inside_workspace(Path(install_state_raw), workspace_root=workspace_root)
        if install_state_raw
        else None
    )

    limits = BatchLimits(
        max_group_size=_int(env, "BELBERRY_BITRIX24_BATCH_MAX_GROUP_SIZE", 2),
        max_contact_additions=_int(env, "BELBERRY_BITRIX24_BATCH_MAX_CONTACT_ADDITIONS", 0),
        max_deal_updates=_int(env, "BELBERRY_BITRIX24_BATCH_MAX_DEAL_UPDATES", 2),
        max_activities=_int(env, "BELBERRY_BITRIX24_BATCH_MAX_ACTIVITIES", 30),
        max_timeline_comments=_int(env, "BELBERRY_BITRIX24_BATCH_MAX_TIMELINE_COMMENTS", 20),
        max_product_signatures=_int(env, "BELBERRY_BITRIX24_BATCH_MAX_PRODUCT_SIGNATURES", 0),
        request_pause_sec=_float(env, "BELBERRY_BITRIX24_REQUEST_PAUSE_SEC", 0.35),
    )

    return DuplicateMergeConfig(
        timezone=timezone,
        portal_base_url=_require(env, "BELBERRY_BITRIX24_PORTAL_BASE_URL").rstrip("/"),
        default_mode=default_mode,
        require_apply_confirmation=_bool(env, "BELBERRY_BITRIX24_REQUIRE_APPLY_CONFIRMATION", True),
        apply_disabled=is_apply_disabled(env),
        process_lock_path=enforce_path_inside_workspace(
            Path(_require(env, "BELBERRY_BITRIX24_PROCESS_LOCK_PATH")),
            workspace_root=workspace_root,
        ),
        ledger_path=enforce_path_inside_workspace(
            Path(_require(env, "BELBERRY_BITRIX24_LEDGER_PATH")),
            workspace_root=workspace_root,
        ),
        sheet_id=_require(env, "BELBERRY_BITRIX24_DUPLICATES_SHEET_ID"),
        work_sheet=_require(env, "BELBERRY_BITRIX24_DUPLICATES_WORK_SHEET"),
        archive_sheet=_require(env, "BELBERRY_BITRIX24_DUPLICATES_ARCHIVE_SHEET"),
        source_sheet=_require(env, "BELBERRY_BITRIX24_DUPLICATES_SOURCE_SHEET"),
        google_service_account_json=enforce_path_inside_workspace(
            Path(_require(env, "BELBERRY_BITRIX24_GOOGLE_SERVICE_ACCOUNT_JSON")),
            workspace_root=workspace_root,
        ),
        bitrix_app_state_dir=enforce_path_inside_workspace(
            Path(_require(env, "BELBERRY_BITRIX24_APP_STATE_DIR")),
            workspace_root=workspace_root,
        ),
        bitrix_app_install_state_file=install_state,
        bitrix_oauth_token_url=str(env.get("BELBERRY_BITRIX24_OAUTH_TOKEN_URL", "")).strip(),
        bitrix_timeout_sec=_int(env, "BELBERRY_BITRIX24_TIMEOUT_SEC", 20),
        batch_limits=limits,
    )
