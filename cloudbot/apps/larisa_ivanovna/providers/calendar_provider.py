"""Календарные адаптеры Ларисы Ивановны."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from cloudbot.providers.bitrix.bitrix_app_auth import BitrixAPIError, BitrixAppAuth

from ..schemas.calendar import CalendarDaySnapshot, CalendarEvent, CreateCalendarEventInput
from ..timezone import normalize_to_moscow, to_moscow_datetime

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


class CalendarProvider(ABC):
    @abstractmethod
    def get_day_snapshot(self, date_msk: str) -> CalendarDaySnapshot:
        raise NotImplementedError

    @abstractmethod
    def create_event(self, payload: CreateCalendarEventInput) -> dict[str, Any]:
        raise NotImplementedError


class NullCalendarProvider(CalendarProvider):
    def get_day_snapshot(self, date_msk: str) -> CalendarDaySnapshot:
        return CalendarDaySnapshot(
            date_msk=date_msk,
            source_available=False,
            limitation="Календарный provider еще не подключен к контуру Ларисы Ивановны.",
        )

    def create_event(self, payload: CreateCalendarEventInput) -> dict[str, Any]:
        return {
            "created": False,
            "event": None,
            "limitation": "Создание встреч недоступно, пока календарный provider не подключен.",
        }


class BitrixCalendarProvider(CalendarProvider):
    def __init__(self, env_data: Mapping[str, str] | None = None, *, timeout_sec: int = 20) -> None:
        if env_data is None:
            self.env_data = dict(os.environ)
        else:
            self.env_data = {str(key): str(value) for key, value in env_data.items()}
        self.timeout_sec = int(timeout_sec)
        env_payload = dict(self.env_data)
        env_payload.setdefault("BITRIX_TIMEOUT_SEC", str(self.timeout_sec))
        self.app_auth = BitrixAppAuth.from_env(env_payload)
        self._user_name_cache: dict[str, str] = {}

    def get_day_snapshot(self, date_msk: str) -> CalendarDaySnapshot:
        try:
            raw_events = self._load_calendar_events(date_msk)
        except Exception as error:  # noqa: BLE001
            return CalendarDaySnapshot(
                date_msk=date_msk,
                source_available=False,
                limitation=f"Bitrix calendar недоступен: {error}",
            )

        if raw_events is None:
            return CalendarDaySnapshot(
                date_msk=date_msk,
                source_available=False,
                limitation="BITRIX_APP_STATE_DIR или fixture календаря не заданы.",
            )

        fixture_payload = self._fixture_payload()
        if fixture_payload:
            profile = fixture_payload.get("profile") or {}
            owner_id = str(profile.get("ID") or profile.get("id") or "").strip()
        else:
            try:
                owner_id = self._profile_id() or ""
            except Exception:  # noqa: BLE001
                owner_id = ""
        meetings = [
            self._normalize_calendar_event(item, owner_id=owner_id)
            for item in raw_events
            if isinstance(item, dict)
        ]
        filtered = [
            item
            for item in meetings
            if item is not None and _same_day(item.start_at_msk, date_msk) and _should_include_in_brief(item)
        ]
        ordered = tuple(sorted(filtered, key=lambda item: item.start_at_msk))
        return CalendarDaySnapshot(
            date_msk=date_msk,
            meetings=ordered,
            source_available=True,
        )

    def create_event(self, payload: CreateCalendarEventInput) -> dict[str, Any]:
        fixture_file = self._fixture_file()
        if fixture_file is not None:
            event = CalendarEvent(
                id="fixture-created",
                title=payload.title,
                start_at_msk=payload.start_at_msk,
                end_at_msk=payload.end_at_msk or payload.start_at_msk,
                description=payload.description,
                participants=payload.participants,
                location=payload.location,
                join_url=payload.join_url,
                source="calendar-fixture",
            )
            return {
                "created": True,
                "event": event,
                "legacy": asdict(payload),
            }

        if not self.app_auth.is_configured():
            return {
                "created": False,
                "event": None,
                "limitation": "App OAuth state Bitrix не найден для создания встречи.",
            }

        try:
            owner_id = self._profile_id() or ""
            result = self.app_auth.call_method(
                "calendar.event.add",
                {
                    "type": "user",
                    "ownerId": owner_id,
                    "name": payload.title,
                    "description": payload.description,
                    "from": payload.start_at_msk,
                    "to": payload.end_at_msk or payload.start_at_msk,
                    "attendees": list(payload.participants),
                    "location": payload.location,
                    "skip_time": "N",
                },
            )
        except BitrixAPIError as error:
            return {
                "created": False,
                "event": None,
                "limitation": f"Ошибка calendar.event.add: {error.message}",
            }

        created_id = ""
        if isinstance(result, dict):
            created_id = str(result.get("ID") or result.get("id") or "").strip()
        elif result is not None:
            created_id = str(result).strip()

        event = CalendarEvent(
            id=created_id or "bitrix-created",
            title=payload.title,
            start_at_msk=payload.start_at_msk,
            end_at_msk=payload.end_at_msk or payload.start_at_msk,
            description=payload.description,
            participants=payload.participants,
            location=payload.location,
            join_url=payload.join_url,
            source="bitrix",
        )
        return {
            "created": True,
            "event": event,
            "legacy": result,
        }

    def _fixture_file(self) -> Path | None:
        candidates = (
            self.env_data.get("LARISA_BITRIX_FIXTURES_FILE"),
            self.env_data.get("BITRIX_FIXTURES_FILE"),
            self.env_data.get("BITRIX_CRM_FIXTURES_FILE"),
        )
        for candidate in candidates:
            raw = str(candidate or "").strip()
            if raw:
                path = Path(raw).expanduser()
                if path.exists():
                    return path
        return None

    def _fixture_payload(self) -> dict[str, Any]:
        fixture_file = self._fixture_file()
        if fixture_file is None:
            return {}
        payload = json.loads(fixture_file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        return payload

    def _profile_id(self) -> str:
        fixture_payload = self._fixture_payload()
        if fixture_payload:
            profile = fixture_payload.get("profile") or {}
            return str(profile.get("ID") or profile.get("id") or "").strip()
        explicit_owner = str(
            self.env_data.get("LARISA_BITRIX_USER_ID")
            or self.env_data.get("BITRIX_USER_ID")
            or self.env_data.get("BITRIX_CALENDAR_OWNER_ID")
            or ""
        ).strip()
        if explicit_owner:
            return explicit_owner
        result = self.app_auth.call_method("profile", {})
        if isinstance(result, dict):
            return str(result.get("ID") or result.get("id") or "").strip()
        return ""

    def _load_calendar_events(self, date_msk: str) -> list[dict[str, Any]] | None:
        fixture_payload = self._fixture_payload()
        if fixture_payload:
            events = fixture_payload.get("calendar_events") or []
            return [item for item in events if isinstance(item, dict)]

        if not self.app_auth.is_configured():
            return None

        start_at, end_at = _day_bounds(date_msk)
        owner_id = self._profile_id() or ""
        result = self.app_auth.call_method(
            "calendar.event.get",
            {
                "from": start_at,
                "to": end_at,
                "type": "user",
                "ownerId": owner_id,
            },
        )
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        if isinstance(result, dict):
            nested = result.get("items") or result.get("events") or []
            return [item for item in nested if isinstance(item, dict)]
        return []

    def _normalize_calendar_event(self, item: dict[str, Any], *, owner_id: str) -> CalendarEvent | None:
        start_at = str(item.get("DATE_FROM") or item.get("dateFrom") or item.get("from") or "").strip()
        end_at = str(item.get("DATE_TO") or item.get("dateTo") or item.get("to") or "").strip()
        if not start_at:
            return None
        start_timezone = _extract_source_timezone(item, ("TZ_FROM", "dateFromTimezone", "TIMEZONE", "timezone"))
        end_timezone = _extract_source_timezone(item, ("TZ_TO", "dateToTimezone", "TIMEZONE", "timezone")) or start_timezone
        participants = self._resolve_participants(item, owner_id=owner_id)
        return CalendarEvent(
            id=str(item.get("ID") or item.get("id") or "").strip(),
            title=str(item.get("NAME") or item.get("name") or item.get("TITLE") or "Без названия").strip(),
            start_at_msk=_normalize_calendar_datetime(start_at, source_timezone=start_timezone),
            end_at_msk=_normalize_calendar_datetime(end_at or start_at, source_timezone=end_timezone),
            status=_normalize_event_status(item),
            description=str(item.get("DESCRIPTION") or item.get("description") or "").strip(),
            participants=participants,
            location=str(item.get("LOCATION") or item.get("location") or "").strip(),
            join_url=str(item.get("MEETING") or item.get("join_url") or "").strip(),
            source="bitrix",
        )

    def _resolve_participants(self, item: Mapping[str, Any], *, owner_id: str) -> tuple[str, ...]:
        participant_ids = _extract_participant_ids(item)
        if not participant_ids:
            return tuple()
        normalized_owner = owner_id.strip()
        resolved: list[str] = []
        seen: set[str] = set()
        for participant_id in participant_ids:
            normalized_id = participant_id.strip()
            if not normalized_id or normalized_id == normalized_owner:
                continue
            name = self._load_user_name(normalized_id)
            candidate = name.strip()
            if not candidate:
                continue
            dedupe_key = candidate.lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            resolved.append(candidate)
        return tuple(resolved)

    def _load_user_name(self, user_id: str) -> str:
        cached = self._user_name_cache.get(user_id)
        if cached is not None:
            return cached
        result = self.app_auth.call_method("user.get", {"FILTER": {"ID": [user_id]}})
        rows = result if isinstance(result, list) else result.get("result") if isinstance(result, dict) else []
        name = ""
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            if row.get("ACTIVE") is False or str(row.get("ACTIVE") or "").upper() == "N":
                continue
            first_name = str(row.get("NAME") or row.get("name") or "").strip()
            last_name = str(row.get("LAST_NAME") or row.get("last_name") or "").strip()
            name = " ".join(part for part in (first_name, last_name) if part).strip()
            if name:
                break
        self._user_name_cache[user_id] = name
        return name


def _day_bounds(date_msk: str) -> tuple[str, str]:
    day = datetime.strptime(date_msk, "%d.%m.%Y").replace(tzinfo=MOSCOW_TZ)
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    end = day.replace(hour=23, minute=59, second=59, microsecond=0)
    return start.isoformat(), end.isoformat()


def _same_day(value: str, date_msk: str) -> bool:
    parsed = to_moscow_datetime(value)
    if parsed is None:
        return value.startswith(datetime.strptime(date_msk, "%d.%m.%Y").date().isoformat())
    return parsed.strftime("%d.%m.%Y") == date_msk


def _extract_source_timezone(item: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def _normalize_calendar_datetime(value: str, *, source_timezone: str) -> str:
    normalized = normalize_to_moscow(value, source_timezone=source_timezone)
    if normalized != str(value or "").strip():
        return normalized
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            parsed = datetime.strptime(str(value).strip(), fmt).replace(
                tzinfo=ZoneInfo(source_timezone) if source_timezone else MOSCOW_TZ
            )
            return parsed.astimezone(MOSCOW_TZ).isoformat()
        except ValueError:
            continue
    return str(value or "").strip()


def _extract_participant_ids(item: Mapping[str, Any]) -> tuple[str, ...]:
    raw_values: list[str] = []
    for key in ("ATTENDEES_CODES", "attendeesCodes", "ATTENDEES", "attendees"):
        value = item.get(key)
        if isinstance(value, str):
            raw_values.extend(part.strip() for part in value.split(",") if part.strip())
        elif isinstance(value, (list, tuple)):
            raw_values.extend(str(part).strip() for part in value if str(part).strip())
    normalized: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        prepared = value.strip()
        if prepared.upper().startswith("U") and prepared[1:].isdigit():
            prepared = prepared[1:]
        if not prepared or not prepared.isdigit():
            continue
        if prepared in seen:
            continue
        seen.add(prepared)
        normalized.append(prepared)
    return tuple(normalized)


def _normalize_event_status(item: Mapping[str, Any]) -> str:
    raw_status = str(item.get("MEETING_STATUS") or item.get("meetingStatus") or "").strip().upper()
    is_meeting = bool(item.get("IS_MEETING") or item.get("isMeeting"))
    if not is_meeting and raw_status == "H":
        return "owner"
    if raw_status in {"Y", "Q"}:
        return "confirmed"
    if raw_status == "H":
        return "owner"
    if raw_status == "N":
        return "declined"
    if raw_status:
        return raw_status.lower()
    return "confirmed"


def _should_include_in_brief(event: CalendarEvent) -> bool:
    if event.status in {"declined", "cancelled"}:
        return False
    return True
