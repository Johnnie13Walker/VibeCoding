#!/usr/bin/env python3
"""Read-only отчет по загрузке сотрудников в задачах Bitrix24."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time as time_module
import unicodedata
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cloudbot.providers.bitrix.bitrix_app_auth import BitrixAppAuth
from scripts.run_sales_copilot import (
    DEFAULT_REMOTE_ENV_FILE,
    DEFAULT_REMOTE_STATE_DIR,
    SalesBridgeError,
    _build_agent_env,
    _fetch_remote_env,
    _load_runtime_env,
    _resolve_remote_host,
    _sync_remote_state,
)

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
OPEN_STATUS_IDS = {"1", "2", "3", "4", "6"}
STATUS_FALLBACK = {
    "1": "Новая",
    "2": "Ждет выполнения",
    "3": "Выполняется",
    "4": "Ждет контроля",
    "5": "Завершена",
    "6": "Отложена",
    "7": "Отклонена",
}
DEFAULT_TARGETS = (
    ("tartysheva_lera", "тартышева", ("лера", "валерия")),
    ("bessonova_vlada", "бессонова", ("влада", "владислава", "владлена")),
    ("kuvandykov_yan", "кувандыков", ("ян",)),
)


def _norm(value: Any) -> str:
    raw = str(value or "").replace("ё", "е").replace("Ё", "Е")
    raw = unicodedata.normalize("NFKC", raw).casefold()
    return " ".join(raw.split())


def _pick(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _as_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _parse_dt(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=MOSCOW_TZ)
    return parsed.astimezone(MOSCOW_TZ)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt else None


def _user_name(user: Mapping[str, Any]) -> str:
    parts = [
        _pick(user, "LAST_NAME", "lastName", "last_name"),
        _pick(user, "NAME", "name"),
        _pick(user, "SECOND_NAME", "secondName", "second_name"),
    ]
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def _match_target(user: Mapping[str, Any], *, surname: str, aliases: tuple[str, ...]) -> bool:
    last = _norm(_pick(user, "LAST_NAME", "lastName", "last_name"))
    first = _norm(_pick(user, "NAME", "name"))
    full = _norm(_user_name(user))
    if surname not in last and surname not in full:
        return False
    return any(alias in first or alias in full for alias in aliases)


def _task_sort_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
    deadline = _parse_dt(item.get("deadline"))
    changed = _parse_dt(item.get("changed_at"))
    task_id = str(item.get("id") or "")
    numeric_id = int(task_id) if task_id.isdigit() else 0
    return (
        deadline is None,
        deadline or datetime.max.replace(tzinfo=MOSCOW_TZ),
        -numeric_id,
        changed or datetime.min.replace(tzinfo=MOSCOW_TZ),
    )


def _normalize_task(
    item: Mapping[str, Any],
    *,
    responsible: Mapping[str, Any],
    portal: str,
    status_map: Mapping[str, str],
) -> dict[str, Any]:
    task = item.get("task") if isinstance(item.get("task"), dict) else item
    status_id = str(_pick(task, "status", "STATUS") or "").strip()
    deadline = _parse_dt(_pick(task, "deadline", "DEADLINE"))
    created = _parse_dt(_pick(task, "createdDate", "CREATED_DATE", "created_date"))
    changed = _parse_dt(_pick(task, "changedDate", "CHANGED_DATE", "changed_date"))
    closed = _parse_dt(_pick(task, "closedDate", "CLOSED_DATE", "closed_date"))
    start_plan = _parse_dt(_pick(task, "startDatePlan", "START_DATE_PLAN", "start_date_plan"))
    end_plan = _parse_dt(_pick(task, "endDatePlan", "END_DATE_PLAN", "end_date_plan"))
    task_id = str(_pick(task, "id", "ID") or "").strip()
    responsible_id = str(
        _pick(task, "responsibleId", "RESPONSIBLE_ID", "responsible_id")
        or _pick(responsible, "ID", "id")
        or ""
    ).strip()
    url = ""
    if portal and responsible_id and task_id:
        url = f"{portal}/company/personal/user/{responsible_id}/tasks/task/view/{task_id}/"

    return {
        "id": task_id,
        "title": str(_pick(task, "title", "TITLE") or "").strip(),
        "status_id": status_id,
        "status": status_map.get(status_id) or STATUS_FALLBACK.get(status_id) or status_id or "-",
        "responsible_id": responsible_id,
        "responsible_name": _user_name(responsible),
        "deadline": _iso(deadline),
        "created_at": _iso(created),
        "changed_at": _iso(changed),
        "closed_at": _iso(closed),
        "start_plan": _iso(start_plan),
        "end_plan": _iso(end_plan),
        "priority": str(_pick(task, "priority", "PRIORITY") or "").strip() or None,
        "group_id": str(_pick(task, "groupId", "GROUP_ID") or "").strip() or None,
        "creator_id": str(_pick(task, "createdBy", "CREATED_BY", "created_by") or "").strip() or None,
        "accomplices": [
            str(value).strip()
            for value in _as_list(_pick(task, "accomplices", "ACCOMPLICES"))
            if str(value).strip()
        ],
        "auditors": [
            str(value).strip()
            for value in _as_list(_pick(task, "auditors", "AUDITORS"))
            if str(value).strip()
        ],
        "crm_bindings": [
            str(value).strip()
            for value in _as_list(_pick(task, "ufCrmTask", "UF_CRM_TASK"))
            if str(value).strip()
        ],
        "url": url,
    }


def _summarize_tasks(
    tasks: list[dict[str, Any]],
    *,
    now: datetime,
    week_start: datetime,
    week_end: datetime,
) -> dict[str, Any]:
    overdue: list[dict[str, Any]] = []
    due_today_remaining: list[dict[str, Any]] = []
    due_week_all: list[dict[str, Any]] = []
    due_week_remaining: list[dict[str, Any]] = []
    due_later: list[dict[str, Any]] = []
    no_deadline: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    high_priority: list[dict[str, Any]] = []
    waiting_control: list[dict[str, Any]] = []
    in_progress: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    by_day: dict[str, int] = {}

    for task in tasks:
        deadline = _parse_dt(task.get("deadline"))
        changed = _parse_dt(task.get("changed_at"))
        status_id = str(task.get("status_id") or "")
        if status_id == "4":
            waiting_control.append(task)
        if status_id == "3":
            in_progress.append(task)
        if status_id == "6":
            deferred.append(task)
        if str(task.get("priority") or "") == "2":
            high_priority.append(task)
        if changed and (now - changed) >= timedelta(days=7):
            stale.append(task)
        if deadline is None:
            no_deadline.append(task)
            continue

        day = deadline.date().isoformat()
        by_day[day] = by_day.get(day, 0) + 1
        if week_start <= deadline < week_end:
            due_week_all.append(task)
        if deadline < now:
            overdue.append(task)
        elif deadline.date() == now.date():
            due_today_remaining.append(task)
            due_week_remaining.append(task)
        elif deadline < week_end:
            due_week_remaining.append(task)
        else:
            due_later.append(task)

    urgent = len(overdue) + len(due_today_remaining)
    if len(overdue) >= 5 or len(due_week_remaining) >= 12 or urgent >= 7:
        load = "высокая"
    elif len(overdue) >= 2 or len(due_week_remaining) >= 6 or len(tasks) >= 18:
        load = "повышенная"
    elif len(due_week_remaining) >= 3 or len(tasks) >= 8:
        load = "средняя"
    else:
        load = "низкая"

    return {
        "open_total": len(tasks),
        "overdue": len(overdue),
        "due_today_remaining": len(due_today_remaining),
        "due_current_week_all": len(due_week_all),
        "due_current_week_remaining": len(due_week_remaining),
        "due_later": len(due_later),
        "no_deadline": len(no_deadline),
        "stale_7d": len(stale),
        "high_priority": len(high_priority),
        "waiting_control": len(waiting_control),
        "in_progress": len(in_progress),
        "deferred": len(deferred),
        "by_deadline_day": dict(sorted(by_day.items())),
        "load_estimate": load,
        "top_overdue": sorted(overdue, key=_task_sort_key)[:10],
        "top_due_week": sorted(due_week_remaining, key=_task_sort_key)[:12],
        "top_no_deadline": sorted(
            no_deadline,
            key=lambda task: _parse_dt(task.get("changed_at")) or datetime.min.replace(tzinfo=MOSCOW_TZ),
            reverse=True,
        )[:10],
        "top_stale": sorted(
            stale,
            key=lambda task: _parse_dt(task.get("changed_at")) or datetime.min.replace(tzinfo=MOSCOW_TZ),
        )[:10],
    }


def _expand_runtime_env(env: Mapping[str, str]) -> dict[str, str]:
    expanded = {str(key): str(value) for key, value in env.items()}
    for key in ("SSH_KEY_PATH",):
        if expanded.get(key):
            expanded[key] = os.path.expanduser(os.path.expandvars(expanded[key]))
    return expanded


def _sync_state_with_retry(env: Mapping[str, str], host: str, remote_state_dir: str, target_dir: Path) -> Path:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            return _sync_remote_state(env, host, remote_state_dir, target_dir)
        except SalesBridgeError as error:
            last_error = error
            if attempt < 3:
                time_module.sleep(float(attempt))
                continue
            raise
    raise last_error or SalesBridgeError("Не удалось синхронизировать live state Bitrix")


def _load_status_map(app: BitrixAppAuth) -> dict[str, str]:
    try:
        payload = app.call_payload("tasks.task.getFields", default={})
    except Exception:  # noqa: BLE001
        return dict(STATUS_FALLBACK)
    result = payload.get("result") if isinstance(payload, dict) else {}
    fields = result.get("fields") if isinstance(result, dict) else {}
    values = (fields.get("STATUS") or {}).get("values") if isinstance(fields, dict) else {}
    if not isinstance(values, dict):
        return dict(STATUS_FALLBACK)
    return {str(key): str(value) for key, value in values.items()} or dict(STATUS_FALLBACK)


def _portal_from_app_state(app: BitrixAppAuth) -> str:
    try:
        state = app.load_state()
    except Exception:  # noqa: BLE001
        return ""
    for candidate in (state.client_endpoint, state.server_endpoint):
        parsed = urlparse(str(candidate or ""))
        if parsed.scheme and parsed.netloc and not parsed.netloc.startswith("oauth."):
            return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    if state.domain and not state.domain.startswith("oauth."):
        return f"https://{state.domain}".rstrip("/")
    return ""


def _list_users(app: BitrixAppAuth) -> list[dict[str, Any]]:
    return app.list_method(
        "user.get",
        params={
            "FILTER": {},
            "SELECT": ["ID", "NAME", "LAST_NAME", "SECOND_NAME", "ACTIVE", "WORK_POSITION", "EMAIL"],
        },
        limit=3000,
    )


def _list_open_tasks_for_user(
    app: BitrixAppAuth,
    *,
    user: Mapping[str, Any],
    portal: str,
    status_map: Mapping[str, str],
) -> tuple[list[dict[str, Any]], str | None]:
    user_id = str(_pick(user, "ID", "id") or "").strip()
    select = [
        "ID",
        "TITLE",
        "STATUS",
        "RESPONSIBLE_ID",
        "CREATED_BY",
        "CREATED_DATE",
        "CHANGED_DATE",
        "DEADLINE",
        "CLOSED_DATE",
        "START_DATE_PLAN",
        "END_DATE_PLAN",
        "PRIORITY",
        "GROUP_ID",
        "ACCOMPLICES",
        "AUDITORS",
        "UF_CRM_TASK",
    ]
    task_items: list[dict[str, Any]] = []
    last_error: str | None = None
    try:
        task_items = app.list_method(
            "tasks.task.list",
            params={
                "filter": {"RESPONSIBLE_ID": user_id},
                "select": select,
                "order": {"ID": "desc"},
            },
            limit=1000,
        )
    except Exception as error:  # noqa: BLE001
        last_error = str(error)
        task_items = []

    normalized = [
        _normalize_task(item, responsible=user, portal=portal, status_map=status_map)
        for item in task_items
    ]
    open_tasks = [
        task
        for task in normalized
        if str(task.get("status_id") or "") in OPEN_STATUS_IDS and not task.get("closed_at")
    ]
    return sorted(open_tasks, key=_task_sort_key), last_error


def _build_text_report(result: Mapping[str, Any]) -> str:
    week_start = str(result.get("week_start_msk") or "")[:10]
    week_end_raw = _parse_dt(result.get("week_end_exclusive_msk"))
    week_end = (week_end_raw - timedelta(days=1)).date().isoformat() if week_end_raw else "-"
    lines = [
        f"Bitrix task load report: {result.get('generated_at_msk')}",
        f"Период: {week_start} - {week_end} МСК",
        f"Портал: {result.get('portal') or '-'}",
        "",
    ]
    for key, payload in (result.get("targets") or {}).items():
        selected = payload.get("selected_user") or {}
        summary = payload.get("summary") or {}
        lines.append(f"{selected.get('name') or key} (ID {selected.get('id') or '-'})")
        if not selected:
            lines.append("  Пользователь не найден")
            lines.append("")
            continue
        lines.append(
            "  Открыто: {open_total}; просрочено: {overdue}; сегодня осталось: {due_today_remaining}; "
            "до конца недели осталось: {due_current_week_remaining}; без срока: {no_deadline}; "
            "не обновлялись 7д: {stale_7d}; нагрузка: {load_estimate}".format(**summary)
        )
        for task in summary.get("top_overdue", [])[:5]:
            lines.append(f"  OVERDUE #{task['id']} {task.get('deadline') or '-'} [{task.get('status')}] {task.get('title')}")
        overdue_ids = {task.get("id") for task in summary.get("top_overdue", [])}
        for task in summary.get("top_due_week", [])[:5]:
            if task.get("id") in overdue_ids:
                continue
            lines.append(f"  WEEK #{task['id']} {task.get('deadline') or '-'} [{task.get('status')}] {task.get('title')}")
        lines.append("")
    return "\n".join(lines)


def build_report() -> dict[str, Any]:
    local_env = _expand_runtime_env(_load_runtime_env())
    remote_host = _resolve_remote_host(local_env)
    remote_env_file = str(local_env.get("SALES_REMOTE_ENV_FILE") or DEFAULT_REMOTE_ENV_FILE).strip() or DEFAULT_REMOTE_ENV_FILE
    remote_state_dir = str(local_env.get("SALES_REMOTE_STATE_DIR") or DEFAULT_REMOTE_STATE_DIR).strip() or DEFAULT_REMOTE_STATE_DIR
    remote_env = _fetch_remote_env(local_env, remote_host, remote_env_file)

    now = datetime.now(MOSCOW_TZ)
    week_start = datetime.combine(now.date() - timedelta(days=now.weekday()), time.min, tzinfo=MOSCOW_TZ)
    week_end = week_start + timedelta(days=7)

    with tempfile.TemporaryDirectory(prefix="bitrix-task-load-state-", dir=ROOT_DIR / "tmp") as tmp_dir:
        state_root = _sync_state_with_retry(local_env, remote_host, remote_state_dir, Path(tmp_dir))
        agent_env = _build_agent_env(local_env, remote_env, state_root, ROOT_DIR)
        app = BitrixAppAuth.from_env(agent_env)
        portal = _portal_from_app_state(app)
        status_map = _load_status_map(app)
        users = _list_users(app)

        result: dict[str, Any] = {
            "generated_at_msk": now.isoformat(timespec="seconds"),
            "week_start_msk": week_start.isoformat(timespec="seconds"),
            "week_end_exclusive_msk": week_end.isoformat(timespec="seconds"),
            "portal": portal,
            "source": "app_oauth:tasks.task.list",
            "assumption": (
                "Оценка загрузки сделана по открытым задачам, где сотрудник указан ответственным. "
                "Если в задачах не заполнены оценки времени, часы не вычисляются."
            ),
            "status_map": status_map,
            "targets": {},
        }

        for key, surname, aliases in DEFAULT_TARGETS:
            matched = [
                user
                for user in users
                if _match_target(user, surname=surname, aliases=aliases)
            ]
            candidates = [
                user
                for user in users
                if surname in _norm(_user_name(user))
            ][:10]
            target_payload: dict[str, Any] = {
                "query": {"surname": surname, "first_aliases": list(aliases)},
                "matched_users": [
                    {
                        "id": str(_pick(user, "ID", "id") or ""),
                        "name": _user_name(user),
                        "active": str(_pick(user, "ACTIVE", "active") or ""),
                        "position": str(_pick(user, "WORK_POSITION", "workPosition", "work_position") or ""),
                    }
                    for user in matched[:3]
                ],
                "surname_candidates": [
                    {
                        "id": str(_pick(user, "ID", "id") or ""),
                        "name": _user_name(user),
                        "active": str(_pick(user, "ACTIVE", "active") or ""),
                    }
                    for user in candidates
                ],
                "tasks": [],
                "summary": {},
            }
            result["targets"][key] = target_payload
            if not matched:
                continue

            user = next(
                (
                    item
                    for item in matched
                    if str(_pick(item, "ACTIVE", "active") or "").lower() in {"y", "true", "1"}
                ),
                matched[0],
            )
            open_tasks, last_error = _list_open_tasks_for_user(
                app,
                user=user,
                portal=portal,
                status_map=status_map,
            )
            target_payload["selected_user"] = {
                "id": str(_pick(user, "ID", "id") or ""),
                "name": _user_name(user),
                "active": str(_pick(user, "ACTIVE", "active") or ""),
            }
            target_payload["last_error"] = last_error
            target_payload["tasks"] = open_tasks
            target_payload["summary"] = _summarize_tasks(
                open_tasks,
                now=now,
                week_start=week_start,
                week_end=week_end,
            )

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only отчет по загрузке сотрудников в задачах Bitrix24")
    parser.add_argument("--json", action="store_true", help="Напечатать JSON-ответ с путями к отчетам")
    return parser.parse_args()


def _compact_summary(summary: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(summary, Mapping):
        return {}
    return {
        str(key): value
        for key, value in summary.items()
        if not str(key).startswith("top_")
    }


def main() -> int:
    args = parse_args()
    result = build_report()
    generated_at = _parse_dt(result.get("generated_at_msk")) or datetime.now(MOSCOW_TZ)
    stamp = generated_at.strftime("%Y%m%d_%H%M%S_MSK")
    out_dir = ROOT_DIR / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"bitrix_task_load_{stamp}.json"
    txt_path = out_dir / f"bitrix_task_load_{stamp}.txt"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(_build_text_report(result), encoding="utf-8")

    payload = {
        "ok": True,
        "json": str(json_path),
        "txt": str(txt_path),
        "summary": {
            key: _compact_summary(value.get("summary"))
            for key, value in (result.get("targets") or {}).items()
        },
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_build_text_report(result))
        print(f"\nJSON: {json_path}")
        print(f"TXT: {txt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
