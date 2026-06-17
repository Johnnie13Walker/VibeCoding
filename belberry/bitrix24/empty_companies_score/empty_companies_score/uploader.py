"""Заливка отскоренных компаний в `Пустые компании (скоринг)` с цветовым форматированием."""

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from .config import COLUMNS, PORTAL_BASE, SA_KEY, SHEET_ID, TARGET_TAB
from .scorer import ScoredCompany

_GREEN = {"red": 0.85, "green": 0.95, "blue": 0.85}
_RED = {"red": 0.99, "green": 0.92, "blue": 0.92}
_YELLOW = {"red": 1.0, "green": 0.97, "blue": 0.82}
_HEADER = {"red": 0.85, "green": 0.92, "blue": 0.83}
_COL_WIDTHS = [280, 60, 90, 70, 80, 60, 110, 70, 200, 130, 100, 200, 110, 150, 150, 100, 100, 80]


def _sheets_service():
    creds = Credentials.from_service_account_file(
        SA_KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _cell(text, link=None, bold=False, bg=None, h_align=None):
    c = {"userEnteredValue": {"stringValue": str(text) if text is not None else ""}}
    fmt = {}
    if bold:
        fmt.setdefault("textFormat", {})["bold"] = True
    if bg:
        fmt["backgroundColor"] = bg
    if h_align:
        fmt["horizontalAlignment"] = h_align
    if fmt:
        c["userEnteredFormat"] = fmt
    if link and text:
        c["textFormatRuns"] = [{
            "startIndex": 0,
            "format": {
                "link": {"uri": link},
                "foregroundColor": {"red": 0.06, "green": 0.4, "blue": 0.75},
                "underline": True,
            },
        }]
    return c


def _num_cell(value, bold=False, bg=None):
    try:
        nv = float(value) if value not in (None, "", "0", 0) else 0.0
    except (TypeError, ValueError):
        nv = 0.0
    c = {"userEnteredValue": {"numberValue": nv}}
    fmt = {"horizontalAlignment": "RIGHT"}
    if bold:
        fmt.setdefault("textFormat", {})["bold"] = True
    if bg:
        fmt["backgroundColor"] = bg
    c["userEnteredFormat"] = fmt
    return c


def _ensure_tab(svc, sheet_id: str) -> dict:
    meta = svc.spreadsheets().get(spreadsheetId=sheet_id).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == TARGET_TAB:
            return s["properties"]
    body = {"requests": [{
        "addSheet": {"properties": {"title": TARGET_TAB, "gridProperties": {"rowCount": 100, "columnCount": 18}}}
    }]}
    resp = svc.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body=body).execute()
    return resp["replies"][0]["addSheet"]["properties"]


def upload(filtered: list[ScoredCompany]) -> None:
    svc = _sheets_service()
    target = _ensure_tab(svc, SHEET_ID)
    gid = target["sheetId"]

    grid_rows: list[dict] = [{"values": [_cell(h, bold=True, bg=_HEADER) for h in COLUMNS]}]
    for r in filtered:
        url = f"{PORTAL_BASE}/{r.id}/"
        score_bg = _RED if r.score == 3 else (_YELLOW if r.score == 2 else None)
        safe_bg = _GREEN if r.safe_to_delete else None
        cells = [
            _cell(r.title or f"company #{r.id}", link=url),
            _num_cell(r.score, bold=True, bg=score_bg),
            _cell("да" if r.safe_to_delete else "нет", bold=r.safe_to_delete, bg=safe_bg, h_align="CENTER"),
            _num_cell(r.n_deals),
            _num_cell(r.n_contacts),
            _num_cell(r.n_leads),
            _cell(r.inn),
            _num_cell(r.uf_filled_count),
            _cell(r.uf_filled),
            _cell(r.uf_brand),
            _cell(r.uf_city),
            _cell(r.uf_site),
            _cell(r.uf_revenue),
            _cell(r.assignee),
            _cell(r.creator),
            _cell(r.date_create),
            _cell(r.date_modify),
            _cell(r.id, h_align="RIGHT"),
        ]
        grid_rows.append({"values": cells})

    requests: list[dict] = []
    need = len(grid_rows) + 50
    if target["gridProperties"]["rowCount"] < need:
        requests.append({"updateSheetProperties": {
            "properties": {"sheetId": gid, "gridProperties": {"rowCount": need, "columnCount": 18}},
            "fields": "gridProperties.rowCount,gridProperties.columnCount",
        }})

    # очистить старое
    requests.append({"updateCells": {
        "range": {
            "sheetId": gid,
            "startRowIndex": 0,
            "endRowIndex": target["gridProperties"]["rowCount"],
            "startColumnIndex": 0,
            "endColumnIndex": 18,
        },
        "fields": "userEnteredValue,userEnteredFormat,textFormatRuns",
    }})

    for i in range(0, len(grid_rows), 500):
        chunk = grid_rows[i:i + 500]
        requests.append({"updateCells": {
            "rows": chunk,
            "fields": "userEnteredValue,userEnteredFormat,textFormatRuns",
            "start": {"sheetId": gid, "rowIndex": i, "columnIndex": 0},
        }})

    requests.append({"updateSheetProperties": {
        "properties": {"sheetId": gid, "gridProperties": {"frozenRowCount": 1}},
        "fields": "gridProperties.frozenRowCount",
    }})
    for i, w in enumerate(_COL_WIDTHS):
        requests.append({"updateDimensionProperties": {
            "range": {"sheetId": gid, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": w},
            "fields": "pixelSize",
        }})

    for start in range(0, len(requests), 15):
        svc.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID, body={"requests": requests[start:start + 15]}
        ).execute()


def tab_url() -> str:
    """Ссылка на вкладку — для TG-нотификации."""
    svc = _sheets_service()
    target = _ensure_tab(svc, SHEET_ID)
    return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid={target['sheetId']}"


# ===== «Компании без ИНН» — отдельный таб =====
# Сюда попадают ВСЕ компании, у которых реквизит без валидного RQ_INN
# (либо нет реквизита, либо он мусорный). Это самая большая категория
# для последующего обогащения через DaData/rusprofile.

NO_INN_TAB = "Компании без ИНН"
NO_INN_HEADERS = [
    "Компания", "Сделок", "Контактов", "Лидов", "Бренд",
    "Город", "Сайт", "Оборот", "Ответственный",
    "Создана", "Изменена", "company_id",
]
_NO_INN_COL_WIDTHS = [280, 70, 80, 60, 90, 110, 180, 100, 150, 100, 100, 80]


def _ensure_no_inn_tab(svc, sheet_id: str) -> dict:
    meta = svc.spreadsheets().get(spreadsheetId=sheet_id).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == NO_INN_TAB:
            return s["properties"]
    r = svc.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={
        "requests": [{"addSheet": {"properties": {
            "title": NO_INN_TAB,
            "gridProperties": {"rowCount": 100, "columnCount": 12, "frozenRowCount": 1},
        }}}]
    }).execute()
    return r["replies"][0]["addSheet"]["properties"]


def upload_no_inn(scored: list[ScoredCompany]) -> None:
    """Залить компании без валидного ИНН в отдельный таб.

    Фильтр: только empty_inn=True. Сортировка по дате создания (старые сверху).
    """
    rows = [s for s in scored if getattr(s, "empty_inn", False)]
    rows.sort(key=lambda s: s.date_create or "")

    svc = _sheets_service()
    target = _ensure_no_inn_tab(svc, SHEET_ID)
    gid = target["sheetId"]

    header_cells = [_cell(h, bold=True, bg=_HEADER) for h in NO_INN_HEADERS]
    grid_rows = [{"values": header_cells}]
    for r in rows:
        url = f"{PORTAL_BASE}/crm/company/details/{r.id}/"
        grid_rows.append({"values": [
            _cell(r.title or f"#{r.id}", link=url),
            _num_cell(r.n_deals),
            _num_cell(r.n_contacts),
            _num_cell(r.n_leads),
            _cell(r.uf_brand),
            _cell(r.uf_city),
            _cell(r.uf_site),
            _cell(r.uf_revenue),
            _cell(r.assignee),
            _cell(r.date_create),
            _cell(r.date_modify),
            _cell(r.id, h_align="RIGHT"),
        ]})

    requests: list[dict] = []
    need = len(grid_rows) + 50
    if target["gridProperties"]["rowCount"] < need:
        requests.append({"updateSheetProperties": {
            "properties": {"sheetId": gid, "gridProperties": {"rowCount": need, "columnCount": 12}},
            "fields": "gridProperties.rowCount,gridProperties.columnCount",
        }})

    requests.append({"updateCells": {
        "range": {
            "sheetId": gid,
            "startRowIndex": 0,
            "endRowIndex": target["gridProperties"]["rowCount"],
            "startColumnIndex": 0,
            "endColumnIndex": 12,
        },
        "fields": "userEnteredValue,userEnteredFormat,textFormatRuns",
    }})

    for i in range(0, len(grid_rows), 500):
        chunk = grid_rows[i:i + 500]
        requests.append({"updateCells": {
            "rows": chunk,
            "fields": "userEnteredValue,userEnteredFormat,textFormatRuns",
            "start": {"sheetId": gid, "rowIndex": i, "columnIndex": 0},
        }})

    requests.append({"updateSheetProperties": {
        "properties": {"sheetId": gid, "gridProperties": {"frozenRowCount": 1}},
        "fields": "gridProperties.frozenRowCount",
    }})
    for i, w in enumerate(_NO_INN_COL_WIDTHS):
        requests.append({"updateDimensionProperties": {
            "range": {"sheetId": gid, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": w},
            "fields": "pixelSize",
        }})

    for start in range(0, len(requests), 15):
        svc.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID, body={"requests": requests[start:start + 15]}
        ).execute()


def no_inn_tab_url() -> str:
    """Ссылка на таб «Компании без ИНН»."""
    svc = _sheets_service()
    target = _ensure_no_inn_tab(svc, SHEET_ID)
    return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid={target['sheetId']}"
