"""Безопасные ручные операции со строками Google Sheets."""
from __future__ import annotations

from typing import Any

from .sync_deals import brand_industry_parity_report


def delete_row_guarded(
    bx,
    service,
    *,
    sheet_id: str,
    tab_title: str,
    sheet_gid: int,
    row_number: int,
    deal_id: str = "",
    company_id: str = "",
    live: bool = False,
) -> dict[str, Any]:
    row = _read_row(service, sheet_id=sheet_id, tab_title=tab_title, row_number=row_number)
    inferred_deal_id = deal_id or _cell(row, 8)
    inferred_company_id = company_id or _cell(row, 12)
    if not inferred_deal_id:
        return _blocked(row, "deal_id_missing")

    deal = bx.get_deal(str(inferred_deal_id))
    if not deal:
        return _blocked(row, f"deal_not_found:{inferred_deal_id}")

    inferred_company_id = inferred_company_id or str(deal.get("COMPANY_ID") or "")
    if not inferred_company_id:
        return _blocked(row, "company_id_missing")

    company = bx.get_company(str(inferred_company_id))
    if not company:
        return _blocked(row, f"company_not_found:{inferred_company_id}")

    report = brand_industry_parity_report(company, deal)
    if not report.get("ok"):
        return {
            "deleted": False,
            "dry_run": not live,
            "row_number": row_number,
            "deal_id": str(inferred_deal_id),
            "company_id": str(inferred_company_id),
            "row": row,
            "parity": report,
            "error": "brand_industry_parity_failed",
        }

    if live:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={
                "requests": [
                    {
                        "deleteDimension": {
                            "range": {
                                "sheetId": int(sheet_gid),
                                "dimension": "ROWS",
                                "startIndex": int(row_number) - 1,
                                "endIndex": int(row_number),
                            }
                        }
                    }
                ]
            },
        ).execute()

    return {
        "deleted": bool(live),
        "dry_run": not live,
        "row_number": row_number,
        "deal_id": str(inferred_deal_id),
        "company_id": str(inferred_company_id),
        "row": row,
        "parity": report,
        "error": "",
    }


def _read_row(service, *, sheet_id: str, tab_title: str, row_number: int) -> list[str]:
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{tab_title}'!A{row_number}:U{row_number}",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    rows = result.get("values") or []
    return [str(value or "") for value in rows[0]] if rows else []


def _cell(row: list[str], index: int) -> str:
    if index >= len(row):
        return ""
    return str(row[index] or "").strip()


def _blocked(row: list[str], error: str) -> dict[str, Any]:
    return {
        "deleted": False,
        "dry_run": True,
        "row": row,
        "parity": {"ok": False, "errors": [error]},
        "error": error,
    }
