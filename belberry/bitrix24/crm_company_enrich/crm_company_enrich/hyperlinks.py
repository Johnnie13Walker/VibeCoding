"""HYPERLINK-формулы для Google Sheets.

Локаль таблицы — ru_RU → разделитель аргументов формул `;`, не `,`.
Скопировано из crm_deal_merge.hyperlinks (deal-формулы убраны — здесь нужны
только company-карточки).
"""
from __future__ import annotations

from .config import PORTAL_DOMAIN

COMPANY_URL = f"https://{PORTAL_DOMAIN}/crm/company/details/{{id}}/"
CONTACT_URL = f"https://{PORTAL_DOMAIN}/crm/contact/details/{{id}}/"


def _escape(text: str) -> str:
    return (text or "").replace('"', '""')


def hlink(url: str, label: str) -> str:
    """Готовая HYPERLINK-формула под локаль ru_RU."""
    return f'=HYPERLINK("{_escape(url)}";"{_escape(label)}")'


def company_link(company_id: str | int, label: str | None = None) -> str:
    cid = str(company_id)
    return hlink(COMPANY_URL.format(id=cid), label or f"company #{cid}")


def contact_link(contact_id: str | int, label: str | None = None) -> str:
    cid = str(contact_id)
    return hlink(CONTACT_URL.format(id=cid), label or f"contact #{cid}")


# Sheets-side формулы (работают через cell-reference)
def company_formula_cell(id_cell: str, label_cell: str | None = None) -> str:
    """Динамическая формула: hyperlink на company по ID из ячейки.

    id_cell — типа "A2", label_cell — "B2" или None (тогда показывает ID).
    ВАЖНО: label_cell НЕ должен совпадать с ячейкой, в которую пишется формула
    (иначе #REF! из-за self-reference, см. memory feedback_sheets_hyperlink_safety).
    """
    label_expr = label_cell if label_cell else id_cell
    return f'=HYPERLINK("{COMPANY_URL.format(id="")}"&{id_cell}&"/";{label_expr})'
