"""Системный health-check Cloudbot для команды /health."""

from __future__ import annotations

from datetime import datetime
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from apps.larisa_ivanovna.agent import build_larisa_agent_from_env
from cloudbot.bot.telegram.commands import COMMAND_ALIASES
from cloudbot.providers.bitrix.bitrix_app_auth import BitrixAppAuth
from cloudbot.orchestrator.router import COMMAND_ROUTES
from cloudbot.providers.bitrix.bitrix_sales_adapter import BitrixSalesAdapter
from cloudbot.providers.search_provider import healthcheck as search_provider_healthcheck
from cloudbot.providers.wazzup_provider import WazzupProvider
from cloudbot.skills.web_search import run as web_search_skill_run

DEFAULT_TIMEOUT_SEC = 8
HEALTH_USER_AGENT = "CloudbotSystemHealth/1.0 (+https://cloudbot.local)"
MOCK_MODE = "mock"
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SYSTEM_HEALTH_LOG_FILE = REPO_ROOT / "logs" / "system_health.log"
TODOIST_TASKS_URL = "https://api.todoist.com/api/v1/tasks"
DEFAULT_REMOTE_OPS_ENV_FILE = Path.home() / ".config" / "openclo" / "assistant" / "happ-vpn.env"


def _env_dict(env: Mapping[str, str] | None = None) -> dict[str, str]:
    if env is None:
        return dict(os.environ)
    return {str(key): str(value) for key, value in env.items()}


def _health_log_file(env: Mapping[str, str]) -> Path:
    return Path(str(env.get("SYSTEM_HEALTH_LOG_FILE") or DEFAULT_SYSTEM_HEALTH_LOG_FILE))


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _merged_remote_ops_env(env: Mapping[str, str]) -> dict[str, str]:
    merged = _parse_env_file(DEFAULT_REMOTE_OPS_ENV_FILE)
    merged.update({str(key): str(value) for key, value in env.items()})
    return merged


def _append_health_log(env: Mapping[str, str], **payload: Any) -> None:
    log_file = _health_log_file(env)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts_msk": datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
        **payload,
    }
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str))
        handle.write("\n")


def _status_payload(
    *,
    ok: bool,
    status: str,
    message: str,
    reason: str = "",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "ok": ok,
        "status": status,
        "message": message,
    }
    if reason:
        payload["reason"] = reason
    if details:
        payload["details"] = details
    return payload


def _ok(message: str = "OK", **details: Any) -> dict[str, Any]:
    return _status_payload(ok=True, status="ok", message=message, details=details or None)


def _degraded(message: str, reason: str = "", **details: Any) -> dict[str, Any]:
    return _status_payload(ok=False, status="degraded", message=message, reason=reason, details=details or None)


def _fail(message: str, reason: str = "", **details: Any) -> dict[str, Any]:
    return _status_payload(ok=False, status="fail", message=message, reason=reason, details=details or None)


def _not_configured(message: str, reason: str = "", **details: Any) -> dict[str, Any]:
    return _status_payload(ok=False, status="not_configured", message=message, reason=reason, details=details or None)


def _not_checked(message: str, reason: str = "", **details: Any) -> dict[str, Any]:
    return _status_payload(ok=False, status="not_checked", message=message, reason=reason, details=details or None)


def _is_local_resolution_error(raw_reason: Any) -> bool:
    reason = str(raw_reason or "").strip().lower()
    return any(
        marker in reason
        for marker in (
            "nodename nor servname provided",
            "name or service not known",
            "temporary failure in name resolution",
            "operation not permitted",
        )
    )


def _mock_health_payload() -> dict[str, Any]:
    host = {
        "os": "MockOS 1.0",
        "uptime": "12д 4ч",
        "python": platform.python_version(),
        "free_disk_gb": "54.57 GB",
        "free_ram_gb": "6.40 GB",
    }
    platform_checks = {
        "gateway_reachable": _not_checked("not checked", "mock-режим не ходит в live OpenClaw gateway"),
        "gateway_probe": _not_checked("not checked", "mock-режим не выполняет gateway probe"),
        "deep_diagnostics": _not_checked("not checked", "mock-режим не выполняет deep diagnostics"),
        "cron_api": _not_checked("not checked", "mock-режим не читает live cron API"),
        "delivery_path": _not_checked("not checked", "mock-режим не проверяет live delivery path"),
        "openclaw_version": "mock-2026.04.12",
        "openclaw_update": "n/a",
        "consecutive_errors": "0",
    }
    integrations = {
        "Telegram": _ok("OK"),
        "OpenAI": _ok("OK"),
        "Bitrix portal": _ok("OK"),
        "Bitrix OAuth": _ok("OK"),
        "Todoist": _not_checked("not checked", "в mock-режиме live Todoist probe не выполняется"),
        "WHOOP": _not_checked("not checked", "в mock-режиме live WHOOP probe не выполняется"),
        "WAZZUP": _not_checked("not checked", "в mock-режиме live WAZZUP probe не выполняется"),
        "WAZZUP_WEBHOOK_FORWARD": _not_checked("not checked", "в mock-режиме live webhook probe не выполняется"),
        "WEBHOOK": _not_checked("not checked", "в mock-режиме live webhook probe не выполняется"),
        "Web Search provider": _ok("OK (mock server runtime)"),
        "web_search skill": _ok("OK"),
    }
    capabilities = {
        "Дневной бриф": _ok("OK"),
        "Задачи": _ok("OK"),
        "Встречи": _ok("OK"),
        "Погода": _ok("OK"),
        "Web search для Ларисы": _ok("OK"),
    }
    scheduler = {
        "healthcheck-daily": _not_checked("not checked", "локальный /health не читает live OpenClaw cron state"),
        "daily-status-report": _not_checked("not checked", "локальный /health не читает live OpenClaw cron state"),
        "Обязательные cron-задачи": _not_checked("not checked", "локальный /health не читает live cron state"),
        "Последняя доставка отчётов": _not_checked("not checked", "локальный /health не читает live delivery state"),
        "Trigger-уведомления": _not_checked("not checked", "локальный /health не читает live trigger state"),
    }
    security = {
        "UFW": _not_checked("not checked", "mock-режим не читает live host firewall state"),
        "Fail2ban": _not_checked("not checked", "mock-режим не читает live fail2ban state"),
        "Security updates": _not_checked("not checked", "mock-режим не читает live host update state"),
        "Trust model": _not_checked("not checked", "mock-режим не читает live OpenClaw trust model"),
    }
    observations = [
        "Web Search provider в mock-режиме эмулируется без live server inspect.",
    ]
    active_problems: list[str] = []
    score = 100
    return {
        "ok": True,
        "host": host,
        "platform": platform_checks,
        "integrations": integrations,
        "capabilities": capabilities,
        "scheduler": scheduler,
        "security": security,
        "observations": observations,
        "active_problems": active_problems,
        "new_apis": [],
        "score": score,
        "warnings": observations,
        "text": format_system_health_report(
            ok=True,
            host=host,
            platform_checks=platform_checks,
            integrations=integrations,
            capabilities=capabilities,
            scheduler=scheduler,
            security=security,
            observations=observations,
            active_problems=active_problems,
            new_apis=[],
            score=score,
        ),
    }


def _probe_http_endpoint(
    url: str,
    *,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    headers: Mapping[str, str] | None = None,
    accepted_status_codes: set[int] | None = None,
) -> dict[str, Any]:
    request = Request(
        str(url).strip(),
        headers={
            "User-Agent": HEALTH_USER_AGENT,
            **dict(headers or {}),
        },
    )
    accepted = accepted_status_codes or {200, 201, 202, 204}

    try:
        with urlopen(request, timeout=timeout_sec) as response:  # noqa: S310
            status_code = int(getattr(response, "status", 200))
            if status_code in accepted:
                return _ok(f"OK (HTTP {status_code})", http_status=status_code)
            return _degraded(
                f"degraded (HTTP {status_code})",
                f"endpoint ответил кодом {status_code}, что не входит в ожидаемый набор",
                http_status=status_code,
            )
    except HTTPError as error:
        status_code = int(error.code)
        if status_code in accepted:
            return _ok(f"OK (HTTP {status_code})", http_status=status_code)
        if status_code in {401, 403, 404, 429}:
            return _degraded(
                f"degraded (HTTP {status_code})",
                str(error),
                http_status=status_code,
            )
        return _fail(
            f"fail (HTTP {status_code})",
            str(error),
            http_status=status_code,
        )
    except URLError as error:
        return _fail("fail", str(error.reason or error))
    except Exception as error:  # noqa: BLE001
        return _fail("fail", str(error))


def _run_remote_readonly(env: Mapping[str, str], remote_command: str) -> tuple[bool, str]:
    ops_env = _merged_remote_ops_env(env)
    host = str(ops_env.get("PRIMARY_HOST") or ops_env.get("OPENCLAW_HOST") or "").strip()
    ssh_user = str(ops_env.get("SSH_USER") or "").strip()
    ssh_key_path = str(ops_env.get("SSH_KEY_PATH") or "").strip()
    ssh_port = str(ops_env.get("SSH_PORT") or "22").strip() or "22"
    if not host or not ssh_user or not ssh_key_path:
        return False, "remote-ops env не настроен для SSH inspect"
    command = [
        "ssh",
        "-i",
        ssh_key_path,
        "-p",
        ssh_port,
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=8",
        f"{ssh_user}@{host}",
        remote_command,
    ]
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=12,
        )
    except Exception as error:  # noqa: BLE001
        return False, str(error)
    if completed.returncode != 0:
        return False, (completed.stderr or completed.stdout or f"ssh rc={completed.returncode}").strip()
    return True, completed.stdout.strip()


def _remote_env_snapshot(
    env: Mapping[str, str],
    *,
    env_files: tuple[str, ...],
    keys: tuple[str, ...],
) -> dict[str, str] | None:
    files_literal = ", ".join(repr(path) for path in env_files)
    keys_literal = ", ".join(repr(key) for key in keys)
    remote_command = (
        "python3 - <<'PY'\n"
        "import json\n"
        "from pathlib import Path\n"
        f"env_files = [{files_literal}]\n"
        f"keys = [{keys_literal}]\n"
        "vals = {key: '' for key in keys}\n"
        "for candidate in env_files:\n"
        "    path = Path(candidate)\n"
        "    if not path.exists():\n"
        "        continue\n"
        "    for raw in path.read_text(encoding='utf-8').splitlines():\n"
        "        line = raw.strip()\n"
        "        if not line or line.startswith('#') or '=' not in raw:\n"
        "            continue\n"
        "        key, value = raw.split('=', 1)\n"
        "        key = key.strip()\n"
        "        if key in vals and not vals[key]:\n"
        "            vals[key] = value.strip()\n"
        "print(json.dumps(vals, ensure_ascii=False))\n"
        "PY"
    )
    ok, output = _run_remote_readonly(env, remote_command)
    if not ok:
        return None
    try:
        parsed = json.loads(output.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return {str(key): str(value or "").strip() for key, value in parsed.items()}


def _remote_search_runtime_snapshot(env: Mapping[str, str]) -> dict[str, str] | None:
    remote_command = (
        "python3 - <<'PY'\n"
        "import json\n"
        "from pathlib import Path\n"
        "cfg = json.loads(Path('/root/.openclaw/openclaw.json').read_text(encoding='utf-8'))\n"
        "search = (((cfg.get('tools') or {}).get('web') or {}).get('search') or {})\n"
        "duck = search.get('duckduckgo') or {}\n"
        "print(json.dumps({\n"
        "  'provider': search.get('provider') or '',\n"
        "  'base_url': duck.get('baseUrl') or duck.get('base_url') or '',\n"
        "  'engine': duck.get('engine') or '',\n"
        "  'image': '',\n"
        "}, ensure_ascii=False))\n"
        "PY\n"
        "printf '\\n__ENV__\\n'\n"
        "grep -E '^OPENCLAW_IMAGE=' /opt/openclaw/.env 2>/dev/null || true"
    )
    ok, output = _run_remote_readonly(env, remote_command)
    if not ok:
        return None
    payload, _, env_tail = output.partition("__ENV__")
    try:
        snapshot = json.loads(payload.strip())
    except json.JSONDecodeError:
        return None
    for line in env_tail.splitlines():
        if line.startswith("OPENCLAW_IMAGE="):
            snapshot["image"] = line.split("=", 1)[1].strip()
            break
    return {str(key): str(value or "").strip() for key, value in snapshot.items()}


def _remote_wazzup_runtime_snapshot(env: Mapping[str, str]) -> dict[str, str] | None:
    snapshot = _remote_env_snapshot(
        env,
        env_files=("/opt/openclaw/.env",),
        keys=("WAZZUP_API_KEY", "WAZZUP_API_BASE_URL", "WAZZUP_WEBHOOK_FORWARD_URL", "BITRIX_WEBHOOK_URL"),
    )
    if snapshot is None:
        return None
    return {
        "api_key_present": "1" if snapshot.get("WAZZUP_API_KEY") else "0",
        "api_base_url": snapshot.get("WAZZUP_API_BASE_URL", ""),
        "webhook_forward_url": snapshot.get("WAZZUP_WEBHOOK_FORWARD_URL", ""),
        "bitrix_webhook_url": snapshot.get("BITRIX_WEBHOOK_URL", ""),
    }


def _remote_whoop_runtime_snapshot(env: Mapping[str, str]) -> dict[str, str] | None:
    return _remote_env_snapshot(
        env,
        env_files=("/etc/openclaw/whoop.env", "/opt/openclaw/.env"),
        keys=(
            "WHOOP_TOKEN",
            "WHOOP_API_KEY",
            "WHOOP_CLIENT_ID",
            "WHOOP_CLIENT_SECRET",
            "WHOOP_REFRESH_TOKEN",
            "WHOOP_REDIRECT_URI",
        ),
    )


def _remote_bitrix_oauth_snapshot(env: Mapping[str, str]) -> dict[str, str] | None:
    remote_command = (
        "python3 - <<'PY'\n"
        "import json\n"
        "from pathlib import Path\n"
        "state_dir = Path('/opt/openclaw/state/bitrix_app')\n"
        "candidates = []\n"
        "for name in ('handler.latest.json', 'install.latest.json'):\n"
        "    path = state_dir / name\n"
        "    if not path.exists():\n"
        "        continue\n"
        "    try:\n"
        "        record = json.loads(path.read_text(encoding='utf-8'))\n"
        "    except Exception:\n"
        "        continue\n"
        "    payload = record.get('payload') if isinstance(record, dict) else None\n"
        "    if not isinstance(payload, dict):\n"
        "        continue\n"
        "    access_token = str(payload.get('AUTH_ID') or payload.get('auth_id') or payload.get('access_token') or payload.get('auth[access_token]') or '').strip()\n"
        "    client_endpoint = str(payload.get('client_endpoint') or payload.get('CLIENT_ENDPOINT') or payload.get('auth[client_endpoint]') or '').strip()\n"
        "    if not access_token or not client_endpoint:\n"
        "        continue\n"
        "    candidates.append({\n"
        "        'path': str(path),\n"
        "        'saved_at': str(record.get('saved_at') or ''),\n"
        "        'domain': str(payload.get('DOMAIN') or payload.get('domain') or payload.get('auth[domain]') or '').strip(),\n"
        "        'member_id': str(payload.get('member_id') or payload.get('MEMBER_ID') or payload.get('auth[member_id]') or '').strip(),\n"
        "        'status': str(payload.get('status') or payload.get('STATUS') or payload.get('auth[status]') or '').strip(),\n"
        "    })\n"
        "if not candidates:\n"
        "    print('{}')\n"
        "else:\n"
        "    candidates.sort(key=lambda item: item.get('saved_at') or '', reverse=True)\n"
        "    print(json.dumps(candidates[0], ensure_ascii=False))\n"
        "PY"
    )
    ok, output = _run_remote_readonly(env, remote_command)
    if not ok:
        return None
    try:
        parsed = json.loads(output.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or not parsed:
        return None
    return {str(key): str(value or "").strip() for key, value in parsed.items()}


def _remote_todo_runtime_snapshot(env: Mapping[str, str]) -> dict[str, str] | None:
    remote_command = (
        "python3 - <<'PY'\n"
        "import json\n"
        "from pathlib import Path\n"
        "env_files = [Path('/root/.openclaw/workspace/todo-integration/.env.runtime'), Path('/etc/openclaw/todo.env')]\n"
        "vals = {}\n"
        "for path in env_files:\n"
        "    if not path.exists():\n"
        "        continue\n"
        "    for raw in path.read_text(encoding='utf-8').splitlines():\n"
        "        line = raw.strip()\n"
        "        if not line or line.startswith('#') or '=' not in raw:\n"
        "            continue\n"
        "        key, value = raw.split('=', 1)\n"
        "        key = key.strip()\n"
        "        if key in {'TODO_TOKEN', 'LARISA_TODO_TOKEN', 'TODO_STATE_DIR'} and key not in vals:\n"
        "            vals[key] = value.strip()\n"
        "state_dir = vals.get('TODO_STATE_DIR') or '/home/node/.openclaw/todo-integration-data'\n"
        "host_state_dir = state_dir\n"
        "if host_state_dir.startswith('/home/node/.openclaw/'):\n"
        "    host_state_dir = '/root' + host_state_dir[len('/home/node'):]\n"
        "snapshot = Path(host_state_dir) / 'tasks_snapshot.json'\n"
        "generated_at = ''\n"
        "if snapshot.exists():\n"
        "    try:\n"
        "        payload = json.loads(snapshot.read_text(encoding='utf-8'))\n"
        "        if isinstance(payload, dict):\n"
        "            generated_at = str(payload.get('generatedAt') or '').strip()\n"
        "    except Exception:\n"
        "        generated_at = ''\n"
        "print(json.dumps({\n"
        "  'token_present': '1' if (vals.get('TODO_TOKEN') or vals.get('LARISA_TODO_TOKEN')) else '0',\n"
        "  'state_dir': state_dir,\n"
        "  'snapshot_present': '1' if snapshot.exists() else '0',\n"
        "  'snapshot_generated_at': generated_at,\n"
        "}, ensure_ascii=False))\n"
        "PY"
    )
    ok, output = _run_remote_readonly(env, remote_command)
    if not ok:
        return None
    try:
        parsed = json.loads(output.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return {str(key): str(value or "").strip() for key, value in parsed.items()}


def _remote_google_calendar_runtime_snapshot(env: Mapping[str, str]) -> dict[str, str] | None:
    remote_command = (
        "python3 - <<'PY'\n"
        "import json\n"
        "from pathlib import Path\n"
        "candidates = [\n"
        "  Path('/root/.openclaw/workspace/todo-integration/src/agenda/providers/googleCalendar.mjs'),\n"
        "  Path('/home/node/.openclaw/workspace/todo-integration/src/agenda/providers/googleCalendar.mjs'),\n"
        "]\n"
        "found = next((path for path in candidates if path.exists()), None)\n"
        "if found is None:\n"
        "    print('{}')\n"
        "else:\n"
        "    print(json.dumps({'provider_path': str(found), 'runtime': 'legacy_todo_integration'}, ensure_ascii=False))\n"
        "PY"
    )
    ok, output = _run_remote_readonly(env, remote_command)
    if not ok:
        return None
    try:
        parsed = json.loads(output.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or not parsed:
        return None
    return {str(key): str(value or "").strip() for key, value in parsed.items()}


def _format_seconds_as_uptime(seconds: float) -> str:
    total = max(int(seconds), 0)
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}д")
    if days or hours:
        parts.append(f"{hours}ч")
    parts.append(f"{minutes}м")
    return " ".join(parts)


def _read_uptime() -> str:
    try:
        raw = Path("/proc/uptime").read_text(encoding="utf-8").split()[0]
        return _format_seconds_as_uptime(float(raw))
    except Exception:  # noqa: BLE001
        return "not checked"


def _read_free_ram_gb() -> str:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                kb = int(line.split()[1])
                return f"{kb / 1024 / 1024:.2f} GB"
    except Exception:  # noqa: BLE001
        pass
    return "not checked"


def _read_free_disk_gb(path: Path) -> str:
    try:
        usage = shutil.disk_usage(path)
        return f"{usage.free / 1024 / 1024 / 1024:.2f} GB"
    except Exception:  # noqa: BLE001
        return "not checked"


def _build_host_snapshot() -> dict[str, str]:
    return {
        "os": platform.platform(),
        "uptime": _read_uptime(),
        "python": platform.python_version(),
        "free_disk_gb": _read_free_disk_gb(REPO_ROOT),
        "free_ram_gb": _read_free_ram_gb(),
    }


def _check_telegram_api(env: Mapping[str, str]) -> dict[str, Any]:
    api_base = str(env.get("TELEGRAM_API_BASE_URL") or "https://api.telegram.org").strip()
    return _probe_http_endpoint(api_base)


def _check_openai_api(env: Mapping[str, str]) -> dict[str, Any]:
    api_base = str(env.get("OPENAI_API_BASE_URL") or "https://api.openai.com/v1/models").strip()
    headers: dict[str, str] = {}
    api_key = str(env.get("OPENAI_API_KEY") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return _probe_http_endpoint(api_base, headers=headers, accepted_status_codes={200})


def _check_bitrix_api(env: Mapping[str, str]) -> dict[str, Any]:
    adapter = BitrixSalesAdapter.from_env(env)
    if not adapter.is_configured():
        return _not_configured("not configured", "Bitrix не настроен")

    access = {item["key"]: item for item in adapter.check_access()}
    profile = access.get("profile") or {}
    deals = access.get("deals") or {}

    if profile.get("ok") and deals.get("ok"):
        return _ok("OK")

    failed = profile if not profile.get("ok") else deals
    return _fail(
        "fail",
        str(failed.get("message") or failed.get("status") or "Bitrix check failed"),
    )


def _check_todoist_api(env: Mapping[str, str]) -> dict[str, Any]:
    token = str(
        env.get("LARISA_TODO_TOKEN")
        or env.get("TODO_TOKEN")
        or env.get("TODOIST_TOKEN")
        or env.get("TODOIST_API_TOKEN")
        or ""
    ).strip()
    if not token:
        remote = _remote_todo_runtime_snapshot(env)
        if remote and (remote.get("token_present") == "1" or remote.get("snapshot_present") == "1"):
            return _not_checked(
                "not checked",
                "Todoist server runtime подтверждён через todo-integration; локальный /health не использует server-side token напрямую",
                state_dir=remote.get("state_dir") or "-",
                snapshot_present=remote.get("snapshot_present") or "0",
                snapshot_generated_at=remote.get("snapshot_generated_at") or "-",
            )
        return _not_configured("not configured", "TODO token не задан")
    return _probe_http_endpoint(
        TODOIST_TASKS_URL,
        headers={"Authorization": f"Bearer {token}"},
        accepted_status_codes={200},
    )


def _check_known_endpoint(
    env: Mapping[str, str],
    *,
    env_name: str,
    label: str,
    remote_runtime_url: str = "",
    remote_runtime_label: str = "server runtime",
) -> dict[str, Any]:
    raw = str(env.get(env_name) or "").strip()
    if not raw:
        if remote_runtime_url:
            return _ok(f"OK ({remote_runtime_label})", endpoint=remote_runtime_url)
        return _not_configured("not configured", f"{label} не задан в ENV")
    probe = _probe_http_endpoint(raw)
    if probe.get("status") == "fail" and _is_local_resolution_error(probe.get("reason")):
        return _not_checked(
            "not checked",
            f"{label} задан, но локальный /health не может подтвердить endpoint из-за сетевых ограничений текущего контура",
        )
    return probe


def _check_whoop_api(env: Mapping[str, str]) -> dict[str, Any]:
    token = str(env.get("WHOOP_TOKEN") or env.get("WHOOP_API_KEY") or "").strip()
    oauth_client_id = str(env.get("WHOOP_CLIENT_ID") or "").strip()
    oauth_client_secret = str(env.get("WHOOP_CLIENT_SECRET") or "").strip()
    oauth_refresh_token = str(env.get("WHOOP_REFRESH_TOKEN") or "").strip()
    remote = _remote_whoop_runtime_snapshot(env) if not token and not (oauth_client_id and oauth_client_secret and oauth_refresh_token) else None
    remote_token = str((remote or {}).get("WHOOP_TOKEN") or (remote or {}).get("WHOOP_API_KEY") or "").strip()
    remote_oauth_client_id = str((remote or {}).get("WHOOP_CLIENT_ID") or "").strip()
    remote_oauth_client_secret = str((remote or {}).get("WHOOP_CLIENT_SECRET") or "").strip()
    remote_oauth_refresh_token = str((remote or {}).get("WHOOP_REFRESH_TOKEN") or "").strip()
    if not token and not (oauth_client_id and oauth_client_secret and oauth_refresh_token):
        if remote_oauth_client_id and remote_oauth_client_secret and remote_oauth_refresh_token:
            return _not_checked(
                "not checked",
                "WHOOP server-only OAuth-контур настроен; локальный /health не содержит канонического live-probe WHOOP API и пока не валидирует refresh-flow",
            )
        if remote_token:
            return _not_checked(
                "not checked",
                "WHOOP server-only контур настроен; локальный /health не содержит канонического live-probe WHOOP API",
            )
        return _not_configured("not configured", "WHOOP token/API key не задан")
    if oauth_client_id and oauth_client_secret and oauth_refresh_token:
        return _not_checked(
            "not checked",
            "WHOOP OAuth-контур настроен; локальный /health не содержит канонического live-probe WHOOP API и пока не валидирует refresh-flow",
        )
    return _not_checked(
        "not checked",
        "локальный /health не содержит канонического live-probe WHOOP API; нужен отдельный smoke report contour",
    )


def _check_bitrix_oauth(env: Mapping[str, str], bitrix_payload: dict[str, Any]) -> dict[str, Any]:
    if bitrix_payload.get("status") == "ok":
        return _not_checked("not checked", "отдельный локальный OAuth-probe Bitrix в /health не реализован")

    try:
        local_summary = BitrixAppAuth.from_env(env).summary()
    except Exception:  # noqa: BLE001
        local_summary = {"ok": False}
    if bool(local_summary.get("ok")):
        return _not_checked(
            "not checked",
            "Bitrix app OAuth state найден в локальном контуре; отдельный live OAuth-probe в /health не реализован",
        )

    remote = _remote_bitrix_oauth_snapshot(env)
    if remote:
        return _not_checked(
            "not checked",
            "Bitrix app OAuth state подтверждён в server runtime; отдельный live OAuth-probe в /health не реализован",
            path=remote.get("path") or "-",
            saved_at=remote.get("saved_at") or "-",
            domain=remote.get("domain") or "-",
            member_id=remote.get("member_id") or "-",
            oauth_status=remote.get("status") or "-",
        )

    return _not_configured("not configured", "Bitrix OAuth state не подтверждён ни локально, ни в server runtime")


def _check_google_calendar_oauth(env: Mapping[str, str]) -> dict[str, Any]:
    remote = _remote_google_calendar_runtime_snapshot(env)
    if remote:
        return _not_checked(
            "not checked",
            "Google Calendar OAuth контур найден в server runtime; отдельный state/probe path в текущем /health не реализован",
            provider_path=remote.get("provider_path") or "-",
            runtime=remote.get("runtime") or "-",
        )
    return _not_configured("not configured", "Google Calendar OAuth контур не подтверждён в текущем runtime registry")


def _check_wazzup_api(env: Mapping[str, str]) -> dict[str, Any]:
    status = WazzupProvider.from_env(env).get_api_status()
    raw_status = str(status.get("status") or "").strip().lower()
    message = str(status.get("message") or raw_status or "-")
    if bool(status.get("ok")):
        return _ok(message)
    if raw_status == "not_configured":
        remote = _remote_wazzup_runtime_snapshot(env)
        if remote and remote.get("api_key_present") == "1":
            return _ok(
                "OK (server runtime)",
                api_base_url=remote.get("api_base_url") or "-",
                webhook_forward_url=remote.get("webhook_forward_url") or "-",
            )
        return _not_configured("not configured", message)
    if _is_local_resolution_error(message):
        remote = _remote_wazzup_runtime_snapshot(env)
        if remote and remote.get("api_key_present") == "1":
            return _ok(
                "OK (server runtime)",
                api_base_url=remote.get("api_base_url") or "-",
                webhook_forward_url=remote.get("webhook_forward_url") or "-",
            )
        return _not_checked(
            "not checked",
            "WAZZUP env настроен, но локальный /health не может подтвердить live API из-за сетевых ограничений текущего контура",
        )
    return _fail("fail", message)


def _check_web_search_provider(env: Mapping[str, str]) -> dict[str, Any]:
    configured_provider = str(env.get("SEARCH_PROVIDER") or env.get("search_provider") or "").strip().lower()
    provider_config: dict[str, Any] = {"provider": configured_provider} if configured_provider else {}
    base_url = str(env.get("SEARCH_BASE_URL") or env.get("SEARXNG_BASE_URL") or "").strip()
    if base_url:
        provider_config["base_url"] = base_url
    engine = str(env.get("SEARCH_ENGINE") or env.get("SEARXNG_ENGINE") or "").strip().lower()
    if engine:
        provider_config["engine"] = engine
    timeout_seconds = str(env.get("SEARCH_TIMEOUT_SECONDS") or env.get("SEARXNG_TIMEOUT_SECONDS") or "").strip()
    if timeout_seconds:
        provider_config["timeout_seconds"] = timeout_seconds

    if not base_url:
        remote = _remote_search_runtime_snapshot(env)
        if remote and remote.get("provider"):
            return _ok(
                "OK (server runtime)",
                provider=remote.get("provider") or "-",
                base_url=remote.get("base_url") or "-",
                engine=remote.get("engine") or "-",
                image=remote.get("image") or "-",
            )
        effective_provider = configured_provider or "duckduckgo"
        return _not_checked(
            "not checked",
            f"provider={effective_provider}; локальный env не является каноническим source of truth для search runtime, нужен inspect server OpenClaw/openclaw.json",
        )

    provider_probe = search_provider_healthcheck(provider_config if provider_config else {})
    if not bool(provider_probe.get("ok")):
        return _fail("fail", str(provider_probe.get("error") or "search provider недоступен"))
    effective_provider = str(provider_probe.get("provider") or "duckduckgo").strip()
    warnings = [str(item).strip() for item in provider_probe.get("warnings") or [] if str(item).strip()]
    probe = provider_probe.get("probe") if isinstance(provider_probe.get("probe"), dict) else {}
    if probe:
        message = (
            f"provider={effective_provider}; backend={probe.get('base_url')}; "
            f"engine={probe.get('engine')}; result_count={probe.get('result_count')}"
        )
        if warnings:
            return _degraded("degraded", f"{message}; {'; '.join(warnings)}")
        return _ok(message)
    if warnings:
        return _degraded(
            "degraded",
            f"provider={effective_provider}; {'; '.join(warnings)}; конфигурационный probe проходит, но реальный search smoke в локальном /health не реализован",
        )
    if configured_provider:
        return _degraded(
            "degraded",
            f"provider={effective_provider}; конфигурационный probe проходит, но реальный search smoke в локальном /health не реализован",
        )
    return _degraded(
        "degraded",
        f"provider={effective_provider}; конфигурационный probe создаёт provider-объект, но не доказывает реальный web search и не должен считаться user-facing OK",
    )


def _check_web_search_skill(env: Mapping[str, str]) -> dict[str, Any]:
    configured_provider = str(env.get("SEARCH_PROVIDER") or env.get("search_provider") or "duckduckgo").strip().lower()
    try:
        result = web_search_skill_run(
            {"query": "healthcheck smoke", "limit": 1},
            providers={"search": {"provider": configured_provider or "duckduckgo"}},
        )
    except Exception as error:  # noqa: BLE001
        if _is_local_resolution_error(error):
            return _not_checked(
                "not checked",
                "локальный /health не может подтвердить web_search skill из-за сетевых ограничений текущего контура",
            )
        return _fail("fail", f"web_search skill вызвал исключение: {error}")
    if bool(result.get("ok")):
        return _ok("OK")
    if _is_local_resolution_error(result.get("error")):
        return _not_checked(
            "not checked",
            "локальный /health не может подтвердить web_search skill из-за сетевых ограничений текущего контура",
        )
    return _fail("fail", str(result.get("error") or "web_search skill недоступен"))


def _check_openclaw_gateway(env: Mapping[str, str]) -> dict[str, Any]:
    explicit_url = str(env.get("OPENCLAW_GATEWAY_HEALTH_URL") or env.get("OPENCLAW_GATEWAY_URL") or "").strip()
    if explicit_url:
        return _probe_http_endpoint(explicit_url)
    port = str(env.get("OPENCLAW_GATEWAY_PORT") or "").strip()
    if port:
        return _probe_http_endpoint(f"http://127.0.0.1:{port}")
    return _not_checked("not checked", "OPENCLAW_GATEWAY_HEALTH_URL или OPENCLAW_GATEWAY_URL не задан")


def _build_platform_snapshot(env: Mapping[str, str]) -> dict[str, Any]:
    gateway = _check_openclaw_gateway(env)
    return {
        "gateway_reachable": gateway,
        "gateway_probe": _not_checked("not checked", "локальный /health не выполняет канонический gateway probe OpenClaw"),
        "deep_diagnostics": _not_checked("not checked", "локальный /health не выполняет openclaw status --deep"),
        "cron_api": _not_checked("not checked", "локальный /health не читает live OpenClaw cron state"),
        "delivery_path": _not_checked("not checked", "локальный /health не читает live delivery path"),
        "openclaw_version": str(env.get("OPENCLAW_VERSION") or "not checked"),
        "openclaw_update": str(env.get("OPENCLAW_AVAILABLE_UPDATE") or "not checked"),
        "consecutive_errors": str(env.get("OPENCLAW_CONSECUTIVE_ERRORS") or "not checked"),
    }


def _check_security_snapshot(env: Mapping[str, str]) -> dict[str, Any]:
    return {
        "UFW": _not_checked("not checked", "локальный /health не читает live host firewall state"),
        "Fail2ban": _not_checked("not checked", "локальный /health не читает live fail2ban state"),
        "Security updates": _not_checked("not checked", "локальный /health не читает live host update state"),
        "Trust model": _degraded(
            "degraded" if str(env.get("OPENCLAW_MULTI_USER_HEURISTIC") or "").strip() else "not checked",
            str(env.get("OPENCLAW_MULTI_USER_HEURISTIC") or "локальный /health не читает live OpenClaw trust model"),
        ) if str(env.get("OPENCLAW_MULTI_USER_HEURISTIC") or "").strip() else _not_checked(
            "not checked",
            "локальный /health не читает live OpenClaw trust model",
        ),
    }


def _check_scheduler_snapshot() -> dict[str, Any]:
    return {
        "healthcheck-daily": _not_checked("not checked", "локальный /health не читает live OpenClaw cron state"),
        "daily-status-report": _not_checked("not checked", "локальный /health не читает live OpenClaw cron state"),
        "Обязательные cron-задачи": _not_checked("not checked", "локальный /health не читает live cron state"),
        "Последняя доставка отчётов": _not_checked("not checked", "локальный /health не читает live delivery state"),
        "Trigger-уведомления": _not_checked("not checked", "локальный /health не читает live trigger state"),
    }


def _capability_from_registry(
    *,
    router_commands: Mapping[str, str],
    alias_commands: Mapping[str, str],
    larisa_registry: Mapping[str, Any],
    route_aliases: tuple[str, ...],
    registry_command: str,
    missing_reason: str,
) -> dict[str, Any]:
    route_present = all(alias in router_commands for alias in route_aliases)
    alias_present = any(alias in alias_commands for alias in route_aliases)
    registry_present = registry_command in larisa_registry
    if route_present and alias_present and registry_present:
        return _ok("OK")
    return _not_configured("not configured", missing_reason)


def _build_capabilities_snapshot(env: Mapping[str, str]) -> dict[str, Any]:
    try:
        larisa_registry = build_larisa_agent_from_env(dict(env)).registry
    except Exception as error:  # noqa: BLE001
        return {
            "Дневной бриф": _degraded("degraded", f"не удалось собрать registry Ларисы: {error}"),
            "Задачи": _degraded("degraded", f"не удалось собрать registry Ларисы: {error}"),
            "Встречи": _degraded("degraded", f"не удалось собрать registry Ларисы: {error}"),
            "Погода": _degraded("degraded", f"не удалось собрать registry Ларисы: {error}"),
            "Web search для Ларисы": _not_configured(
                "not configured",
                "у Ларисы нет отдельного user-facing route/command для web search",
            ),
        }

    return {
        "Дневной бриф": _capability_from_registry(
            router_commands=COMMAND_ROUTES,
            alias_commands=COMMAND_ALIASES,
            larisa_registry=larisa_registry,
            route_aliases=("/today", "/brief", "/day"),
            registry_command="get_day_brief",
            missing_reason="неполный route/command path для day brief",
        ),
        "Задачи": _capability_from_registry(
            router_commands=COMMAND_ROUTES,
            alias_commands=COMMAND_ALIASES,
            larisa_registry=larisa_registry,
            route_aliases=("/tasks",),
            registry_command="get_tasks",
            missing_reason="неполный route/command path для задач",
        ),
        "Встречи": _capability_from_registry(
            router_commands=COMMAND_ROUTES,
            alias_commands=COMMAND_ALIASES,
            larisa_registry=larisa_registry,
            route_aliases=("/meetings",),
            registry_command="get_meetings",
            missing_reason="неполный route/command path для встреч",
        ),
        "Погода": _capability_from_registry(
            router_commands=COMMAND_ROUTES,
            alias_commands=COMMAND_ALIASES,
            larisa_registry=larisa_registry,
            route_aliases=("/weather",),
            registry_command="get_weather",
            missing_reason="неполный route/command path для погоды",
        ),
        "Web search для Ларисы": _capability_from_registry(
            router_commands=COMMAND_ROUTES,
            alias_commands=COMMAND_ALIASES,
            larisa_registry=larisa_registry,
            route_aliases=("/search", "/web", "/find"),
            registry_command="get_web_search",
            missing_reason="неполный route/command path для web search",
        ),
    }


def _build_integrations_snapshot(env: Mapping[str, str], bitrix_payload: dict[str, Any]) -> dict[str, Any]:
    remote_wazzup = _remote_wazzup_runtime_snapshot(env)
    bitrix_oauth = _check_bitrix_oauth(env, bitrix_payload)
    return {
        "Telegram": _check_telegram_api(env),
        "OpenAI": _check_openai_api(env),
        "Bitrix portal": bitrix_payload,
        "Bitrix OAuth": bitrix_oauth,
        "Todoist": _check_todoist_api(env),
        "WHOOP": _check_whoop_api(env),
        "WAZZUP": _check_wazzup_api(env),
        "WAZZUP_WEBHOOK_FORWARD": _check_known_endpoint(
            env,
            env_name="WAZZUP_WEBHOOK_FORWARD_URL",
            label="WAZZUP_WEBHOOK_FORWARD_URL",
            remote_runtime_url=str((remote_wazzup or {}).get("webhook_forward_url") or "").strip(),
        ),
        "WEBHOOK": _check_known_endpoint(
            env,
            env_name="BITRIX_WEBHOOK_URL",
            label="BITRIX_WEBHOOK_URL",
            remote_runtime_url=str((remote_wazzup or {}).get("bitrix_webhook_url") or "").strip(),
        ),
        "Google Calendar OAuth": _check_google_calendar_oauth(env),
        "Web Search provider": _check_web_search_provider(env),
        "web_search skill": _check_web_search_skill(env),
    }


def _load_new_apis(env: Mapping[str, str]) -> list[dict[str, Any]]:
    raw = str(env.get("SYSTEM_HEALTH_NEW_APIS") or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [{"name": "parse_error", "status": "fail", "message": "SYSTEM_HEALTH_NEW_APIS содержит невалидный JSON"}]
    if not isinstance(parsed, list):
        return [{"name": "parse_error", "status": "fail", "message": "SYSTEM_HEALTH_NEW_APIS должен быть JSON-массивом"}]
    result: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "name": str(item.get("name") or "unknown"),
                "status": str(item.get("status") or "not_checked"),
                "message": str(item.get("message") or "-"),
            }
        )
    return result


def _status_kind(payload: Mapping[str, Any]) -> str:
    return str(payload.get("status") or "").strip().lower()


def _status_word(payload: Mapping[str, Any]) -> str:
    mapping = {
        "ok": "Работает",
        "degraded": "Предупреждение",
        "fail": "Ошибка",
        "not_configured": "Не настроено",
        "not_checked": "Предупреждение",
    }
    raw = _status_kind(payload)
    return mapping.get(raw, raw or "-")


def _status_emoji(payload: Mapping[str, Any]) -> str:
    raw = _status_kind(payload)
    if raw == "ok":
        return "🟢"
    if raw in {"degraded", "not_checked"}:
        return "🟡"
    if raw == "not_configured":
        return "⚪"
    return "🔴"


def _collect_active_problems(
    platform_checks: Mapping[str, Any],
    integrations: Mapping[str, Mapping[str, Any]],
    capabilities: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    problems: list[str] = []
    for label, payload in (
        ("OpenClaw gateway", platform_checks["gateway_reachable"]),
        ("Telegram", integrations["Telegram"]),
        ("OpenAI", integrations["OpenAI"]),
        ("Bitrix portal", integrations["Bitrix portal"]),
    ):
        if str(payload.get("status") or "").strip().lower() == "fail":
            problems.append(f"{label}: {payload.get('reason') or payload.get('message') or 'fail'}")
    if str(capabilities["Web search для Ларисы"].get("status") or "").strip().lower() == "fail":
        problems.append(
            "Web search для Ларисы: "
            f"{capabilities['Web search для Ларисы'].get('reason') or capabilities['Web search для Ларисы'].get('message') or 'fail'}"
        )
    return problems


def _collect_observations(
    platform_checks: Mapping[str, Any],
    integrations: Mapping[str, Mapping[str, Any]],
    capabilities: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    observations: list[str] = []
    for label, payload in (
        ("Gateway probe", platform_checks["gateway_probe"]),
        ("Deep diagnostics", platform_checks["deep_diagnostics"]),
        ("Cron API", platform_checks["cron_api"]),
        ("Delivery path", platform_checks["delivery_path"]),
        ("Web Search provider", integrations["Web Search provider"]),
        ("Bitrix OAuth", integrations["Bitrix OAuth"]),
        ("Todoist", integrations["Todoist"]),
        ("WHOOP", integrations["WHOOP"]),
        ("WAZZUP_WEBHOOK_FORWARD", integrations["WAZZUP_WEBHOOK_FORWARD"]),
        ("WEBHOOK", integrations["WEBHOOK"]),
        ("Web search для Ларисы", capabilities["Web search для Ларисы"]),
    ):
        status = str(payload.get("status") or "").strip().lower()
        if status in {"degraded", "not_configured", "not_checked"}:
            observations.append(f"{label}: {payload.get('reason') or payload.get('message') or status}")
    return observations


def _health_score(active_problems: list[str]) -> int:
    if not active_problems:
        return 100
    return max(0, 100 - 25 * len(active_problems))


def _status_line(label: str, payload: Mapping[str, Any]) -> str:
    return f"{label} — {_status_emoji(payload)} {_status_word(payload)}"


def _status_reason(payload: Mapping[str, Any]) -> str:
    return str(payload.get("reason") or payload.get("message") or "").strip()


def _render_reason_lines(payload: Mapping[str, Any]) -> list[str]:
    reason = _status_reason(payload)
    if not reason or reason == "OK":
        return []
    return [f"Причина: {reason}"]


def _render_named_item(label: str, payload: Mapping[str, Any]) -> list[str]:
    lines = [f"• {_status_line(label, payload)}"]
    for reason_line in _render_reason_lines(payload):
        lines.append(f"  {reason_line}")
    return lines


def _count_statuses(*groups: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    counts = {"critical": 0, "warning": 0, "not_configured": 0}
    for group in groups:
        for payload in group.values():
            if not isinstance(payload, Mapping):
                continue
            kind = _status_kind(payload)
            if kind == "fail":
                counts["critical"] += 1
            elif kind == "degraded":
                counts["warning"] += 1
            elif kind == "not_configured":
                counts["not_configured"] += 1
    return counts


def _manager_summary(
    *,
    active_problems: list[str],
    counts: Mapping[str, int],
) -> list[str]:
    if active_problems:
        return [
            "Система работает с отклонениями.",
            f"Есть активные проблемы, требующие внимания: {len(active_problems)}.",
        ]
    if counts["warning"]:
        return [
            "Система работает штатно.",
            "Есть незначительные деградации и задачи на плановую донастройку.",
        ]
    if counts["not_configured"]:
        return [
            "Система работает штатно.",
            "Часть дополнительных контуров не настроена, но на стабильность ядра это не влияет.",
        ]
    return [
        "Система работает штатно.",
        "Критических проблем и существенных деградаций не выявлено.",
    ]


def _build_important_now(
    *,
    active_problems: list[str],
    capabilities: Mapping[str, Mapping[str, Any]],
    platform_checks: Mapping[str, Any],
) -> list[str]:
    items: list[str] = []
    if active_problems:
        items.append("Есть активные проблемы, требующие внимания.")
    else:
        items.append("Система работает стабильно.")

    if _status_kind(capabilities["Web search для Ларисы"]) != "ok":
        items.append("Web-поиск для Ларисы не работает.")

    update_value = str(platform_checks.get("openclaw_update") or "").strip().lower()
    if update_value and update_value not in {"not checked", "-", "n/a"}:
        items.append("Доступно обновление OpenClaw.")

    if _status_kind(platform_checks["deep_diagnostics"]) != "ok":
        items.append("Ограничена глубокая диагностика.")

    return items[:4]


def _read_health_log_records(env: Mapping[str, str]) -> list[dict[str, Any]]:
    log_file = _health_log_file(env)
    if not log_file.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        with log_file.open(encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    records.append(item)
    except Exception:  # noqa: BLE001
        return []
    return records


def _changes_last_24h(
    env: Mapping[str, str],
    *,
    score: int,
    active_problems: list[str],
    observations: list[str],
) -> dict[str, Any] | None:
    records = _read_health_log_records(env)
    if not records:
        return None

    now = datetime.now(MOSCOW_TZ)
    day_records: list[dict[str, Any]] = []
    for item in records:
        raw_ts = str(item.get("ts_msk") or "").strip()
        if not raw_ts:
            continue
        try:
            ts = datetime.fromisoformat(raw_ts)
        except ValueError:
            continue
        if (now - ts).total_seconds() <= 86400:
            day_records.append(item)

    if not day_records:
        return None

    previous = day_records[-1]
    prev_active = list(previous.get("active_problems") or [])
    prev_observations = list(previous.get("observations") or [])
    prev_score = int(previous.get("score") or score)
    return {
        "new_errors": max(len(active_problems) - len(prev_active), 0),
        "new_warnings": max(len(observations) - len(prev_observations), 0),
        "fixed": len(set(prev_active) - set(active_problems)),
        "prev_score": prev_score,
        "score": score,
    }


def _render_section_header(title: str) -> list[str]:
    return ["", f"<b>{title}</b>"]


def format_system_health_report(
    *,
    ok: bool,
    host: Mapping[str, Any],
    platform_checks: Mapping[str, Any],
    integrations: Mapping[str, Mapping[str, Any]],
    capabilities: Mapping[str, Mapping[str, Any]],
    scheduler: Mapping[str, Mapping[str, Any]],
    security: Mapping[str, Mapping[str, Any]],
    observations: list[str],
    active_problems: list[str],
    new_apis: list[dict[str, Any]],
    score: int,
    changes_24h: Mapping[str, Any] | None = None,
) -> str:
    now_msk = datetime.now(MOSCOW_TZ).strftime("%d.%m.%Y %H:%M МСК")
    counts = _count_statuses(platform_checks, integrations, capabilities, scheduler, security)
    summary_lines = _manager_summary(active_problems=active_problems, counts=counts)
    important_now = _build_important_now(
        active_problems=active_problems,
        capabilities=capabilities,
        platform_checks=platform_checks,
    )

    lines = ["<b>🟢 Статус системы</b>" if ok else "<b>🔴 Статус системы</b>"]
    lines.append(f"📊 <b>Индекс здоровья:</b> {score}/100")
    lines.append(f"🚨 <b>Критических проблем:</b> {len(active_problems)}")
    lines.append(f"⚠️ <b>Предупреждений:</b> {counts['warning']}")
    lines.append(f"⚪ <b>Не настроено:</b> {counts['not_configured']}")
    lines.append("")
    lines.extend(summary_lines)

    lines.extend(_render_section_header("📌 Что важно сейчас"))
    lines.extend(f"• {item}" for item in important_now)

    lines.extend(_render_section_header("Общий статус"))
    lines.append(f"• {'🟢 Система стабильна' if ok else '🔴 Есть активные проблемы'}")
    if active_problems:
        lines.extend(f"• {item}" for item in active_problems)
    else:
        lines.append("• Критических проблем не выявлено.")

    lines.extend(_render_section_header("Инфраструктура"))
    lines.extend(
        [
            f"• Операционная система: {host.get('os')}",
            f"• Время работы: {host.get('uptime')}",
            f"• Свободная память: {host.get('free_ram_gb')}",
            f"• Свободный диск: {host.get('free_disk_gb')}",
        ]
    )

    lines.extend(_render_section_header("OpenClaw / OpenCloud"))
    lines.extend(_render_named_item("Шлюз", platform_checks["gateway_reachable"]))
    if _status_kind(platform_checks["gateway_probe"]) != "ok":
        lines.extend(_render_named_item("Проверка шлюза", platform_checks["gateway_probe"]))
    if _status_kind(platform_checks["deep_diagnostics"]) != "ok":
        lines.append("• Глубокая диагностика — 🟡 ограничена")
        deep_reason = _status_reason(platform_checks["deep_diagnostics"]).replace("missing scope:", "отсутствует доступ ")
        if deep_reason:
            lines.append(f"  Причина: {deep_reason}")
    lines.extend(_render_named_item("Планировщик OpenClaw", platform_checks["cron_api"]))
    lines.extend(_render_named_item("Контур доставки", platform_checks["delivery_path"]))
    lines.append(f"• Версия OpenClaw: <b>{platform_checks.get('openclaw_version')}</b>")
    lines.append(f"• Доступное обновление: <b>{platform_checks.get('openclaw_update')}</b>")
    lines.append(f"• Ошибок подряд: <b>{platform_checks.get('consecutive_errors')}</b>")

    lines.extend(_render_section_header("Интеграции"))
    for label, payload in integrations.items():
        lines.extend(_render_named_item(label, payload))

    lines.extend(_render_section_header("Пользовательские возможности"))
    for label, payload in capabilities.items():
        lines.extend(_render_named_item(label, payload))

    lines.extend(_render_section_header("Планировщик"))
    for label, payload in scheduler.items():
        lines.append(f"• <b>{label}</b>")
        lines.append(f"  Статус: {_status_emoji(payload)} {_status_word(payload)}")
        reason = _status_reason(payload)
        if reason:
            lines.append(f"  Детали: {reason}")

    lines.extend(_render_section_header("Безопасность"))
    for label, payload in security.items():
        lines.extend(_render_named_item(label, payload))

    lines.extend(_render_section_header("⚠️ Риски и техдолг"))
    if observations:
        lines.extend(f"• {item}" for item in observations)
    else:
        lines.append("• Существенных рисков и техдолга не выявлено.")

    if new_apis:
        lines.extend(_render_section_header("Новые интеграции"))
        for item in new_apis:
            lines.append(f"• {item['name']} — {item['message']}")

    if changes_24h:
        lines.extend(_render_section_header("📊 Изменения за 24 часа"))
        lines.append(f"• Новых ошибок: <b>{changes_24h['new_errors']}</b>")
        lines.append(f"• Новых предупреждений: <b>{changes_24h['new_warnings']}</b>")
        lines.append(f"• Исправлено: <b>{changes_24h['fixed']}</b>")
        lines.append(f"• Индекс здоровья: <b>{changes_24h['prev_score']} → {changes_24h['score']}</b>")

    lines.extend(_render_section_header("📌 Итог"))
    lines.append(f"• {'🟢 Система стабильна' if ok else '🔴 Есть активные проблемы'}")
    lines.append(f"• {'🟢 Критических проблем нет' if not active_problems else f'🔴 Критических проблем: {len(active_problems)}'}")
    lines.append(
        "• 🟡 Есть незначительные деградации"
        if counts["warning"] or counts["not_configured"]
        else "• 🟢 Существенных деградаций не выявлено"
    )
    if _status_kind(capabilities["Web search для Ларисы"]) != "ok":
        lines.append("• 🟡 Требуется плановая донастройка web-поиска")

    lines.extend(_render_section_header("Время отчёта"))
    lines.append(f"• Проверка: {now_msk}")

    return "\n".join(lines)


def run_system_health(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    env_data = _env_dict(env)
    if str(env_data.get("SYSTEM_HEALTH_MODE") or "").strip().lower() == MOCK_MODE:
        return _mock_health_payload()

    host = _build_host_snapshot()
    bitrix_payload = _check_bitrix_api(env_data)
    platform_checks = _build_platform_snapshot(env_data)
    integrations = _build_integrations_snapshot(env_data, bitrix_payload)
    capabilities = _build_capabilities_snapshot(env_data)
    scheduler = _check_scheduler_snapshot()
    security = _check_security_snapshot(env_data)
    new_apis = _load_new_apis(env_data)
    active_problems = _collect_active_problems(platform_checks, integrations, capabilities)
    observations = _collect_observations(platform_checks, integrations, capabilities)
    ok = not active_problems
    score = _health_score(active_problems)
    changes_24h = _changes_last_24h(
        env_data,
        score=score,
        active_problems=active_problems,
        observations=observations,
    )

    _append_health_log(
        env_data,
        event="system_health",
        ok=ok,
        active_problems=active_problems,
        observations=observations,
        integrations={name: payload.get("status") for name, payload in integrations.items()},
        capabilities={name: payload.get("status") for name, payload in capabilities.items()},
        score=score,
    )

    return {
        "ok": ok,
        "host": host,
        "platform": platform_checks,
        "integrations": integrations,
        "capabilities": capabilities,
        "scheduler": scheduler,
        "security": security,
        "new_apis": new_apis,
        "warnings": observations,
        "observations": observations,
        "active_problems": active_problems,
        "score": score,
        "text": format_system_health_report(
            ok=ok,
            host=host,
            platform_checks=platform_checks,
            integrations=integrations,
            capabilities=capabilities,
            scheduler=scheduler,
            security=security,
            observations=observations,
            active_problems=active_problems,
            new_apis=new_apis,
            score=score,
            changes_24h=changes_24h,
        ),
    }
