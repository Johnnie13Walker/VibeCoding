"""Единый source of truth для состава sales-команды Sales Copilot."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

DEFAULT_SALES_DEPARTMENT_NAMES = (
    "Группа продаж Belberry",
    "Группа продаж Acoola Team",
    "Телемаркетинг",
)
DEFAULT_EXCLUDED_USER_MARKERS = (
    "интегратор",
    "интеграц",
    "integrator",
    "integration",
    "technical",
    "техничес",
    "service account",
    "service user",
    "служебн",
    "сервисн",
    "robot",
    "робот",
    " bot ",
    " бот ",
)
LEADER_POSITION_MARKERS = ("руководител", "директор", "роп")


def split_multi_value(raw_value: Any) -> list[str]:
    raw = str(raw_value or "").replace("\n", ",").replace(";", ",")
    return [item.strip() for item in raw.split(",") if item.strip()]


def normalize_name(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def compact_person_name(value: Any) -> str:
    raw = " ".join(str(value or "").split()).strip()
    if not raw:
        return ""
    parts = raw.split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
    return raw


def manager_name(user: Mapping[str, Any]) -> str:
    last_name = str(user.get("last_name") or "").strip()
    name = str(user.get("name") or "").strip()
    if last_name and name:
        return f"{last_name} {name}"
    return (
        compact_person_name(user.get("full_name"))
        or compact_person_name(user.get("name"))
        or str(user.get("id") or "").strip()
        or "без ответственного"
    )


def user_department_ids(user: Mapping[str, Any]) -> set[str]:
    return {
        str(item).strip()
        for item in (user.get("department_ids") or [])
        if str(item).strip()
    }


def infer_role(user: Mapping[str, Any], departments_by_id: Mapping[str, Mapping[str, Any]]) -> str:
    position = normalize_name(user.get("position"))
    department_names = [
        normalize_name((departments_by_id.get(str(dept_id)) or {}).get("name"))
        for dept_id in (user.get("department_ids") or [])
    ]
    haystack = " ".join([position, *department_names])
    if "телемарк" in haystack:
        return "telemarketing"
    return "sales"


def role_marker(role: str) -> str:
    normalized = str(role or "").strip().lower()
    if normalized == "telemarketing":
        return "TM"
    return "SM"


def sales_allowlist_user_ids(department_filter: Mapping[str, Any] | None) -> set[str]:
    return {
        str(user_id).strip()
        for user_id in (department_filter or {}).get("allowlist_users") or []
        if str(user_id).strip()
    }


def _resolve_sales_root_departments(
    env_data: Mapping[str, Any],
    *,
    departments_by_id: Mapping[str, Mapping[str, Any]],
    departments_by_name: Mapping[str, Mapping[str, Any]],
) -> tuple[str, list[str], list[str], list[str]]:
    configured_ids = split_multi_value(env_data.get("SALES_DEPARTMENT_IDS"))
    configured_names = split_multi_value(env_data.get("SALES_DEPARTMENT_NAMES")) or list(DEFAULT_SALES_DEPARTMENT_NAMES)
    mode = "ids" if configured_ids else "names"
    found_departments: list[str] = []
    missing_departments: list[str] = []
    root_department_ids: list[str] = []

    if configured_ids:
        for department_id in configured_ids:
            department = departments_by_id.get(str(department_id))
            if department:
                root_department_ids.append(str(department.get("id") or "").strip())
                found_departments.append(str(department.get("name") or department_id))
            else:
                missing_departments.append(str(department_id))
    else:
        for department_name in configured_names:
            department = departments_by_name.get(normalize_name(department_name))
            if department:
                root_department_ids.append(str(department.get("id") or "").strip())
                found_departments.append(str(department.get("name") or department_name))
            else:
                missing_departments.append(str(department_name))

    return (
        mode,
        found_departments,
        missing_departments,
        list(dict.fromkeys([item for item in root_department_ids if item])),
    )


def _expand_department_scope(
    root_department_ids: list[str],
    *,
    departments: list[Mapping[str, Any]],
) -> list[str]:
    children_by_parent: dict[str, list[str]] = defaultdict(list)
    for item in departments:
        department_id = str(item.get("id") or "").strip()
        parent_id = str(item.get("parent_id") or "").strip()
        if department_id and parent_id:
            children_by_parent[parent_id].append(department_id)

    seen: set[str] = set()
    queue = list(root_department_ids)
    while queue:
        department_id = queue.pop(0)
        if not department_id or department_id in seen:
            continue
        seen.add(department_id)
        queue.extend(children_by_parent.get(department_id) or [])
    return list(dict.fromkeys(root_department_ids + sorted(seen)))


def _promote_common_sales_parent(
    mode: str,
    root_department_ids: list[str],
    *,
    departments_by_id: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    if mode != "names" or len(root_department_ids) < 2:
        return list(root_department_ids)

    parent_ids = {
        str((departments_by_id.get(department_id) or {}).get("parent_id") or "").strip()
        for department_id in root_department_ids
        if str((departments_by_id.get(department_id) or {}).get("parent_id") or "").strip()
    }
    if len(parent_ids) != 1:
        return list(root_department_ids)

    parent_id = next(iter(parent_ids), "")
    parent_name = normalize_name((departments_by_id.get(parent_id) or {}).get("name"))
    if "продаж" not in parent_name:
        return list(root_department_ids)
    return [parent_id]


def _scope_head_ids(
    department_ids: list[str],
    *,
    departments_by_id: Mapping[str, Mapping[str, Any]],
) -> set[str]:
    return {
        str((departments_by_id.get(department_id) or {}).get("head_user_id") or "").strip()
        for department_id in department_ids
        if str((departments_by_id.get(department_id) or {}).get("head_user_id") or "").strip()
    }


def _is_service_department_user(
    user: Mapping[str, Any],
    *,
    departments_by_id: Mapping[str, Mapping[str, Any]],
) -> bool:
    full_name = normalize_name(manager_name(user))
    if not full_name:
        return False
    department_names = {
        normalize_name((departments_by_id.get(department_id) or {}).get("name"))
        for department_id in user_department_ids(user)
    }
    return full_name in department_names


def _explicit_excluded_user_ids(env_data: Mapping[str, Any]) -> set[str]:
    return {item for item in split_multi_value(env_data.get("SALES_EXCLUDED_USER_IDS")) if item}


def _explicit_excluded_user_names(env_data: Mapping[str, Any]) -> set[str]:
    return {
        normalize_name(item)
        for item in split_multi_value(env_data.get("SALES_EXCLUDED_USER_NAMES"))
        if normalize_name(item)
    }


def _excluded_user_markers(env_data: Mapping[str, Any]) -> tuple[str, ...]:
    configured = [normalize_name(item) for item in split_multi_value(env_data.get("SALES_EXCLUDED_USER_MARKERS"))]
    merged = [item for item in configured if item] + list(DEFAULT_EXCLUDED_USER_MARKERS)
    return tuple(dict.fromkeys(item for item in merged if item))


def _user_identity_haystacks(
    user: Mapping[str, Any],
    *,
    departments_by_id: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    department_names = [
        str((departments_by_id.get(department_id) or {}).get("name") or "").strip()
        for department_id in user_department_ids(user)
    ]
    return [
        normalize_name(manager_name(user)),
        normalize_name(user.get("full_name")),
        normalize_name(user.get("position")),
        normalize_name(user.get("email")),
        normalize_name(" ".join(department_names)),
    ]


def _excluded_scope_reason(
    user: Mapping[str, Any],
    *,
    env_data: Mapping[str, Any],
    departments_by_id: Mapping[str, Mapping[str, Any]],
    head_ids: set[str],
) -> str | None:
    user_id = str(user.get("id") or "").strip()
    position = normalize_name(user.get("position"))
    if user_id and user_id in head_ids:
        return "department_head_or_service_entity"
    if any(marker in position for marker in LEADER_POSITION_MARKERS):
        return "department_head_or_service_entity"
    if _is_service_department_user(user, departments_by_id=departments_by_id):
        return "department_head_or_service_entity"

    if user_id and user_id in _explicit_excluded_user_ids(env_data):
        return "explicit_blacklist"

    normalized_names = _explicit_excluded_user_names(env_data)
    if normalize_name(manager_name(user)) in normalized_names or normalize_name(user.get("full_name")) in normalized_names:
        return "explicit_blacklist"

    haystacks = [item for item in _user_identity_haystacks(user, departments_by_id=departments_by_id) if item]
    for marker in _excluded_user_markers(env_data):
        compact_marker = normalize_name(marker)
        if compact_marker and any(compact_marker in haystack for haystack in haystacks):
            return "service_or_integration_account"
    return None


def resolve_sales_team_filter(
    env: Mapping[str, Any] | None,
    *,
    snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    env_data = dict(env or {})
    snapshot_data = dict(snapshot or {})
    departments = list(snapshot_data.get("departments") or [])
    users_by_id = dict(snapshot_data.get("responsibles") or {})
    departments_by_id = {
        str(item.get("id") or "").strip(): item
        for item in departments
        if str(item.get("id") or "").strip()
    }
    departments_by_name = {
        normalize_name(item.get("name")): item
        for item in departments
        if normalize_name(item.get("name"))
    }

    mode, found_departments, missing_departments, root_department_ids = _resolve_sales_root_departments(
        env_data,
        departments_by_id=departments_by_id,
        departments_by_name=departments_by_name,
    )
    root_department_ids = _promote_common_sales_parent(
        mode,
        root_department_ids,
        departments_by_id=departments_by_id,
    )
    allowlist_department_ids = _expand_department_scope(root_department_ids, departments=departments)
    head_ids = _scope_head_ids(allowlist_department_ids, departments_by_id=departments_by_id)
    allowlist_users: list[str] = []
    allowlist_user_names: list[str] = []
    scoped_active_users: list[str] = []
    excluded_users: list[dict[str, str]] = []

    for user_id, user in users_by_id.items():
        if not user_id or not bool(user.get("active")):
            continue
        department_ids = user_department_ids(user)
        if not allowlist_department_ids or not department_ids.intersection(allowlist_department_ids):
            continue
        scoped_active_users.append(str(user_id))
        excluded_reason = _excluded_scope_reason(
            user,
            env_data=env_data,
            departments_by_id=departments_by_id,
            head_ids=head_ids,
        )
        if excluded_reason:
            excluded_users.append(
                {
                    "id": str(user_id),
                    "name": manager_name(user),
                    "role": role_marker(infer_role(user, departments_by_id)),
                    "reason": excluded_reason,
                }
            )
            continue
        allowlist_users.append(str(user_id))
        allowlist_user_names.append(manager_name(user))

    warnings: list[str] = []
    if missing_departments:
        warnings.append(
            "Не найдены sales-подразделения по точному совпадению: " + ", ".join(missing_departments)
        )
    if not allowlist_department_ids:
        warnings.append("Фильтр продажных подразделений не собран.")
    elif not allowlist_users:
        warnings.append("В sales-подразделениях не найдено активных сотрудников.")

    return {
        "mode": mode,
        "found_departments": found_departments,
        "missing_departments": missing_departments,
        "allowlist_department_ids": allowlist_department_ids,
        "allowlist_count": len(allowlist_users),
        "allowlist_users": sorted(allowlist_users),
        "allowlist_user_names": sorted(allowlist_user_names),
        "scoped_active_users_count": len(scoped_active_users),
        "scoped_active_users": sorted(scoped_active_users),
        "excluded_users": sorted(excluded_users, key=lambda item: (item["name"], item["id"])),
        "warnings": warnings,
    }
