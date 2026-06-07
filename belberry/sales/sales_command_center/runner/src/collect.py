import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests

from . import bx_client
from .chat_attribution import attribute_dialogs
from .timeutil import next_working_day

PORTAL_BASE = "https://belberrycrm.bitrix24.ru"
# Стадия проведённой встречи (SP 1048). NEW = ожидание, FAIL = отменена/перенесена —
# их НЕ считаем проведёнными и НЕ анализируем.
MEETING_HELD_STAGE = "DT1048_24:SUCCESS"

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
    if os.environ.get("SCC_COLLECT_PROGRESS") != "1":
        return _client(bx).fetch_all(method, params, idfield=idfield)
    started = time.monotonic()
    entity = params.get("entityTypeId", "")
    filter_keys = ",".join(sorted((params.get("filter") or {}).keys()))
    print(
        f"collect_day START fetch_all method={method} entityTypeId={entity} idfield={idfield} filter={filter_keys}",
        flush=True,
    )
    rows = _client(bx).fetch_all(method, params, idfield=idfield)
    print(
        f"collect_day DONE fetch_all method={method} entityTypeId={entity} count={len(rows)} sec={time.monotonic() - started:.1f}",
        flush=True,
    )
    return rows


def _progress_step(name: str, fn):
    if os.environ.get("SCC_COLLECT_PROGRESS") != "1":
        return fn()
    started = time.monotonic()
    print(f"collect_day START {name}", flush=True)
    value = fn()
    count = len(value) if hasattr(value, "__len__") else "?"
    print(f"collect_day DONE {name} count={count} sec={time.monotonic() - started:.1f}", flush=True)
    return value


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
        if isinstance(response, dict) and response.get("error") and "result" not in response:
            raise RuntimeError(f"voximplant.statistic.get failed: {response.get('error')}")
        result = response.get("result") or []
        if not result:
            break
        output.extend(result)
        last = int(result[-1]["ID"])

    # Страховка: отбрасываем звонки, чья дата ЕСТЬ и вне целевого дня (защита от
    # «всей истории» при неточном серверном фильтре). Записи без CALL_START_DATE
    # не трогаем — судить не по чему.
    return [c for c in output if not c.get("CALL_START_DATE") or d0 <= str(c["CALL_START_DATE"]) <= d1]


def _clean_uids(user_ids: set[Any]) -> list[str]:
    return sorted({str(uid) for uid in user_ids if uid not in (None, "", "0", 0)})


def _quote_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, urllib.parse.quote(parts.path), parts.query, "")
    )


def _resize_jpeg_sips(raw: bytes, uid: str) -> bytes | None:
    if not shutil.which("sips"):
        return None
    with tempfile.TemporaryDirectory() as tmpdir:
        source = Path(tmpdir) / f"{uid}.img"
        output = Path(tmpdir) / f"{uid}.jpg"
        source.write_bytes(raw)
        completed = subprocess.run(
            ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "60",
             "-Z", "140", str(source), "--out", str(output)],
            capture_output=True,
            check=False,
        )
        if completed.returncode == 0 and output.exists():
            return output.read_bytes()
    return None


def _resize_jpeg_pillow(raw: bytes) -> bytes | None:
    try:
        from io import BytesIO

        from PIL import Image

        img = Image.open(BytesIO(raw)).convert("RGB")
        img.thumbnail((140, 140))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=60)
        return buf.getvalue()
    except Exception:
        return None


def _encode_photo(photo_url: str, uid: str) -> str | None:
    url = _quote_url(photo_url)
    raw = None
    for _ in range(2):
        try:
            response = requests.get(url, timeout=(3, 6), headers={"User-Agent": "SCC/1.0"})
            if response.status_code == 200 and response.content:
                raw = response.content
                break
        except Exception:
            time.sleep(0.5)
    if raw is None:
        return None
    # КРИТИЧНО сжимать: иначе сырые аватары Bitrix (~1 МБ каждый) раздувают
    # отчёт до мегабайтов. macOS → sips (генерация фикстур), Linux/прод →
    # Pillow (140px, JPEG q60). Без сжатия фото НЕ вшиваем (вернём None).
    image_bytes = _resize_jpeg_sips(raw, uid) or _resize_jpeg_pillow(raw)
    if image_bytes is None:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode()


def _photo_store_path(uid: str) -> Path | None:
    # Серверное фото-хранилище: SCC_PHOTO_DIR/<uid>.jpg. Источник истины для
    # аватаров — читаем оттуда (надёжно, без зависимости от Bitrix/сети). Если
    # у сотрудника нет фото в Bitrix — кладём файл руками один раз.
    base = os.environ.get("SCC_PHOTO_DIR")
    return Path(base) / f"{uid}.jpg" if base else None


def _read_stored_photo(uid: str) -> str | None:
    path = _photo_store_path(uid)
    if not path or not path.exists():
        return None
    raw = path.read_bytes()
    if not raw:
        return None
    # сжимаем при чтении: ручной аплоад может быть любого размера/формата
    image_bytes = _resize_jpeg_sips(raw, uid) or _resize_jpeg_pillow(raw) or raw
    return "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode()


def _write_stored_photo(uid: str, data_uri: str) -> None:
    path = _photo_store_path(uid)
    if not path:
        return
    try:
        b64 = data_uri.split(",", 1)[1]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(b64))
    except Exception:
        pass


def collect_users_and_photos(
    user_ids: set[Any], bx=None
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Один user.get на пользователя: имя + роль (WORK_POSITION) + аватар.

    Фото: сначала из серверного хранилища (SCC_PHOTO_DIR), иначе тянем из Bitrix
    (параллельно) и кэшируем туда же — следующие прогоны не зависят от сети.
    """
    names: dict[str, str] = {}
    photos: dict[str, str] = {}
    roles: dict[str, str] = {}
    photo_jobs: dict[str, str] = {}
    client = _client(bx)
    for uid in _clean_uids(user_ids):
        stored = _read_stored_photo(uid)
        if stored:
            photos[uid] = stored  # из хранилища — приоритетно
        result = client.call("user.get", {"ID": uid}).get("result") or []
        if not result:
            names[uid] = uid
            continue
        user = result[0]
        names[uid] = f"{user.get('LAST_NAME', '')} {user.get('NAME', '')}".strip() or uid
        position = (user.get("WORK_POSITION") or "").strip()
        if position:
            roles[uid] = position
        if uid not in photos:
            photo_url = user.get("PERSONAL_PHOTO")
            if photo_url:
                photo_jobs[uid] = photo_url
    if photo_jobs:
        with ThreadPoolExecutor(max_workers=min(6, len(photo_jobs))) as pool:
            futures = {pool.submit(_encode_photo, url, uid): uid for uid, url in photo_jobs.items()}
            for future in as_completed(futures):
                uid = futures[future]
                try:
                    encoded = future.result()
                except Exception:
                    encoded = None
                if encoded:
                    photos[uid] = encoded
                    _write_stored_photo(uid, encoded)  # кэшируем для след. прогонов
    return names, photos, roles


def _collect_wazzup(deal_ids: set[Any], bx=None, cap: int = 600) -> dict[str, list[dict[str, Any]]]:
    # crm.timeline.comment.list умеет фильтровать только по конкретной сущности →
    # один вызов на сделку. cap страхует от runaway, если воронка очень большая.
    client = _client(bx)
    output: dict[str, list[dict[str, Any]]] = {}
    for deal_id in sorted({str(i) for i in deal_ids if i not in (None, "", "0", 0)})[:cap]:
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


def collect_employees(bx=None, max_pages: int = 60) -> dict[str, str]:
    """Полный справочник сотрудников Bitrix: id → «Фамилия Имя».

    Нужен для атрибуции Wazzup-чатов фактическому отправителю (подпись в тексте
    сообщения), а не ответственному за сделку — так чаты попадают в «Опер» тому,
    кто реально вёл переписку, включая ТМ (они часто не ответственные).
    """
    client = _client(bx)
    out: dict[str, str] = {}
    start = 0
    for _ in range(max_pages):
        resp = client.call("user.get", {"start": start, "ADMIN_MODE": "Y"})
        result = resp.get("result") or []
        for user in result:
            name = f"{user.get('LAST_NAME') or ''} {user.get('NAME') or ''}".strip()
            uid = user.get("ID")
            if name and uid is not None:
                out[str(uid)] = name
        nxt = resp.get("next")
        if not result or nxt is None:
            break
        start = nxt
    return out


ABSENCE_NAME_HINTS = ("отпуск", "отгул", "отсутств", "больнич", "командир", "vacation")


def collect_absences(user_ids: set[Any], target: date, bx=None) -> dict[str, str]:
    """Кто в отпуске/отсутствует — из «Графика отсутствий» Bitrix.

    calendar.accessibility.get возвращает события доступности; отпуск приходит с
    ACCESSIBILITY="absent" (или календарным событием с «отпуск» в названии). Берём
    дату окончания (DATE_TO) → «в отпуске до DD.MM». Отдельного absence-метода в
    REST портала нет, этого достаточно.
    """
    client = _client(bx)
    ids = sorted({str(u) for u in user_ids if u not in (None, "", "0", 0)})
    if not ids:
        return {}
    response = client.call(
        "calendar.accessibility.get",
        {"users": ids, "from": target.isoformat(), "to": (target + timedelta(days=21)).isoformat()},
    )
    result = response.get("result") if isinstance(response, dict) else None
    if not isinstance(result, dict):
        return {}
    out: dict[str, str] = {}
    for uid, events in result.items():
        best_key, until = (0, 0, 0), None
        for ev in events or []:
            from_hr = ev.get("FROM_HR") in (True, "true", "True", "1", 1)
            acc = str(ev.get("ACCESSIBILITY") or "").lower()
            name = str(ev.get("NAME") or "").lower()
            if not (from_hr or acc == "absent" or any(h in name for h in ABSENCE_NAME_HINTS)):
                continue
            dt_to = ev.get("DT_TO") or ev.get("DATE_TO")  # HR-отсутствия: DT_TO «05.06.2026»
            key = _absence_date_key(dt_to)
            if key >= best_key:
                best_key, until = key, dt_to
        if until:
            out[str(uid)] = str(until)
    return out


def _absence_date_key(dt: Any) -> tuple[int, int, int]:
    """«05.06.2026 ...» → (2026, 6, 5) для сравнения дат окончания."""
    head = str(dt or "").split()[0]
    parts = head.split(".")
    try:
        return (int(parts[2]), int(parts[1]), int(parts[0])) if len(parts) >= 3 else (0, 0, 0)
    except (ValueError, IndexError):
        return (0, 0, 0)


REJECTION_STAGES = {"C10:LOSE", "C50:APOLOGY"}
# «Оплата получена» = переход сделки в УСПЕХ воронки Продажи (CAT 10). ТМ-воронку
# (C50:WON «успех») в оплаты НЕ берём — это передача в продажи, а не деньги.
WON_STAGES = {"C10:WON"}


def collect_rejected_deals(stagehistory: list[dict[str, Any]], bx=None) -> list[dict[str, Any]]:
    """Названия отклонённых сегодня сделок (они закрыты → не в deals_open/created),
    чтобы в «Отказах» был домен, а не «Сделка <id>»."""
    ids = sorted(
        {
            str(h.get("OWNER_ID"))
            for h in stagehistory
            if h.get("STAGE_ID") in REJECTION_STAGES and h.get("OWNER_ID")
        }
    )
    if not ids:
        return []
    return _fetch_all(
        bx,
        "crm.deal.list",
        {"filter": {"@ID": ids}, "select": ["ID", "TITLE", "ASSIGNED_BY_ID", "OPPORTUNITY", "UF_CRM_1771495464"]},
    )


def collect_won_deals(stagehistory: list[dict[str, Any]], bx=None) -> list[dict[str, Any]]:
    """Выигранные сегодня сделки (переход в C10:WON) — для метрики «оплаты, шт+руб»
    и среднего чека. Сумма берётся из OPPORTUNITY сделки."""
    ids = sorted(
        {
            str(h.get("OWNER_ID"))
            for h in stagehistory
            if h.get("STAGE_ID") in WON_STAGES and h.get("OWNER_ID")
        }
    )
    if not ids:
        return []
    return _fetch_all(
        bx,
        "crm.deal.list",
        {"filter": {"@ID": ids}, "select": ["ID", "TITLE", "ASSIGNED_BY_ID", "OPPORTUNITY"]},
    )


def collect_entered_deals(stagehistory: list[dict[str, Any]], bx=None) -> list[dict[str, Any]]:
    """Сделки, ВОШЕДШИЕ в воронку Продажи за день — есть запись C10:NEW в истории
    стадий (дата-точно, таймстампы неизменны). Тянем ответственного и дату создания:
    в transform вход = создана в этот же день, холод = создана раньше (переведена из ТМ).
    Не опираемся на текущий CATEGORY_ID сделки — он мог измениться после перевода."""
    ids = sorted(
        {
            str(h.get("OWNER_ID"))
            for h in stagehistory
            if str(h.get("CATEGORY_ID")) == "10" and h.get("STAGE_ID") == "C10:NEW" and h.get("OWNER_ID")
        }
    )
    if not ids:
        return []
    return _fetch_all(
        bx, "crm.deal.list", {"filter": {"@ID": ids}, "select": ["ID", "ASSIGNED_BY_ID", "DATE_CREATE"]}
    )


def collect_flow_day(target: date, bx=None) -> dict[str, Any]:
    """Лёгкий сбор ТОЛЬКО потоковых данных для backfill истории: сделки/встречи/
    КП/брифы/звонки/письма/оплаты за конкретный день. БЕЗ снимка воронки
    (deals_snapshot нельзя восстановить за прошлое), без LLM-анализа, без фото/
    справочников/wazzup. Все фильтры — по дате целевого дня, поэтому историю
    можно перегнать задним числом. Идемпотентно через build_db_rows + upsert."""
    d0, d1 = _range(target)
    deals_created = _fetch_all(
        bx,
        "crm.deal.list",
        {
            "filter": {">=DATE_CREATE": d0, "<=DATE_CREATE": d1},
            "select": [
                "ID", "TITLE", "CATEGORY_ID", "STAGE_ID", "OPPORTUNITY",
                "ASSIGNED_BY_ID", "DATE_CREATE", "SOURCE_ID", "COMPANY_ID",
                "CONTACT_ID", "UF_CRM_1771495464",
            ],
        },
    )
    stagehistory = _fetch_all(
        bx,
        "crm.stagehistory.list",
        {
            "entityTypeId": 2,
            "filter": {">=CREATED_TIME": d0, "<=CREATED_TIME": d1},
            "select": ["ID", "TYPE_ID", "OWNER_ID", "CREATED_TIME", "STAGE_SEMANTIC_ID", "STAGE_ID", "CATEGORY_ID"],
        },
    )
    meet_day = _fetch_all(
        bx,
        "crm.item.list",
        {"entityTypeId": 1048, "filter": {">=ufCrm16_1751009238": d0, "<=ufCrm16_1751009238": d1, "stageId": MEETING_HELD_STAGE}, "select": SEL_1048},
        idfield="id",
    )
    meet_created_day = _fetch_all(
        bx,
        "crm.item.list",
        {"entityTypeId": 1048, "filter": {">=createdTime": d0, "<=createdTime": d1}, "select": SEL_1048},
        idfield="id",
    )
    briefs = _fetch_all(
        bx,
        "crm.item.list",
        {
            "entityTypeId": 1056,
            "filter": {">=updatedTime": d0, "<=updatedTime": d1},
            "select": ["id", "title", "stageId", "createdTime", "updatedTime", "assignedById", "ufCrm20_1754044185200", "parentId2"],
        },
        idfield="id",
    )
    kp = _fetch_all(
        bx,
        "crm.item.list",
        {
            "entityTypeId": 1106,
            "filter": {">=updatedTime": d0, "<=updatedTime": d1},
            "select": ["id", "title", "stageId", "createdTime", "updatedTime", "assignedById", "opportunity", "parentId2", "begindate"],
        },
        idfield="id",
    )
    activities = _fetch_all(
        bx,
        "crm.activity.list",
        {
            "filter": {">=CREATED": d0, "<=CREATED": d1},
            "select": ["ID", "OWNER_ID", "OWNER_TYPE_ID", "TYPE_ID", "PROVIDER_ID", "PROVIDER_TYPE_ID", "SUBJECT", "COMPLETED", "RESPONSIBLE_ID", "AUTHOR_ID", "CREATED", "DIRECTION", "START_TIME", "END_TIME"],
        },
    )
    calls = collect_voximplant(target, bx)
    return {
        "report_date": target.isoformat(),
        "deals_created": deals_created,
        "deals_open": [],  # снимок за прошлое не восстанавливаем
        "stagehistory": stagehistory,
        "won_deals": collect_won_deals(stagehistory, bx),
        "entered_deals": collect_entered_deals(stagehistory, bx),
        "meet_day": meet_day,
        "meet_created_day": meet_created_day,
        "meet_today": [],
        "briefs": briefs,
        "kp": kp,
        "activities": activities,
        "calls": calls,
        "wazzup": {},
        "messenger_dialogs": {},
    }


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
                "UF_CRM_1771495464",  # причина отказа (8588 = СПАМ)
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
            "filter": {">=ufCrm16_1751009238": d0, "<=ufCrm16_1751009238": d1, "stageId": MEETING_HELD_STAGE},
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
                "AUTHOR_ID",
                "CREATED",
                "DIRECTION",
                "START_TIME",
                "END_TIME",
            ],
        },
    )
    calls = _progress_step("voximplant", lambda: collect_voximplant(target, bx))

    user_ids: set[Any] = set()
    for seq in [deals_created, deals_open]:
        user_ids.update(item.get("ASSIGNED_BY_ID") for item in seq)
    for seq in [meet_day, meet_created_day, meet_today, briefs, kp]:
        user_ids.update(item.get("assignedById") for item in seq)
        user_ids.update(item.get("createdBy") for item in seq)
    user_ids.update(item.get("PORTAL_USER_ID") for item in calls)

    deal_ids = {item.get("ID") for item in deals_created}
    deal_ids.update(item.get("parentId2") for item in [*meet_day, *meet_created_day, *meet_today])
    # Wazzup собираем и по зависшим (open) сделкам: иначе их last_contact игнорирует
    # переписку и «дни без контакта» завышаются.
    deal_ids.update(item.get("ID") for item in deals_open)

    users, photos, user_roles = _progress_step(
        "users_and_photos", lambda: collect_users_and_photos(user_ids, bx)
    )
    employees = _progress_step("employees", lambda: collect_employees(bx))
    wazzup = _progress_step("wazzup", lambda: _collect_wazzup(deal_ids, bx))
    # Чаты атрибутируем по подписи отправителя в тексте сообщения (chat_attribution),
    # а не по ответственному за сделку — иначе переписка ТМ не попадает в «Опер».
    messenger_dialogs = attribute_dialogs(wazzup, employees, d0, d1)
    return {
        "user_roles": user_roles,
        "messenger_dialogs": messenger_dialogs,
        "absences": _progress_step("absences", lambda: collect_absences(user_ids, target, bx)),
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
        "photos": photos,
        "rejected_deals": _progress_step("rejected_deals", lambda: collect_rejected_deals(stagehistory, bx)),
        "won_deals": _progress_step("won_deals", lambda: collect_won_deals(stagehistory, bx)),
        "entered_deals": _progress_step("entered_deals", lambda: collect_entered_deals(stagehistory, bx)),
        "wazzup": wazzup,
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
