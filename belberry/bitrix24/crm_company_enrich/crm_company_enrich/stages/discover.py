"""Стадия discover — собрать очередь из deal-merge `merge_groups`.

Текущая задача crm_company_enrich обслуживает не весь портал, а ровно остаток
deal-merge: группы `PLAN_READY`, где `inn == "—"` и есть нормализованный
`domain`. Поэтому очередь пересобирается из `merge_groups` целиком, чтобы
старые широкие прогоны по всем компаниям не отправили в enrich-web тысячи
лишних компаний.

Ничего не пишет в Bitrix. Sheets-write только в `company_enrich_queue`.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..config import TAB_DEAL_MERGE_GROUPS
from ..hyperlinks import company_link
from ..models import QueueRow, extract_web_url, find_uf_inn_candidate
from ..sheet_store import write_queue_rows
from ..sheets_client import SheetsClient
from ..state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def run(bx: BitrixClient, sheets: SheetsClient, *, limit_companies: int | None = None) -> dict:
    print("[discover] читаю merge_groups: status=PLAN_READY, inn=—, domain непустой")
    raw_rows = sheets.read(TAB_DEAL_MERGE_GROUPS)
    if not raw_rows:
        raise RuntimeError(f"Лист {TAB_DEAL_MERGE_GROUPS} пуст или недоступен")

    headers = [str(x) for x in raw_rows[0]]
    candidates: list[dict[str, str]] = []
    for raw in raw_rows[1:]:
        row = _row_dict(headers, raw)
        if row.get("status", "").strip().upper() != "PLAN_READY":
            continue
        if row.get("ИНН", "").strip() != "—":
            continue
        domain = row.get("domain", "").strip()
        company_id = row.get("company_id", "").strip()
        if not company_id or not domain:
            continue
        candidates.append(row)
        if limit_companies is not None and len(candidates) >= limit_companies:
            break

    print(f"[discover] найдено deal-merge no_inn групп: {len(candidates)}")

    rows: list[QueueRow] = []
    for idx, row in enumerate(candidates, start=1):
        company_id = row["company_id"].strip()
        domain = row["domain"].strip()
        company = bx.get_company(company_id) or {}
        title = str(company.get("TITLE") or _formula_label(row.get("🏢 Компания")) or f"company #{company_id}")
        web = extract_web_url(company.get("WEB")) or domain
        qrow = QueueRow(
            company_id=company_id,
            company_name=title,
            domain=domain,
            n_losers=_int(row.get("n_loser")),
            n_total_transferable=(
                _int(row.get("n_activities_planned"))
                + _int(row.get("n_timeline_planned"))
                + _int(row.get("n_contacts_planned"))
                + _int(row.get("n_sp_planned"))
            ),
            current_inn=None,
            web=web,
            uf_inn_candidate=find_uf_inn_candidate(company),
            n_deals=_int(row.get("n_total")),
            n_contacts=0,
            in_active_deal_merge=False,
            status=Status.NEW,
            priority=_int(row.get("n_loser")),
            company_link_formula=company_link(company_id, title),
        )
        rows.append(qrow)
        if idx % 25 == 0:
            print(f"[discover] подготовлено {idx}/{len(candidates)}")

    rows.sort(key=lambda r: (r.n_total_transferable, r.n_losers), reverse=True)
    write_queue_rows(sheets, rows)
    print(f"[discover] company_enrich_queue пересобран: {len(rows)} строк")

    return {
        "source": TAB_DEAL_MERGE_GROUPS,
        "queued": len(rows),
        "limited": limit_companies is not None,
        "ts_msk": datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
    }


def _row_dict(headers: list[str], raw: list[str]) -> dict[str, str]:
    return {h: str(raw[i]) if i < len(raw) else "" for i, h in enumerate(headers)}


def _int(value: str | None) -> int:
    if value is None:
        return 0
    s = str(value).strip()
    return int(float(s)) if s else 0


def _formula_label(value: str | None) -> str | None:
    """Грубый fallback для HYPERLINK(label), если Bitrix get временно пустой."""
    if not value:
        return None
    s = str(value)
    if "," not in s:
        return s
    label = s.rsplit(",", 1)[-1].strip()
    return label.strip(')"')
