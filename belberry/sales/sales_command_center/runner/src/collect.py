import base64
import json
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

from . import bx_client
from .timeutil import next_working_day

PORTAL_BASE = "https://belberrycrm.bitrix24.ru"
SEL_1048 = [
    "id",
    "title",
    "stageId",
    "createdTime",
    "createdBy",
    "updatedTime",
    "assignedById",
    "ufCrm16_1751009238",
    "ufCrm16_1751006460",
    "ufCrm16_1751006555",
    "ufCrm16_1751006126",
    "ufCrm16_1751470800",
    "ufCrm16Transcript",
    "parentId2",
    "opportunity",
]


def _range(day: date) -> tuple[str, str]:
    return f"{day.isoformat()}T00:00:00+03:00", f"{day.isoformat()}T23:59:59+03:00"


def _client(bx):
    return bx or bx_client


def _fetch_all(bx, method: str, params: dict[str, Any], idfield: str = "ID"):
    return _client(bx).fetch_all(method, params, idfield=idfield)


def collect_voximplant(target: date, bx=None) -> list[dict[str, Any]]:
    d0, d1 = _range(target)
    output: list[dict[str, Any]] = []
    last = 0
    client = _client(bx)

    # Жёсткий потолок страниц: если серверный фильтр CALL_START_DATE не
    # применится (наблюдалось на этом портале), без потолка цикл пейджит всю
    # историю звонков и подвешивает прогон. ~140 звонков/день → 3 страницы;
    # 200 страниц (10000 строк) — заведомо аномалия, прерываемся.
    pages = 0
    max_pages = 200
    while len(output) < 50000 and pages < max_pages:
        pages += 1
        response = client.call(
            "voximplant.statistic.get",
            {
                "FILTER": {
                    ">=CALL_START_DATE": d0,
                    "<=CALL_START_DATE": d1,
                    ">ID": last,
                },
                "SORT": "ID",
                "ORDER": "ASC",
                "start": -1,
            },
        )
        result = response.get("result") or []
        if not result:
            break
        output.extend(result)
        last = int(result[-1]["ID"])

    # Страховка: оставляем только звонки целевого дня, даже если серверный
    # фильтр отработал неточно (защита от «всей истории»).
    return [c for c in output if d0 <= str(c.get("CALL_START_DATE", "")) <= d1]


def collect_users(user_ids: set[Any], bx=None) -> dict[str, str]:
    users: dict[str, str] = {}
    client = _client(bx)
    for uid in sorted({str(uid) for uid in user_ids if uid not in (None, "", "0", 0)}):
        result = client.call("user.get", {"ID": uid}).get("result") or []
        if result:
            user = result[0]
            users[uid] = f"{user.get('LAST_NAME', '')} {user.get('NAME', '')}".strip() or uid
        else:
            users[uid] = uid
    return users


def _quote_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, urllib.parse.quote(parts.path), parts.query, "")
    )


def collect_photos(user_ids: set[Any], bx=None) -> dict[str, str]:
    photos: dict[str, str] = {}
    client = _client(bx)
    for uid in sorted({str(uid) for uid in user_ids if uid not in (None, "", "0", 0)}):
        result = client.call("user.get", {"ID": uid}).get("result") or []
        if not result or not result[0].get("PERSONAL_PHOTO"):
            continue
        url = _quote_url(result[0]["PERSONAL_PHOTO"])
        try:
            raw = urllib.request.urlopen(url, timeout=20).read()
            image_bytes = raw
            # sips есть только на macOS (локальная генерация фикстур). На Linux-
            # сервере его нет — тогда вшиваем исходное изображение как есть.
            if shutil.which("sips"):
                with tempfile.TemporaryDirectory() as tmpdir:
                    source = Path(tmpdir) / f"{uid}.img"
                    output = Path(tmpdir) / f"{uid}.jpg"
                    source.write_bytes(raw)
                    completed = subprocess.run(
                        [
                            "sips",
                            "-s",
                            "format",
                            "jpeg",
                            "-s",
                            "formatOptions",
                            "60",
                            "-Z",
                            "140",
                            str(source),
                            "--out",
                            str(output),
                        ],
                        capture_output=True,
                        check=False,
                    )
                    if completed.returncode == 0 and output.exists():
                        image_bytes = output.read_bytes()
            photos[uid] = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode()
        except Exception:
            continue
    return photos


def _collect_wazzup(deal_ids: set[Any], bx=None) -> dict[str, list[dict[str, Any]]]:
    client = _client(bx)
    output: dict[str, list[dict[str, Any]]] = {}
    for deal_id in sorted({str(i) for i in deal_ids if i not in (None, "", "0", 0)}):
        response = client.call(
            "crm.timeline.comment.list",
            {
                "filter": {"ENTITY_ID": deal_id, "ENTITY_TYPE": "deal", "AUTHOR_ID": 2358},
                "order": {"ID": "ASC"},
            },
        )
        result = response.get("result") or []
        if result:
            output[deal_id] = result
    return output


def collect_day(target: date, bx=None) -> dict[str, Any]:
    d0, d1 = _range(target)
    today = next_working_day(target)
    t0, t1 = _range(today)

    deals_created = _fetch_all(
        bx,
        "crm.deal.list",
        {
            "filter": {">=DATE_CREATE": d0, "<=DATE_CREATE": d1},
            "select": [
                "ID",
                "TITLE",
                "CATEGORY_ID",
                "STAGE_ID",
                "OPPORTUNITY",
                "ASSIGNED_BY_ID",
                "DATE_CREATE",
                "SOURCE_ID",
                "COMPANY_ID",
                "CONTACT_ID",
            ],
        },
    )
    deals_open = _fetch_all(
        bx,
        "crm.deal.list",
        {
            "filter": {"CLOSED": "N", "@CATEGORY_ID": [10, 50]},
            "select": [
                "ID",
                "TITLE",
                "CATEGORY_ID",
                "STAGE_ID",
                "OPPORTUNITY",
                "ASSIGNED_BY_ID",
                "DATE_CREATE",
                "MOVED_TIME",
                "LAST_ACTIVITY_TIME",
                "SOURCE_ID",
                "COMPANY_ID",
            ],
        },
    )
    stagehistory = _fetch_all(
        bx,
        "crm.stagehistory.list",
        {
            "entityTypeId": 2,
            "filter": {">=CREATED_TIME": d0, "<=CREATED_TIME": d1},
            "select": [
                "ID",
                "TYPE_ID",
                "OWNER_ID",
                "CREATED_TIME",
                "STAGE_SEMANTIC_ID",
                "STAGE_ID",
                "CATEGORY_ID",
            ],
        },
    )
    meet_day = _fetch_all(
        bx,
        "crm.item.list",
        {
            "entityTypeId": 1048,
            "filter": {">=ufCrm16_1751009238": d0, "<=ufCrm16_1751009238": d1},
            "select": SEL_1048,
        },
        idfield="id",
    )
    meet_created_day = _fetch_all(
        bx,
        "crm.item.list",
        {
            "entityTypeId": 1048,
            "filter": {">=createdTime": d0, "<=createdTime": d1},
            "select": SEL_1048,
        },
        idfield="id",
    )
    meet_today = _fetch_all(
        bx,
        "crm.item.list",
        {
            "entityTypeId": 1048,
            "filter": {">=ufCrm16_1751009238": t0, "<=ufCrm16_1751009238": t1},
            "select": SEL_1048,
        },
        idfield="id",
    )
    briefs = _fetch_all(
        bx,
        "crm.item.list",
        {
            "entityTypeId": 1056,
            "filter": {">=updatedTime": d0, "<=updatedTime": d1},
            "select": [
                "id",
                "title",
                "stageId",
                "createdTime",
                "updatedTime",
                "assignedById",
                "ufCrm20_1754044185200",
                "parentId2",
            ],
        },
        idfield="id",
    )
    kp = _fetch_all(
        bx,
        "crm.item.list",
        {
            "entityTypeId": 1106,
            "filter": {">=updatedTime": d0, "<=updatedTime": d1},
            "select": [
                "id",
                "title",
                "stageId",
                "createdTime",
                "updatedTime",
                "assignedById",
                "opportunity",
                "parentId2",
                "begindate",
            ],
        },
        idfield="id",
    )
    activities = _fetch_all(
        bx,
        "crm.activity.list",
        {
            "filter": {">=CREATED": d0, "<=CREATED": d1},
            "select": [
                "ID",
                "OWNER_ID",
                "OWNER_TYPE_ID",
                "TYPE_ID",
                "PROVIDER_ID",
                "PROVIDER_TYPE_ID",
                "SUBJECT",
                "COMPLETED",
                "RESPONSIBLE_ID",
                "CREATED",
                "DIRECTION",
                "START_TIME",
                "END_TIME",
            ],
        },
    )
    calls = collect_voximplant(target, bx)

    user_ids: set[Any] = set()
    for seq in [deals_created, deals_open]:
        user_ids.update(item.get("ASSIGNED_BY_ID") for item in seq)
    for seq in [meet_day, meet_created_day, meet_today, briefs, kp]:
        user_ids.update(item.get("assignedById") for item in seq)
        user_ids.update(item.get("createdBy") for item in seq)
    user_ids.update(item.get("PORTAL_USER_ID") for item in calls)

    deal_ids = {item.get("ID") for item in deals_created}
    deal_ids.update(item.get("parentId2") for item in [*meet_day, *meet_created_day, *meet_today])

    users = collect_users(user_ids, bx)
    return {
        "report_date": target.isoformat(),
        "deals_created": deals_created,
        "deals_open": deals_open,
        "stagehistory": stagehistory,
        "meet_day": meet_day,
        "meet_created_day": meet_created_day,
        "meet_today": meet_today,
        "briefs": briefs,
        "kp": kp,
        "activities": activities,
        "calls": calls,
        "users": users,
        "photos": collect_photos(set(users), bx),
        "wazzup": _collect_wazzup(deal_ids, bx),
    }


if __name__ == "__main__":
    bx_client.ensure_token_fresh()
    day = date(2026, 5, 29)
    data = collect_day(day)
    fixture_dir = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "2026-05-29"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    raw = {k: v for k, v in data.items() if k not in {"calls", "users", "photos"}}
    (fixture_dir / "raw.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2))
    (fixture_dir / "vox.json").write_text(json.dumps(data["calls"], ensure_ascii=False, indent=2))
    (fixture_dir / "users.json").write_text(json.dumps(data["users"], ensure_ascii=False, indent=2))
    (fixture_dir / "photos.json").write_text(json.dumps(data["photos"], ensure_ascii=False, indent=2))
