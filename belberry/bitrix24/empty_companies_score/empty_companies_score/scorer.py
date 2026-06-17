"""Скоринг компаний по трём бинарным флагам: empty_links, empty_inn, empty_uf."""

from collections import Counter
from dataclasses import dataclass

from .config import UF_FIELDS, UF_LABELS


@dataclass
class ScoredCompany:
    id: str
    title: str
    assignee: str
    creator: str
    date_create: str
    date_modify: str
    n_deals: int
    n_contacts: int
    n_leads: int
    inn: str
    uf_filled_count: int
    uf_filled: str
    uf_brand: str
    uf_city: str
    uf_site: str
    uf_revenue: str
    empty_links: bool
    empty_inn: bool
    empty_uf: bool
    score: int
    safe_to_delete: bool


def _uf_state(company: dict) -> tuple[int, list[str]]:
    """Возвращает (заполнено_штук, [названия_заполненных_полей])."""
    filled: list[str] = []
    for field, label in zip(UF_FIELDS, UF_LABELS):
        raw = company.get(field)
        if raw is None:
            continue
        sv = str(raw).strip()
        if sv and sv not in ("0", "0.0", "false", "False"):
            filled.append(label)
    return len(filled), filled


def _build_inn_map(requisites: list[dict]) -> dict[str, str]:
    """company_id → RQ_INN (если в реквизите OGRN/OGRNIP без INN — пишем пустую строку)."""
    inn_by_co: dict[str, str] = {}
    for r in requisites:
        cid = str(r.get("ENTITY_ID") or "")
        if not cid:
            continue
        inn = (r.get("RQ_INN") or "").strip()
        ogrn = (r.get("RQ_OGRN") or "").strip()
        ogrnip = (r.get("RQ_OGRNIP") or "").strip()
        if inn:
            inn_by_co.setdefault(cid, inn)
        elif (ogrn or ogrnip) and cid not in inn_by_co:
            inn_by_co[cid] = ""
    return inn_by_co


def score_companies(
    companies: list[dict],
    deals: list[dict],
    contacts: list[dict],
    leads: list[dict],
    requisites: list[dict],
    users: dict[str, str],
) -> list[ScoredCompany]:
    deals_by_co = Counter(str(d["COMPANY_ID"]) for d in deals if d.get("COMPANY_ID"))
    contacts_by_co = Counter(str(c["COMPANY_ID"]) for c in contacts if c.get("COMPANY_ID"))
    leads_by_co = Counter(str(l["COMPANY_ID"]) for l in leads if l.get("COMPANY_ID"))
    inn_by_co = _build_inn_map(requisites)

    scored: list[ScoredCompany] = []
    for c in companies:
        cid = str(c["ID"])
        n_deals = deals_by_co.get(cid, 0)
        n_contacts = contacts_by_co.get(cid, 0)
        n_leads = leads_by_co.get(cid, 0)

        empty_links = (n_deals + n_contacts + n_leads) == 0
        inn = inn_by_co.get(cid, "")
        empty_inn = not bool(inn)
        uf_filled_count, uf_filled = _uf_state(c)
        empty_uf = uf_filled_count == 0

        score = int(empty_links) + int(empty_inn) + int(empty_uf)
        safe_to_delete = empty_links  # нет привязок → удалять можно

        scored.append(ScoredCompany(
            id=cid,
            title=(c.get("TITLE") or "").strip(),
            assignee=users.get(str(c.get("ASSIGNED_BY_ID") or ""), str(c.get("ASSIGNED_BY_ID") or "")),
            creator=users.get(str(c.get("CREATED_BY_ID") or ""), str(c.get("CREATED_BY_ID") or "")),
            date_create=(c.get("DATE_CREATE") or "")[:10],
            date_modify=(c.get("DATE_MODIFY") or "")[:10],
            n_deals=n_deals,
            n_contacts=n_contacts,
            n_leads=n_leads,
            inn=inn,
            uf_filled_count=uf_filled_count,
            uf_filled=",".join(uf_filled),
            uf_brand=str(c.get(UF_FIELDS[0]) or ""),
            uf_city=str(c.get(UF_FIELDS[1]) or ""),
            uf_site=str(c.get(UF_FIELDS[2]) or ""),
            uf_revenue=str(c.get(UF_FIELDS[3]) or ""),
            empty_links=empty_links,
            empty_inn=empty_inn,
            empty_uf=empty_uf,
            score=score,
            safe_to_delete=safe_to_delete,
        ))
    return scored


def select_for_upload(scored: list[ScoredCompany]) -> list[ScoredCompany]:
    """В Sheet попадают только score>=2 ИЛИ safe_to_delete. Сортировка: score desc, date_create asc."""
    filtered = [r for r in scored if r.score >= 2 or r.safe_to_delete]
    filtered.sort(key=lambda r: (-r.score, r.date_create))
    return filtered


def summary_counts(filtered: list[ScoredCompany]) -> dict[str, int]:
    """Срез для TG-нотификации и state-снапшота."""
    return {
        "total": len(filtered),
        "score_3": sum(1 for r in filtered if r.score == 3),
        "score_2": sum(1 for r in filtered if r.score == 2),
        "safe": sum(1 for r in filtered if r.safe_to_delete),
        "score_3_safe": sum(1 for r in filtered if r.score == 3 and r.safe_to_delete),
    }
