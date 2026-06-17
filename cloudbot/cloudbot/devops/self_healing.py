"""Self-healing Cloudbot: проверка и автоматическое исправление типовых сбоев."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

DEFAULT_TIMEOUT_SEC = 8
HEALING_USER_AGENT = "CloudbotSelfHealing/1.0 (+https://cloudbot.local)"
MOCK_MODE = "mock"
REPO_ROOT = Path(__file__).resolve().parents[2]
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
MAX_TARGET_LOG_SIZE_BYTES = 50 * 1024 * 1024
EMPTY_CACHE_PAYLOAD = {
    "version": 1,
    "entries": {},
}
DEFAULT_SELF_HEALING_LOG_FILE = REPO_ROOT / "logs" / "self_healing.log"
DEFAULT_RUNTIME_CACHE_FILE = REPO_ROOT / "cache" / "cloudbot_runtime_state.json"
DEFAULT_RUNTIME_LOG_FILE = REPO_ROOT / "logs" / "cloudbot_runtime.log"


def _env_dict(env: Mapping[str, str] | None = None) -> dict[str, str]:
    if env is None:
        return dict(os.environ)
    return {str(key): str(value) for key, value in env.items()}


def _is_mock_mode(env: Mapping[str, str]) -> bool:
    return str(env.get("SELF_HEALING_MODE") or "").strip().lower() == MOCK_MODE


def _self_healing_log_file(env: Mapping[str, str]) -> Path:
    return Path(str(env.get("SELF_HEALING_LOG_FILE") or DEFAULT_SELF_HEALING_LOG_FILE))


def _runtime_cache_file(env: Mapping[str, str]) -> Path:
    return Path(str(env.get("SELF_HEALING_CACHE_FILE") or DEFAULT_RUNTIME_CACHE_FILE))


def _runtime_log_file(env: Mapping[str, str]) -> Path:
    return Path(str(env.get("SELF_HEALING_TARGET_LOG_FILE") or DEFAULT_RUNTIME_LOG_FILE))


def _log_self_healing(env: Mapping[str, str], event: str, **payload: Any) -> None:
    log_file = _self_healing_log_file(env)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts_msk": datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
        "event": str(event),
        **payload,
    }
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str))
        handle.write("\n")


def _probe_http_endpoint(
    url: str,
    *,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    headers: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    request = Request(
        str(url).strip(),
        headers={
            "User-Agent": HEALING_USER_AGENT,
            **dict(headers or {}),
        },
    )

    try:
        with urlopen(request, timeout=timeout_sec) as response:  # noqa: S310
            return {
                "ok": True,
                "status": "OK",
                "http_status": getattr(response, "status", 200),
            }
    except HTTPError as error:
        if int(error.code) < 500:
            return {
                "ok": True,
                "status": "OK",
                "http_status": int(error.code),
            }
        return {
            "ok": False,
            "status": "FAIL",
            "http_status": int(error.code),
            "error": str(error),
        }
    except URLError as error:
        return {"ok": False, "status": "FAIL", "error": str(error.reason or error)}
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "status": "FAIL", "error": str(error)}


def _run_command(command: list[str], *, timeout_sec: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        command,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_sec,
    )


def check_internet(env: Mapping[str, str]) -> dict[str, Any]:
    if _is_mock_mode(env):
        return {"ok": True, "status": "OK", "mode": MOCK_MODE}

    try:
        completed = _run_command(["ping", "-c", "1", "8.8.8.8"], timeout_sec=5)
    except Exception as error:  # noqa: BLE001
        _log_self_healing(env, "internet_check_error", error=str(error))
        return {"ok": False, "status": "FAIL", "error": str(error)}

    if completed.returncode == 0:
        return {"ok": True, "status": "OK"}

    error_text = (completed.stderr or completed.stdout or "ping failed").strip()
    _log_self_healing(env, "internet_check_failed", error=error_text)
    return {"ok": False, "status": "FAIL", "error": error_text}


def _warm_reload_telegram_handler() -> tuple[bool, str]:
    from cloudbot.bot.telegram.telegram_handler import handle_update

    original_mode = os.environ.get("SYSTEM_HEALTH_MODE")
    os.environ["SYSTEM_HEALTH_MODE"] = "mock"
    try:
        handle_update(
            {
                "message": {
                    "text": "/health",
                    "chat": {"id": 1},
                    "from": {"id": 1},
                }
            }
        )
    finally:
        if original_mode is None:
            os.environ.pop("SYSTEM_HEALTH_MODE", None)
        else:
            os.environ["SYSTEM_HEALTH_MODE"] = original_mode
    return True, "handler_warm_reload"


def _attempt_telegram_repair(env: Mapping[str, str]) -> list[str]:
    actions: list[str] = []

    try:
        ok, action = _warm_reload_telegram_handler()
        if ok:
            actions.append(action)
    except Exception as error:  # noqa: BLE001
        actions.append(f"handler_reload_failed: {error}")

    restart_cmd = str(env.get("SELF_HEALING_TELEGRAM_RESTART_CMD") or "").strip()
    allow_restart = str(env.get("SELF_HEALING_ALLOW_RESTART") or "0").strip() == "1"
    if not restart_cmd:
        actions.append("restart_not_configured")
        return actions

    if not allow_restart:
        actions.append("restart_disabled")
        return actions

    try:
        completed = _run_command(shlex.split(restart_cmd), timeout_sec=45)
    except Exception as error:  # noqa: BLE001
        actions.append(f"restart_failed: {error}")
        return actions

    if completed.returncode == 0:
        actions.append("restart_executed")
        return actions

    error_text = (completed.stderr or completed.stdout or "restart command failed").strip()
    actions.append(f"restart_failed: {error_text}")
    return actions


def check_telegram(env: Mapping[str, str]) -> dict[str, Any]:
    if _is_mock_mode(env):
        return {"ok": True, "status": "OK", "mode": MOCK_MODE, "actions": []}

    token = str(env.get("TELEGRAM_BOT_TOKEN") or "").strip()
    api_base = str(env.get("TELEGRAM_API_BASE_URL") or "https://api.telegram.org").strip()
    if not token:
        actions = _attempt_telegram_repair(env)
        _log_self_healing(
            env,
            "telegram_check_failed",
            error="TELEGRAM_BOT_TOKEN не задан",
            actions=actions,
        )
        return {
            "ok": False,
            "status": "FAIL",
            "error": "TELEGRAM_BOT_TOKEN не задан",
            "actions": actions,
        }

    endpoint = f"{api_base.rstrip('/')}/bot{token}/getMe"
    first_probe = _probe_http_endpoint(endpoint)
    if first_probe.get("ok"):
        return {"ok": True, "status": "OK", "actions": []}

    actions = _attempt_telegram_repair(env)
    second_probe = _probe_http_endpoint(endpoint)
    if second_probe.get("ok"):
        _log_self_healing(env, "telegram_recovered", actions=actions)
        return {
            "ok": True,
            "status": "OK",
            "actions": actions,
            "recovered": True,
        }

    error_text = str(second_probe.get("error") or first_probe.get("error") or "telegram api unavailable")
    _log_self_healing(
        env,
        "telegram_check_failed",
        error=error_text,
        actions=actions,
    )
    return {
        "ok": False,
        "status": "FAIL",
        "error": error_text,
        "actions": actions,
    }


def _ensure_empty_cache(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(EMPTY_CACHE_PAYLOAD, ensure_ascii=False, indent=2), encoding="utf-8")


def check_cache(env: Mapping[str, str]) -> dict[str, Any]:
    cache_file = _runtime_cache_file(env)
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    if not cache_file.exists():
        _ensure_empty_cache(cache_file)
        _log_self_healing(env, "cache_created", cache_file=str(cache_file))
        return {"ok": True, "status": "recreated", "actions": ["cache_created"]}

    try:
        raw_cache = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        if cache_file.exists():
            cache_file.unlink()
        _ensure_empty_cache(cache_file)
        _log_self_healing(
            env,
            "cache_recreated",
            cache_file=str(cache_file),
            error=str(error),
        )
        return {
            "ok": True,
            "status": "recreated",
            "actions": ["cache_recreated"],
            "warning": str(error),
        }

    if not isinstance(raw_cache, dict) or not isinstance(raw_cache.get("entries"), dict):
        if cache_file.exists():
            cache_file.unlink()
        _ensure_empty_cache(cache_file)
        _log_self_healing(
            env,
            "cache_recreated",
            cache_file=str(cache_file),
            error="Некорректная структура JSON кеша",
        )
        return {
            "ok": True,
            "status": "recreated",
            "actions": ["cache_recreated"],
            "warning": "Некорректная структура JSON кеша",
        }

    return {"ok": True, "status": "OK", "actions": []}


def check_logs(env: Mapping[str, str]) -> dict[str, Any]:
    log_file = _runtime_log_file(env)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if not log_file.exists():
        log_file.write_text("", encoding="utf-8")
        _log_self_healing(env, "runtime_log_created", log_file=str(log_file))
        return {"ok": True, "status": "created", "actions": ["log_created"]}

    rotate_limit = int(str(env.get("SELF_HEALING_LOG_ROTATE_BYTES") or MAX_TARGET_LOG_SIZE_BYTES))
    size_bytes = log_file.stat().st_size
    if size_bytes <= rotate_limit:
        return {"ok": True, "status": "OK", "size_bytes": size_bytes, "actions": []}

    rotated_path = log_file.with_name(f"{log_file.name}.1")
    if rotated_path.exists():
        archive_path = log_file.with_name(f"{log_file.name}.2")
        rotated_path.replace(archive_path)
    log_file.replace(rotated_path)
    log_file.write_text("", encoding="utf-8")
    _log_self_healing(
        env,
        "runtime_log_rotated",
        log_file=str(log_file),
        rotated_to=str(rotated_path),
        previous_size_bytes=size_bytes,
    )
    return {
        "ok": True,
        "status": "rotated",
        "size_bytes": size_bytes,
        "actions": [f"rotated:{rotated_path.name}"],
    }


def format_self_healing_report(
    *,
    checks: Mapping[str, Mapping[str, Any]],
    warnings: list[str],
    actions: list[str],
) -> str:
    lines = [
        "SELF HEALING REPORT",
        "",
        f"Internet: {checks['internet']['status']}",
        f"Telegram API: {checks['telegram_api']['status']}",
        f"Runtime cache: {checks['cache']['status']}",
        f"Runtime logs: {checks['logs']['status']}",
    ]

    if warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in warnings:
            lines.append(f"- {warning}")

    if actions:
        lines.append("")
        lines.append("Actions:")
        for action in actions:
            lines.append(f"- {action}")

    return "\n".join(lines)


def run_self_healing(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    env_data = _env_dict(env)

    checks = {
        "internet": check_internet(env_data),
        "telegram_api": check_telegram(env_data),
        "cache": check_cache(env_data),
        "logs": check_logs(env_data),
    }

    warnings: list[str] = []
    actions: list[str] = []
    for check_name, payload in checks.items():
        warning = payload.get("warning")
        if warning:
            warnings.append(f"{check_name}: {warning}")
        warnings.extend(str(item) for item in payload.get("warnings") or [])
        actions.extend(str(item) for item in payload.get("actions") or [])

    ok = all(bool(payload.get("ok")) for payload in checks.values())
    report_text = format_self_healing_report(checks=checks, warnings=warnings, actions=actions)

    _log_self_healing(
        env_data,
        "self_healing_run",
        ok=ok,
        checks={name: payload.get("status") for name, payload in checks.items()},
        warnings=warnings,
        actions=actions,
    )

    return {
        "ok": ok,
        "checks": checks,
        "warnings": warnings,
        "actions": actions,
        "text": report_text,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Self-healing Cloudbot")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_self_healing()
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, default=str))
    else:
        print(result["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
