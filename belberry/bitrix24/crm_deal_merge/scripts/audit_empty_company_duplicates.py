#!/usr/bin/env python3
"""Read-only аудит дублей для листа «Пустые компании»."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from crm_deal_merge.bitrix_client import BitrixClient  # noqa: E402
from crm_deal_merge.config import LOG_PATH, PORTAL_DOMAIN, SERVICE_ACCOUNT_JSON, STATE_PATH  # noqa: E402
from crm_deal_merge.sheets_client import SheetsClient  # noqa: E402

SHEET_ID = "13L0gqwkNzrWacYeI5TzkOxZuRuXn5bBCtfxx-uzHH_4"
TAB = "Пустые компании"
MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def main() -> None:
    bx = BitrixClient(STATE_PATH, log_path=LOG_PATH)
    sheets = SheetsClient(SHEET_ID, SERVICE_ACCOUNT_JSON)

    print("[dup-audit] читаю лист...")
    sheet_rows = sheets.read(TAB, "A1:R12000", unformatted=True)
    headers = sheet_rows[1]
    idx = {h: i for i, h in enumerate(headers)}
    empty_rows = []
    for rownum, row in enumerate(sheet_rows[2:], start=3):
        company_id_idx = idx.get("company_id", 12)
        if len(row) <= company_id_idx:
            continue
        company_id = clean(row[company_id_idx])
        if company_id:
            empty_rows.append((rownum, row, company_id))
    print(f"[dup-audit] строк пустых компаний: {len(empty_rows)}")

    print("[dup-audit] выгружаю все компании...")
    companies = list(
        bx.paginate(
            "crm.company.list",
            {
                "select": [
                    "ID",
                    "TITLE",
                    "REVENUE",
                    "DATE_CREATE",
                    "DATE_MODIFY",
                    "UF_CRM_1735331882180",
                    "UF_CRM_1737098549301",
                    "WEB",
                ],
            },
        )
    )
    by_id = {clean(c.get("ID")): c for c in companies}
    by_inn: dict[str, list[str]] = defaultdict(list)
    by_title: dict[str, list[str]] = defaultdict(list)
    for company in companies:
        company_id = clean(company.get("ID"))
        inn = clean(company.get("UF_CRM_1735331882180"))
        if inn and inn != "0":
            by_inn[inn].append(company_id)
        normalized = normalize_title(company.get("TITLE"))
        if normalized:
            by_title[normalized].append(company_id)
    print(f"[dup-audit] компаний: {len(companies)}")

    print("[dup-audit] выгружаю контакты...")
    contact_counts: Counter[str] = Counter()
    for contact in bx.paginate("crm.contact.list", {"select": ["ID", "COMPANY_ID"]}):
        company_id = clean(contact.get("COMPANY_ID"))
        if company_id and company_id != "0":
            contact_counts[company_id] += 1
    print(f"[dup-audit] контактов с компанией: {sum(contact_counts.values())}")

    print("[dup-audit] выгружаю сделки...")
    deal_counts: Counter[str] = Counter()
    deal_examples: dict[str, list[dict]] = defaultdict(list)
    for deal in bx.paginate(
        "crm.deal.list",
        {"select": ["ID", "TITLE", "COMPANY_ID", "STAGE_ID", "CATEGORY_ID", "CLOSED"]},
    ):
        company_id = clean(deal.get("COMPANY_ID"))
        if company_id and company_id != "0":
            deal_counts[company_id] += 1
            if len(deal_examples[company_id]) < 3:
                deal_examples[company_id].append(deal)
    print(f"[dup-audit] сделок с компанией: {sum(deal_counts.values())}")

    print("[dup-audit] выгружаю лиды...")
    lead_counts: Counter[str] = Counter()
    for lead in bx.paginate(
        "crm.lead.list",
        {"select": ["ID", "TITLE", "COMPANY_ID", "STATUS_ID"]},
    ):
        company_id = clean(lead.get("COMPANY_ID"))
        if company_id and company_id != "0":
            lead_counts[company_id] += 1
    print(f"[dup-audit] лидов с компанией: {sum(lead_counts.values())}")

    now = datetime.now(MOSCOW_TZ).isoformat(timespec="seconds") + " МСК"
    new_headers = [
        "Есть дубль",
        "Ключ дубля",
        "Дубль company_id",
        "Дубль компания",
        "Сделки дубля",
        "Контакты дубля",
        "Лиды дубля",
        "Пример сделки дубля",
        "Рекомендация",
        "Проверено дублей",
    ]
    rows = []
    stats: Counter[str] = Counter()
    inn_idx = idx.get("ИНН", 2)

    for _rownum, sheet_row, company_id in empty_rows:
        company = by_id.get(company_id, {})
        title = clean(company.get("TITLE") or (sheet_row[0] if sheet_row else ""))
        inn = clean(company.get("UF_CRM_1735331882180"))
        if not inn and len(sheet_row) > inn_idx:
            inn = clean(sheet_row[inn_idx])

        key = ""
        candidates: list[str] = []
        if inn and inn != "0":
            key = f"ИНН {inn}"
            candidates = [cid for cid in by_inn.get(inn, []) if cid != company_id]
        if not candidates:
            normalized = normalize_title(title)
            key = f"название {normalized}" if normalized else key
            candidates = [cid for cid in by_title.get(normalized, []) if cid != company_id] if normalized else []

        candidates = sorted(set(candidates), key=lambda cid: score(cid, by_id, deal_counts, contact_counts, lead_counts), reverse=True)
        active_candidates = [cid for cid in candidates if deal_counts[cid] or contact_counts[cid] or lead_counts[cid]]

        if active_candidates:
            best_id = active_candidates[0]
            duplicate = by_id.get(best_id, {})
            stats["active_duplicate"] += 1
            rows.append(
                [
                    "да",
                    key,
                    company_link(best_id, best_id),
                    company_link(best_id, clean(duplicate.get("TITLE")) or best_id),
                    str(deal_counts[best_id]),
                    str(contact_counts[best_id]),
                    str(lead_counts[best_id]),
                    ", ".join(deal_link(clean(d.get("ID")), clean(d.get("TITLE")) or None) for d in deal_examples.get(best_id, [])),
                    "кандидат на объединение: пустую карточку не удалять без переноса полезных полей",
                    now,
                ]
            )
        elif candidates:
            best_id = candidates[0]
            duplicate = by_id.get(best_id, {})
            stats["inactive_duplicate"] += 1
            rows.append(
                [
                    "да",
                    key,
                    company_link(best_id, best_id),
                    company_link(best_id, clean(duplicate.get("TITLE")) or best_id),
                    str(deal_counts[best_id]),
                    str(contact_counts[best_id]),
                    str(lead_counts[best_id]),
                    "",
                    "дубль без активности: ручная проверка, затем можно объединять/удалять",
                    now,
                ]
            )
        else:
            stats["no_duplicate"] += 1
            rows.append(
                [
                    "нет",
                    key,
                    "",
                    "",
                    "0",
                    "0",
                    "0",
                    "",
                    "кандидат на удаление после ручной spot-check проверки",
                    now,
                ]
            )

    update_rows = [[f"Аудит дублей пустых компаний; Б24 read-only; обновлено {now}"] + [""] * (len(new_headers) - 1), new_headers] + rows
    print("[dup-audit] пишу Google Sheets...")
    for offset in range(0, len(update_rows), 200):
        chunk = update_rows[offset : offset + 200]
        start_row = offset + 1
        end_row = start_row + len(chunk) - 1
        sheets.update(TAB, f"T{start_row}:AC{end_row}", chunk, value_input_option="USER_ENTERED")
    print(json.dumps({"rows": len(rows), **stats}, ensure_ascii=False, indent=2))


def normalize_title(value: object) -> str:
    text = str(value or "").lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    stop = {
        "ооо",
        "ао",
        "зао",
        "пао",
        "оао",
        "ип",
        "общество",
        "ограниченной",
        "ответственностью",
        "обособленное",
        "подразделение",
        "ано",
        "ночу",
        "гб",
        "мц",
        "медицинский",
        "центр",
    }
    return " ".join(part for part in text.split() if part not in stop).strip()


def score(
    company_id: str,
    by_id: dict[str, dict],
    deal_counts: Counter[str],
    contact_counts: Counter[str],
    lead_counts: Counter[str],
) -> tuple[int, int, int, int, int]:
    company = by_id.get(company_id, {})
    activity = deal_counts[company_id] + contact_counts[company_id] + lead_counts[company_id]
    return (
        activity,
        deal_counts[company_id],
        contact_counts[company_id],
        to_int(company.get("REVENUE")),
        to_int(company_id),
    )


def company_link(company_id: str, label: str | None = None) -> str:
    safe_label = (label or f"company #{company_id}").replace('"', '""')
    return f'=HYPERLINK("https://{PORTAL_DOMAIN}/crm/company/details/{company_id}/";"{safe_label}")'


def deal_link(deal_id: str, label: str | None = None) -> str:
    safe_label = (label or f"deal #{deal_id}").replace('"', '""')
    return f'=HYPERLINK("https://{PORTAL_DOMAIN}/crm/deal/details/{deal_id}/";"{safe_label}")'


def clean(value: object) -> str:
    return str(value or "").strip()


def to_int(value: object) -> int:
    try:
        return int(float(str(value or 0).replace(" ", "").replace(",", ".")))
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    main()
