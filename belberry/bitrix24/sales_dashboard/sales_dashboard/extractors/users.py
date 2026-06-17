"""Экстрактор пользователей и справочников (стадии, воронки).

Используется и в ETL (чтобы Looker Studio мог JOIN), и в user_sync.
"""
from __future__ import annotations

from ..bitrix_client import BitrixClient

# ---------- users ----------

USER_HEADER = [
    "user_id",
    "active",
    "email",
    "name",
    "last_name",
    "second_name",
    "full_name",
    "work_position",
    "department_ids",       # comma-separated
    "date_register",
    "last_login",
    "is_online",
]


def extract_users(client: BitrixClient) -> list[list]:
    """Все пользователи портала, активные и нет.

    Не фильтруем по ACTIVE — это нужно user_sync, чтобы знать, кого деактивировать.
    """
    rows: list[list] = []
    for u in client.paginate_by_start("user.get", {"ADMIN_MODE": "Y"}):
        rows.append(_user_to_row(u))
    return rows


def _user_to_row(u: dict) -> list:
    name = u.get("NAME") or ""
    last = u.get("LAST_NAME") or ""
    second = u.get("SECOND_NAME") or ""
    full = " ".join(p for p in [last, name, second] if p).strip()
    depts = u.get("UF_DEPARTMENT") or []
    if isinstance(depts, list):
        depts_str = ",".join(str(d) for d in depts)
    else:
        depts_str = str(depts) if depts else ""
    return [
        _as_int(u.get("ID")),
        "Y" if u.get("ACTIVE") in (True, "Y", "y", 1, "1") else "N",
        (u.get("EMAIL") or u.get("WORK_EMAIL") or "").lower(),
        name,
        last,
        second,
        full,
        u.get("WORK_POSITION") or "",
        depts_str,
        u.get("DATE_REGISTER") or "",
        u.get("LAST_LOGIN") or "",
        "Y" if u.get("IS_ONLINE") in (True, "Y", "y") else "N",
    ]


# ---------- categories (воронки) ----------

CATEGORY_HEADER = ["category_id", "name", "sort", "is_default"]


def extract_categories(client: BitrixClient) -> list[list]:
    body = client.call("crm.dealcategory.list", {"order": {"SORT": "ASC"}})
    rows: list[list] = []
    for c in body.get("result") or []:
        rows.append(
            [
                _as_int(c.get("ID")),
                c.get("NAME") or "",
                _as_int(c.get("SORT")),
                "Y" if c.get("IS_DEFAULT") in (True, "Y") else "N",
            ]
        )
    # Bitrix не отдаёт через crm.dealcategory.list дефолтную воронку (CATEGORY_ID=0).
    # Добавим её явно.
    has_default = any(r[0] == 0 for r in rows)
    if not has_default:
        rows.insert(0, [0, "Общая", 0, "Y"])
    return rows


# ---------- stages ----------

STAGE_HEADER = [
    "stage_id",         # как в crm.deal.list (например "C50:NEW")
    "category_id",
    "status_id",
    "name",
    "sort",
    "semantic",         # P/S/F
]


def extract_stages(client: BitrixClient, categories: list[list]) -> list[list]:
    """Стадии по всем воронкам.

    Bitrix: crm.dealcategory.stage.list(id=<category_id>)
    """
    rows: list[list] = []
    for cat in categories:
        cat_id = cat[0]
        try:
            body = client.call("crm.dealcategory.stage.list", {"id": cat_id})
        except Exception:
            continue
        for s in body.get("result") or []:
            rows.append(
                [
                    s.get("STATUS_ID") or "",   # это и есть stage_id в crm.deal.list
                    cat_id,
                    s.get("STATUS_ID") or "",
                    s.get("NAME") or "",
                    _as_int(s.get("SORT")),
                    s.get("SEMANTICS") or "P",
                ]
            )
    return rows


def _as_int(v) -> int | str:
    try:
        return int(v)
    except (TypeError, ValueError):
        return ""
