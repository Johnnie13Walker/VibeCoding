"""Полная выгрузка из Bitrix: компании + сделки/контакты/лиды/реквизиты + резолв юзеров."""

import json
import time
from pathlib import Path

from .bitrix_client import BitrixClient
from .config import UF_FIELDS

COMPANY_BASE_FIELDS = [
    "ID", "TITLE", "DATE_CREATE", "DATE_MODIFY",
    "CREATED_BY_ID", "ASSIGNED_BY_ID",
    "HAS_PHONE", "HAS_EMAIL", "INDUSTRY", "REVENUE",
    "COMPANY_TYPE", "COMMENTS",
]


def _dump(path: Path, data: list[dict], label: str, started: float) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False))
    print(f"  {label}: {len(data)}, {time.time() - started:.0f}s → {path.name}")


def fetch_all(bx: BitrixClient, data_dir: Path) -> dict[str, list[dict]]:
    """Полная выгрузка пяти коллекций. Возвращает их же in-memory + пишет в data_dir."""
    data_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print("[fetch] companies (with UF) ...")
    companies = list(bx.paginate("crm.company.list", COMPANY_BASE_FIELDS + UF_FIELDS))
    _dump(data_dir / "companies.json", companies, "companies", t0)

    t0 = time.time()
    print("[fetch] deals (any category, with COMPANY_ID) ...")
    deals = list(bx.paginate(
        "crm.deal.list",
        ["ID", "COMPANY_ID", "CATEGORY_ID", "STAGE_ID", "CLOSED"],
        [("filter[>COMPANY_ID]", "0")],
    ))
    _dump(data_dir / "deals.json", deals, "deals", t0)

    t0 = time.time()
    print("[fetch] contacts (with COMPANY_ID) ...")
    contacts = list(bx.paginate(
        "crm.contact.list",
        ["ID", "COMPANY_ID"],
        [("filter[>COMPANY_ID]", "0")],
    ))
    _dump(data_dir / "contacts.json", contacts, "contacts", t0)

    t0 = time.time()
    print("[fetch] leads (with COMPANY_ID) ...")
    leads = list(bx.paginate(
        "crm.lead.list",
        ["ID", "COMPANY_ID", "STATUS_ID"],
        [("filter[>COMPANY_ID]", "0")],
    ))
    _dump(data_dir / "leads.json", leads, "leads", t0)

    t0 = time.time()
    print("[fetch] requisites (ENTITY_TYPE_ID=4) ...")
    requisites = list(bx.paginate(
        "crm.requisite.list",
        ["ID", "ENTITY_ID", "RQ_INN", "RQ_OGRN", "RQ_OGRNIP"],
        [("filter[ENTITY_TYPE_ID]", "4")],
    ))
    _dump(data_dir / "requisites.json", requisites, "requisites", t0)

    return {
        "companies": companies,
        "deals": deals,
        "contacts": contacts,
        "leads": leads,
        "requisites": requisites,
    }


def resolve_user_names(bx: BitrixClient, user_ids: set[str]) -> dict[str, str]:
    """Подтянуть имена юзеров через batch crm/user.get. Возвращает {uid: 'Имя Фамилия'}."""
    users: dict[str, str] = {}
    ids = sorted(user_ids)
    for start in range(0, len(ids), 50):
        chunk = ids[start:start + 50]
        params: list[tuple[str, str]] = [("halt", "0")]
        for uid in chunk:
            params.append((f"cmd[u{uid}]", f"user.get?ID={uid}"))
        resp = bx.call("batch", params)
        for key, value in resp.get("result", {}).get("result", {}).items():
            if value and isinstance(value, list) and len(value) > 0:
                u = value[0]
                uid = key[1:]
                name = " ".join(p for p in [u.get("NAME") or "", u.get("LAST_NAME") or ""] if p).strip()
                users[uid] = name or f"user#{uid}"
    return users
