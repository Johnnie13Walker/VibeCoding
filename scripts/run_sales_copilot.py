#!/usr/bin/env python3
"""Bridge-рантайм Льва Петровича: тянет live env/state с сервера и запускает локальный sales runtime."""

from __future__ import annotations

import argparse
import io
import json
import os
from datetime import date
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from apps.lev_petrovich.legacy_sales_agent.report_contract import sales_followup_report_types
from shared.contracts.sales_runtime_contract import REMOTE_ENV_KEYS, REPORT_TYPES
from shared.contracts.telegram_routing_contract import normalize_chat_id

WHOOP_ENV_FILE = ROOT_DIR.parent / "whoop" / ".env"
DEFAULT_REMOTE_HOST = "72.56.83.251"
DEFAULT_REMOTE_ENV_FILE = "/opt/openclaw/.env"
DEFAULT_REMOTE_STATE_DIR = "/opt/openclaw/state/bitrix_app"
DEFAULT_REMOTE_SALES_TELEGRAM_TOKEN_FILE = "/root/.openclaw/telegram/commercial-director.bot_token"
DEFAULT_SALES_CODE_ROOT = ROOT_DIR
MOCK_TEXT = {
    "sales": "📊 Sales Copilot\n\nMOCK sales report",
    "pipeline": "📊 Pipeline\n\nMOCK pipeline report",
    "risks": "🚨 Риски по продажам\n\nMOCK risks report",
    "focus": "🎯 Фокус РОПа\n\nMOCK focus report",
    "weekly": "🗓 Еженедельный отчёт Льва Петровича\n\nMOCK weekly report",
    "bitrixcheck": "Bitrix connection: OK\n\nДоступно:\n- сделки\n- встречи\n- брифы\n- задачи\n\nWazzup API: OK (channels, webhooks)\nWazzup история: История диалогов считается из webhook archive; документированный read-only endpoint dialogs/messages не подтвержден\nWazzup диалоги: OK (45 payloads; вчера dialogs=21, messages=64; latest=19.03 23:10)",
}


class SalesBridgeError(RuntimeError):
    pass


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = raw_line.split("=", 1)
        cleaned = value.strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
            cleaned = cleaned[1:-1]
        values[key.strip()] = cleaned
    return values


def _load_runtime_env() -> dict[str, str]:
    merged: dict[str, str] = {}
    for path in (ROOT_DIR / "infra" / "remote-ops.env", ROOT_DIR / ".env.integrations", WHOOP_ENV_FILE):
        merged.update(_parse_env_file(path))
    merged.update({str(key): str(value) for key, value in os.environ.items()})
    return merged


def _ssh_base(env: Mapping[str, str], host: str) -> list[str]:
    ssh_user = str(env.get("SSH_USER") or "").strip()
    ssh_key_path = str(env.get("SSH_KEY_PATH") or "").strip()
    ssh_port = str(env.get("SSH_PORT") or "22").strip() or "22"
    if not ssh_user or not ssh_key_path:
        raise SalesBridgeError("Не заданы SSH_USER/SSH_KEY_PATH для bridge Sales Copilot")
    return [
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
        "ConnectTimeout=10",
        f"{ssh_user}@{host}",
    ]


def _fetch_remote_env(env: Mapping[str, str], host: str, remote_env_file: str) -> dict[str, str]:
    command = _ssh_base(env, host) + [f"sudo cat {shlex.quote(remote_env_file)}"]
    completed = subprocess.run(command, text=True, capture_output=True, check=False, timeout=30)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or f"ssh rc={completed.returncode}").strip()
        raise SalesBridgeError(f"Не удалось прочитать live env с сервера: {detail}")
    raw_values: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        raw_values[key.strip()] = value.strip()
    return {key: value for key, value in raw_values.items() if key in REMOTE_ENV_KEYS}


def _sync_remote_state(env: Mapping[str, str], host: str, remote_state_dir: str, target_dir: Path) -> Path:
    remote_path = Path(remote_state_dir)
    parent = str(remote_path.parent)
    name = remote_path.name
    command = _ssh_base(env, host) + [f"sudo tar -C {shlex.quote(parent)} -cf - {shlex.quote(name)}"]
    completed = subprocess.run(command, capture_output=True, check=False, timeout=60)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or f"ssh rc={completed.returncode}").decode("utf-8", errors="replace").strip()
        raise SalesBridgeError(f"Не удалось синхронизировать live state Bitrix: {detail}")
    if not completed.stdout:
        raise SalesBridgeError("Live state Bitrix с сервера пуст")
    target_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:*") as archive:
        archive.extractall(target_dir)
    state_path = target_dir / name
    if not state_path.exists():
        raise SalesBridgeError("После синхронизации не найден локальный bitrix_app state")
    return state_path


def _fetch_remote_text(env: Mapping[str, str], host: str, remote_path: str) -> str:
    command = _ssh_base(env, host) + [f"sudo cat {shlex.quote(remote_path)}"]
    completed = subprocess.run(command, text=True, capture_output=True, check=False, timeout=30)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or f"ssh rc={completed.returncode}").strip()
        raise SalesBridgeError(f"Не удалось прочитать remote file {remote_path}: {detail}")
    return completed.stdout


def _build_agent_env(base_env: Mapping[str, str], remote_env: Mapping[str, str], local_state_dir: Path, code_root: Path) -> dict[str, str]:
    runtime = {str(key): str(value) for key, value in base_env.items()}
    runtime.update({str(key): str(value) for key, value in remote_env.items()})
    runtime["BITRIX_APP_STATE_DIR"] = str(local_state_dir)
    runtime["TZ"] = "Europe/Moscow"
    runtime["PYTHONIOENCODING"] = "utf-8"
    existing_path = str(runtime.get("PYTHONPATH") or "").strip()
    runtime["PYTHONPATH"] = f"{code_root}{os.pathsep}{existing_path}" if existing_path else str(code_root)
    return runtime


def _resolve_agent_timeout(
    env: Mapping[str, str],
    *,
    report_type: str,
    date_from: str = "",
    date_to: str = "",
) -> int:
    configured = str(env.get("SALES_AGENT_TIMEOUT_SEC") or "").strip()
    default_timeout = 900 if report_type == "weekly" else 240
    if configured:
        return max(int(configured), default_timeout)
    if not date_from or not date_to:
        return default_timeout
    try:
        start_date = date.fromisoformat(date_from)
        end_date = date.fromisoformat(date_to)
    except ValueError:
        return default_timeout
    period_days = max((end_date - start_date).days + 1, 1)
    return min(max(default_timeout + (period_days * 45), default_timeout), 1800)


def _run_sales_agent(
    code_root: Path,
    report_type: str,
    *,
    send: bool,
    env: Mapping[str, str],
    date_from: str = "",
    date_to: str = "",
) -> str:
    command = [sys.executable, "-m", "agents.lev_petrovich", "--report", report_type]
    runtime_env = dict(env)
    if not send:
        runtime_env["SALES_SKIP_ACCESS_REPORT"] = "1"
    timeout_sec = _resolve_agent_timeout(
        runtime_env,
        report_type=report_type,
        date_from=date_from,
        date_to=date_to,
    )
    if date_from:
        command.extend(["--date-from", date_from])
    if date_to:
        command.extend(["--date-to", date_to])
    if send:
        command.append("--send")
    completed = subprocess.run(
        command,
        cwd=code_root,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_sec,
        env=runtime_env,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or f"rc={completed.returncode}").strip()
        raise SalesBridgeError(f"Sales Copilot завершился ошибкой: {detail}")
    return (completed.stdout or "").strip()


def _build_sales_runtime_payload(
    *,
    code_root: Path,
    report_type: str,
    env: Mapping[str, str],
    date_from: str = "",
    date_to: str = "",
) -> dict[str, object]:
    code_root_str = str(code_root)
    if code_root_str not in sys.path:
        sys.path.insert(0, code_root_str)
    from apps.lev_petrovich.agent import build_sales_report_from_env

    runtime_env = dict(env)
    runtime_env["SALES_SKIP_ACCESS_REPORT"] = "1"
    payload = build_sales_report_from_env(
        runtime_env,
        report_type=report_type,
        date_from=date_from or None,
        date_to=date_to or None,
    )
    if not isinstance(payload, dict):
        raise SalesBridgeError("Sales runtime вернул неожиданный payload")
    return payload


def _build_followup_messages(
    code_root: Path,
    *,
    report_type: str,
    env: Mapping[str, str],
    date_from: str = "",
    date_to: str = "",
    use_mock: bool = False,
) -> list[dict[str, str]]:
    if report_type != "sales":
        return []

    followup_messages: list[dict[str, str]] = []
    for followup_report_type in sales_followup_report_types(report_type):
        followup_text = MOCK_TEXT[followup_report_type] if use_mock else _run_sales_agent(
            code_root,
            followup_report_type,
            send=False,
            env=env,
            date_from=date_from,
            date_to=date_to,
        )
        if not followup_text.strip():
            continue
        followup_messages.append(
            {
                "report_type": followup_report_type,
                "text": followup_text,
                "parse_mode": "HTML",
            }
        )
    return followup_messages


def _build_bridge_payload(
    code_root: Path,
    *,
    report_type: str,
    env: Mapping[str, str],
    date_from: str = "",
    date_to: str = "",
    use_mock: bool = False,
) -> dict[str, object]:
    if use_mock:
        text = MOCK_TEXT[report_type]
        followup_messages = _build_followup_messages(
            code_root,
            report_type=report_type,
            env=env,
            date_from=date_from,
            date_to=date_to,
            use_mock=True,
        )
    elif report_type == "bitrixcheck":
        text = _run_bitrix_check(code_root, env=env)
        followup_messages = []
    else:
        runtime_payload = _build_sales_runtime_payload(
            code_root=code_root,
            report_type=report_type,
            env=env,
            date_from=date_from,
            date_to=date_to,
        )
        text = str(runtime_payload.get("text") or "").strip()
        followup_messages = [
            {
                "report_type": str(item.get("report_type") or "").strip(),
                "text": str(item.get("text") or "").strip(),
                "parse_mode": str(item.get("parse_mode") or "").strip() or "HTML",
            }
            for item in (runtime_payload.get("followup_messages") or [])
            if str(item.get("text") or "").strip()
        ]

    parse_mode = "HTML" if report_type != "bitrixcheck" else None
    return {
        "ok": True,
        "report_type": report_type,
        "text": text,
        "parse_mode": parse_mode,
        "followup_messages": followup_messages,
    }


def _run_bitrix_check(code_root: Path, *, env: Mapping[str, str]) -> str:
    script = """
import os

from cloudbot.providers.wazzup_provider import WazzupProvider
from cloudbot.providers.bitrix.bitrix_sales_adapter import (
    BRIEF_CATEGORY_ID,
    BRIEF_ENTITY_TYPE_ID,
    MEETING_CATEGORY_ID,
    MEETING_ENTITY_TYPE_ID,
    SALES_DEAL_CATEGORY_ID,
    BitrixSalesAdapter,
)

adapter = BitrixSalesAdapter.from_env()
access = adapter.check_access()
access_by_key = {str(item.get("key") or ""): item for item in access}
wazzup_provider = WazzupProvider.from_env(dict(os.environ))
wazzup = wazzup_provider.get_archive_status()
wazzup_api = wazzup_provider.get_api_status()
wazzup_history = wazzup_provider.get_history_source_status()

critical_keys = {"profile", "deals"}
critical_failed = any(item.get("key") in critical_keys and not item.get("ok") for item in access)
optional_failed = any(not item.get("ok") for item in access if item.get("key") not in critical_keys)
status = "ERROR" if critical_failed else "WARNING" if optional_failed else "OK"

available = [item for item in access if item.get("ok")]
unavailable = [item for item in access if not item.get("ok")]
tasks_item = next((item for item in access if item.get("key") == "tasks"), None)
telephony_item = access_by_key.get("telephony") or {}

lines = [
    f"Bitrix connection: {status}",
    "",
    f"Источник: {adapter.sales_read_mode()}",
    f"Портал: {adapter.portal_base_url() or '-'}",
    f"Сделки: category {SALES_DEAL_CATEGORY_ID}",
    f"Встречи: type {MEETING_ENTITY_TYPE_ID} / category {MEETING_CATEGORY_ID}",
    f"Брифы: type {BRIEF_ENTITY_TYPE_ID} / category {BRIEF_CATEGORY_ID}",
    "",
    "Доступно:",
]

if available:
    lines.extend(f"- {item.get('label')} — {item.get('message') or item.get('status') or 'OK'}" for item in available)
else:
    lines.append("- ничего")

lines.extend(["", "Недоступно:"])
if unavailable:
    lines.extend(f"- {item.get('label')} — {item.get('message') or item.get('status') or 'error'}" for item in unavailable)
else:
    lines.append("- нет")

if telephony_item:
    lines.extend(["", f"Телефония: {telephony_item.get('message') or telephony_item.get('status') or '-'}"])

if wazzup_api:
    lines.append(f"Wazzup API: {wazzup_api.get('message') or wazzup_api.get('status') or '-'}")

if wazzup_history:
    lines.append(f"Wazzup история: {wazzup_history.get('message') or wazzup_history.get('status') or '-'}")

if wazzup:
    lines.append(f"Wazzup диалоги: {wazzup.get('message') or wazzup.get('status') or '-'}")

if tasks_item:
    lines.append(f"Задачи: {tasks_item.get('message') or tasks_item.get('status') or '-'}")

print("\\n".join(lines))
"""
    command = [
        sys.executable,
        "-c",
        script,
    ]
    completed = subprocess.run(
        command,
        cwd=code_root,
        text=True,
        capture_output=True,
        check=False,
        timeout=180,
        env=dict(env),
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or f"rc={completed.returncode}").strip()
        raise SalesBridgeError(f"Bitrix check завершился ошибкой: {detail}")
    return (completed.stdout or "").strip()


def _split_telegram_text(text: str, limit: int = 3500) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return [""]
    if len(raw) <= limit:
        return [raw]

    parts: list[str] = []
    current = ""
    for block in raw.split("\n\n"):
        candidate = block if not current else f"{current}\n\n{block}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            parts.append(current)
            current = ""
        if len(block) <= limit:
            current = block
            continue
        lines = block.split("\n")
        line_chunk = ""
        for line in lines:
            candidate_line = line if not line_chunk else f"{line_chunk}\n{line}"
            if len(candidate_line) <= limit:
                line_chunk = candidate_line
                continue
            if line_chunk:
                parts.append(line_chunk)
            if len(line) <= limit:
                line_chunk = line
                continue
            start_pos = 0
            while start_pos < len(line):
                parts.append(line[start_pos:start_pos + limit])
                start_pos += limit
            line_chunk = ""
        if line_chunk:
            current = line_chunk

    if current:
        parts.append(current)
    return [part for part in parts if part]


def _normalize_chat_id(value: str | None) -> str:
    return normalize_chat_id(value)


def _resolve_telegram_delivery(env: Mapping[str, str], *, report_type: str) -> tuple[str, str, str]:
    bot_token = str(env.get("SALES_TELEGRAM_BOT_TOKEN") or env.get("TELEGRAM_BOT_TOKEN") or "").strip()
    api_base = str(
        env.get("SALES_TELEGRAM_API_BASE_URL")
        or env.get("TELEGRAM_API_BASE_URL")
        or "https://api.telegram.org"
    ).strip()
    if report_type == "weekly":
        chat_id = _normalize_chat_id(env.get("SALES_WEEKLY_TELEGRAM_CHAT_ID"))
        if not bot_token:
            raise SalesBridgeError("Не задан SALES_TELEGRAM_BOT_TOKEN для weekly-отчёта")
        if not chat_id:
            raise SalesBridgeError(
                "Не задан SALES_WEEKLY_TELEGRAM_CHAT_ID для weekly-отчёта; fixed target не настроен"
            )
        return bot_token, chat_id, api_base

    chat_id = _normalize_chat_id(
        str(
            env.get("SALES_TELEGRAM_CHAT_ID")
            or env.get("SALES_TELEGRAM_OWNER_ID")
            or env.get("TELEGRAM_CHAT_ID")
            or env.get("TELEGRAM_OWNER_ID")
            or ""
        ).strip()
    )
    if not bot_token or not chat_id:
        raise SalesBridgeError(
            "Не заданы SALES_TELEGRAM_BOT_TOKEN/SALES_TELEGRAM_CHAT_ID "
            "(или fallback TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID) для отправки отчета"
        )
    return bot_token, chat_id, api_base


def _send_telegram_message(
    text: str,
    env: Mapping[str, str],
    *,
    report_type: str,
    parse_mode: str | None = None,
) -> dict[str, str]:
    bot_token, chat_id, api_base = _resolve_telegram_delivery(env, report_type=report_type)

    payload: dict[str, object] = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    request = Request(
        f"{api_base.rstrip('/')}/bot{bot_token}/sendMessage",
        method="POST",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as error:
        try:
            detail = error.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            detail = str(error)
        raise SalesBridgeError(f"Telegram sendMessage failed: {detail}") from None
    except URLError as error:
        raise SalesBridgeError(f"Telegram sendMessage failed: {error.reason or error}") from None

    response_payload = json.loads(raw or "{}")
    if response_payload.get("ok") is not True:
        description = response_payload.get("description") or "unknown error"
        raise SalesBridgeError(f"Telegram sendMessage failed: {description}")

    result = response_payload.get("result") or {}
    masked_chat_id = "***" if len(chat_id) <= 4 else f"{chat_id[:2]}***{chat_id[-2:]}"
    return {
        "chat_id_masked": masked_chat_id,
        "message_id": str(result.get("message_id") or ""),
    }


def _send_telegram_report(
    text: str,
    env: Mapping[str, str],
    *,
    report_type: str,
    parse_mode: str | None = None,
) -> dict[str, object]:
    chunks = _split_telegram_text(text)
    message_ids: list[str] = []
    chat_masked = "***"
    for chunk in chunks:
        delivery = _send_telegram_message(chunk, env, report_type=report_type, parse_mode=parse_mode)
        chat_masked = str(delivery.get('chat_id_masked') or chat_masked)
        message_id = str(delivery.get('message_id') or '').strip()
        if message_id:
            message_ids.append(message_id)
    return {
        'chat_id_masked': chat_masked,
        'message_ids': message_ids,
        'chunks': len(chunks),
    }


def _resolve_remote_host(env: Mapping[str, str]) -> str:
    return (
        str(env.get("BITRIX_SALES_REMOTE_HOST") or "").strip()
        or str(env.get("PRIMARY_HOST") or "").strip()
        or DEFAULT_REMOTE_HOST
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bridge Sales Copilot")
    parser.add_argument("--report", choices=sorted(REPORT_TYPES), default="sales")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--date-from", default="")
    parser.add_argument("--date-to", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if bool(args.date_from) != bool(args.date_to):
        raise SalesBridgeError("Для произвольного периода нужны оба параметра: --date-from и --date-to.")
    if (args.date_from or args.date_to) and args.report != "weekly":
        raise SalesBridgeError("Произвольный период сейчас поддержан только для weekly-отчёта.")

    local_env = _load_runtime_env()
    use_mock = False
    if args.report == "bitrixcheck" and str(local_env.get("BITRIX_CHECK_MOCK") or "") == "1":
        use_mock = True
    elif str(local_env.get("SALES_COPILOT_MOCK") or "") == "1":
        use_mock = True

    code_root = Path(str(local_env.get("SALES_COPILOT_CODE_ROOT") or DEFAULT_SALES_CODE_ROOT)).expanduser()
    if not code_root.exists():
        raise SalesBridgeError(f"Не найден код Sales Copilot: {code_root}")

    remote_host = _resolve_remote_host(local_env)
    remote_env_file = str(local_env.get("SALES_REMOTE_ENV_FILE") or DEFAULT_REMOTE_ENV_FILE).strip() or DEFAULT_REMOTE_ENV_FILE
    remote_state_dir = str(local_env.get("SALES_REMOTE_STATE_DIR") or DEFAULT_REMOTE_STATE_DIR).strip() or DEFAULT_REMOTE_STATE_DIR

    if use_mock:
        payload = _build_bridge_payload(
            code_root,
            report_type=args.report,
            env=local_env,
            date_from=args.date_from,
            date_to=args.date_to,
            use_mock=True,
        )
        delivery_env = local_env
    else:
        remote_env = _fetch_remote_env(local_env, remote_host, remote_env_file)
        sales_token = str(local_env.get("SALES_TELEGRAM_BOT_TOKEN") or remote_env.get("SALES_TELEGRAM_BOT_TOKEN") or "").strip()
        if not sales_token:
            token_file = str(
                local_env.get("SALES_REMOTE_TELEGRAM_BOT_TOKEN_FILE")
                or remote_env.get("SALES_TELEGRAM_BOT_TOKEN_FILE")
                or DEFAULT_REMOTE_SALES_TELEGRAM_TOKEN_FILE
            ).strip()
            if token_file:
                sales_token = _fetch_remote_text(local_env, remote_host, token_file).strip()
                if sales_token:
                    remote_env = dict(remote_env)
                    remote_env["SALES_TELEGRAM_BOT_TOKEN"] = sales_token

        with tempfile.TemporaryDirectory(prefix="sales-copilot-state-", dir=ROOT_DIR / "tmp") as tmp_dir:
            state_root = _sync_remote_state(local_env, remote_host, remote_state_dir, Path(tmp_dir))
            agent_env = _build_agent_env(local_env, remote_env, state_root, code_root)
            payload = _build_bridge_payload(
                code_root,
                report_type=args.report,
                env=agent_env,
                date_from=args.date_from,
                date_to=args.date_to,
                use_mock=False,
            )
            delivery_env = agent_env

    if args.send:
        delivery = _send_telegram_report(
            str(payload.get("text") or ""),
            delivery_env,
            report_type=args.report,
            parse_mode=str(payload.get("parse_mode") or "") or None,
        )
        message_ids = [item for item in delivery.get('message_ids') or [] if item]
        if message_ids:
            print(
                f"Telegram sent: chat={delivery['chat_id_masked']} message_ids={','.join(message_ids)} chunks={delivery.get('chunks')}",
                file=sys.stderr,
            )
        for followup in payload.get("followup_messages") or []:
            followup_delivery = _send_telegram_report(
                str(followup.get("text") or ""),
                delivery_env,
                report_type=str(followup.get("report_type") or args.report),
                parse_mode=str(followup.get("parse_mode") or "") or None,
            )
            followup_ids = [item for item in followup_delivery.get("message_ids") or [] if item]
            if followup_ids:
                print(
                    f"Telegram sent: chat={followup_delivery['chat_id_masked']} message_ids={','.join(followup_ids)} "
                    f"chunks={followup_delivery.get('chunks')} report={followup.get('report_type')}",
                    file=sys.stderr,
                )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(str(payload.get("text") or ""))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SalesBridgeError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
