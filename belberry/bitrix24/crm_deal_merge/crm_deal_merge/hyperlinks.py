"""Универсальные хелперы для HYPERLINK-формул Sheets.

Локаль таблицы — ru_RU → разделитель аргументов формул `;`, не `,`.
"""
from __future__ import annotations

from .config import PORTAL_DOMAIN

DEAL_URL = f"https://{PORTAL_DOMAIN}/crm/deal/details/{{id}}/"
COMPANY_URL = f"https://{PORTAL_DOMAIN}/crm/company/details/{{id}}/"
CONTACT_URL = f"https://{PORTAL_DOMAIN}/crm/contact/details/{{id}}/"
LEAD_URL = f"https://{PORTAL_DOMAIN}/crm/lead/details/{{id}}/"


def _escape(text: str) -> str:
    return (text or "").replace('"', '""')


def hlink(url: str, label: str) -> str:
    """Готовая HYPERLINK-формула под локаль ru_RU."""
    return f'=HYPERLINK("{_escape(url)}";"{_escape(label)}")'


def deal_link(deal_id: str | int, label: str | None = None) -> str:
    did = str(deal_id)
    return hlink(DEAL_URL.format(id=did), label or f"deal #{did}")


def company_link(company_id: str | int, label: str | None = None) -> str:
    cid = str(company_id)
    return hlink(COMPANY_URL.format(id=cid), label or f"company #{cid}")


def contact_link(contact_id: str | int, label: str | None = None) -> str:
    cid = str(contact_id)
    return hlink(CONTACT_URL.format(id=cid), label or f"contact #{cid}")


def lead_link(lead_id: str | int, label: str | None = None) -> str:
    lid = str(lead_id)
    return hlink(LEAD_URL.format(id=lid), label or f"lead #{lid}")


# Sheets-side формулы (работают через cell-reference, без вызовов в Bitrix)
def deal_formula_cell(id_cell: str, label_cell: str | None = None) -> str:
    """Динамическая формула: hyperlink на deal по ID из ячейки.

    id_cell — типа "C2", label_cell — "B2" или None (тогда показывает ID).
    """
    label_expr = label_cell if label_cell else id_cell
    return f'=HYPERLINK("{DEAL_URL.format(id="")}"&{id_cell}&"/";{label_expr})'


def company_formula_cell(id_cell: str, label_cell: str | None = None) -> str:
    label_expr = label_cell if label_cell else id_cell
    return f'=HYPERLINK("{COMPANY_URL.format(id="")}"&{id_cell}&"/";{label_expr})'


def contact_formula_cell(id_cell: str, label_cell: str | None = None) -> str:
    label_expr = label_cell if label_cell else id_cell
    return f'=HYPERLINK("{CONTACT_URL.format(id="")}"&{id_cell}&"/";{label_expr})'


def lead_formula_cell(id_cell: str, label_cell: str | None = None) -> str:
    label_expr = label_cell if label_cell else id_cell
    return f'=HYPERLINK("{LEAD_URL.format(id="")}"&{id_cell}&"/";{label_expr})'
