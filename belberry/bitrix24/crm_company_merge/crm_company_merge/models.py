from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from .state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

GROUP_HEADERS = [
    "inn",
    "size",
    "risk_class",
    "status",
    "winner_id",
    "loser_ids",
    "approved",
    "approved_by",
    "approved_at",
    "actions_planned",
    "conflicts_count",
    "last_action_at",
    "error_message",
    "backup_sheet",
    "ui_link",
]

INVENTORY_HEADERS = [
    "inn",
    "loser_id",
    "entity_type",
    "child_id",
    "child_name",
    "owner",
    "details",
    "transferred",
    "transferred_at",
]

CONFLICT_HEADERS = [
    "inn",
    "field",
    "kind",
    "winner_value",
    "loser_value",
    "resolution",
    "applied",
]

LOG_ENTRY_HEADERS = [
    "ts",
    "inn",
    "stage",
    "action",
    "api_method",
    "request_hash",
    "response_summary",
    "ok",
    "duration_ms",
]


@dataclass
class Group:
    inn: str
    size: int
    risk_class: str | None
    status: Status
    winner_id: str | None
    loser_ids: list[str]
    approved: bool
    approved_by: str | None
    approved_at: datetime | None
    actions_planned: int
    conflicts_count: int
    last_action_at: datetime | None
    error_message: str | None
    backup_sheet: str | None
    ui_link: str | None

    def to_sheet_row(self) -> list[str]:
        return [
            self.inn,
            str(self.size),
            self.risk_class or "",
            self.status.value,
            self.winner_id or "",
            ",".join(self.loser_ids),
            _bool_to_sheet(self.approved),
            self.approved_by or "",
            _datetime_to_sheet(self.approved_at),
            str(self.actions_planned),
            str(self.conflicts_count),
            _datetime_to_sheet(self.last_action_at),
            self.error_message or "",
            self.backup_sheet or "",
            self.ui_link or "",
        ]

    @classmethod
    def from_sheet_row(cls, row: list[str], headers: list[str]) -> "Group":
        values = {header: row[index] if index < len(row) else "" for index, header in enumerate(headers)}
        loser_ids = [item.strip() for item in values.get("loser_ids", "").split(",") if item.strip()]
        return cls(
            inn=values.get("inn", ""),
            size=_int_from_sheet(values.get("size", "")),
            risk_class=_none_if_empty(values.get("risk_class", "")),
            status=Status(values.get("status", Status.NEW.value)),
            winner_id=_none_if_empty(values.get("winner_id", "")),
            loser_ids=loser_ids,
            approved=_bool_from_sheet(values.get("approved", "")),
            approved_by=_none_if_empty(values.get("approved_by", "")),
            approved_at=_datetime_from_sheet(values.get("approved_at", "")),
            actions_planned=_int_from_sheet(values.get("actions_planned", "")),
            conflicts_count=_int_from_sheet(values.get("conflicts_count", "")),
            last_action_at=_datetime_from_sheet(values.get("last_action_at", "")),
            error_message=_none_if_empty(values.get("error_message", "")),
            backup_sheet=_none_if_empty(values.get("backup_sheet", "")),
            ui_link=_none_if_empty(values.get("ui_link", "")),
        )


@dataclass
class InventoryRecord:
    inn: str
    loser_id: str
    entity_type: str
    child_id: str
    child_name: str
    owner: str
    details: str
    transferred: bool
    transferred_at: datetime | None

    def to_sheet_row(self) -> list[str]:
        return [
            self.inn,
            self.loser_id,
            self.entity_type,
            self.child_id,
            self.child_name,
            self.owner,
            self.details,
            _bool_to_sheet(self.transferred),
            _datetime_to_sheet(self.transferred_at),
        ]


@dataclass
class Conflict:
    inn: str
    field: str
    kind: str
    winner_value: str
    loser_value: str
    resolution: str
    applied: bool

    def to_sheet_row(self) -> list[str]:
        return [
            self.inn,
            self.field,
            self.kind,
            self.winner_value,
            self.loser_value,
            self.resolution,
            _bool_to_sheet(self.applied),
        ]


@dataclass
class LogEntry:
    ts: datetime
    inn: str
    stage: str
    action: str
    api_method: str
    request_hash: str
    response_summary: str
    ok: bool
    duration_ms: int

    def to_sheet_row(self) -> list[str]:
        return [
            _datetime_to_sheet(self.ts),
            self.inn,
            self.stage,
            self.action,
            self.api_method,
            self.request_hash,
            self.response_summary,
            _bool_to_sheet(self.ok),
            str(self.duration_ms),
        ]


def _bool_to_sheet(value: bool) -> str:
    return "1" if value else "0"


def _bool_from_sheet(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "да", "✓"}


def _datetime_to_sheet(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=MOSCOW_TZ)
    return value.astimezone(MOSCOW_TZ).isoformat(timespec="seconds")


def _datetime_from_sheet(value: str) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=MOSCOW_TZ)
    return parsed.astimezone(MOSCOW_TZ)


def _none_if_empty(value: str) -> str | None:
    value = str(value).strip()
    return value or None


def _int_from_sheet(value: str) -> int:
    raw = str(value).strip()
    return int(raw) if raw else 0
