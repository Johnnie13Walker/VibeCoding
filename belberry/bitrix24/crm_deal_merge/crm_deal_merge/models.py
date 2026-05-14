"""Модели для crm_deal_merge."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from .state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

GROUP_HEADERS = [
    "company_id",
    "🏢 Компания",
    "winner_id",
    "ИНН",
    "domain",
    "n_total",
    "n_loser",
    "n_winner",
    "🟢 WINNER",
    "winner_stage",
    "winner_stage_name",
    "winner_closed",
    "loser_ids",
    "🔴 LOSER_1",
    "🔴 LOSER_2",
    "🔴 LOSER_3",
    "🔴 LOSER_4",
    "🔴 LOSER_5",
    "status",
    "approved",
    "approved_by",
    "approved_at",
    "n_activities_planned",
    "n_timeline_planned",
    "n_contacts_planned",
    "n_sp_planned",
    "last_action_at",
    "error_message",
    "backup_sheet",
]

INVENTORY_HEADERS = [
    "company_id",
    "loser_id",
    "entity_type",        # activity | timeline | contact | sp:<entityTypeId>
    "child_id",
    "child_subject",
    "details",            # PROVIDER_ID/COMPLETED для activity и т.п.
    "transferred",        # 1/0
    "transferred_at",
    "note",               # not_transferable, already_linked, ...
]

LOG_HEADERS = [
    "ts",
    "company_id",
    "stage",
    "action",
    "api_method",
    "ok",
    "duration_ms",
    "summary",
]


@dataclass
class Group:
    company_id: str
    company_name: str
    inn: str | None
    domain: str | None
    winner_id: str | None
    winner_stage: str | None
    winner_stage_name: str | None
    winner_closed: bool
    loser_ids: list[str]
    n_total: int = 0
    n_winner: int = 1
    # Для display-колонок храним готовые HYPERLINK-формулы Sheets:
    company_link_formula: str = ""
    winner_link_formula: str = ""
    loser_link_formulas: list[str] = field(default_factory=list)
    status: Status = Status.NEW
    approved: bool = False
    approved_by: str | None = None
    approved_at: datetime | None = None
    n_activities_planned: int = 0
    n_timeline_planned: int = 0
    n_contacts_planned: int = 0
    n_sp_planned: int = 0
    last_action_at: datetime | None = None
    error_message: str | None = None
    backup_sheet: str | None = None

    def to_sheet_row(self) -> list[str]:
        return [
            self.company_id,
            self.company_link_formula or self.company_name or "",
            self.winner_id or "",
            self.inn or "—",
            self.domain or "",
            str(self.n_total or (len(self.loser_ids) + (1 if self.winner_id else 0))),
            str(len(self.loser_ids)),
            str(self.n_winner),
            self.winner_link_formula or "",
            self.winner_stage or "",
            self.winner_stage_name or "",
            _bool(self.winner_closed),
            ",".join(self.loser_ids),
            *(_pad(self.loser_link_formulas, 5)),
            self.status.value,
            _bool(self.approved),
            self.approved_by or "",
            _dt(self.approved_at),
            str(self.n_activities_planned),
            str(self.n_timeline_planned),
            str(self.n_contacts_planned),
            str(self.n_sp_planned),
            _dt(self.last_action_at),
            self.error_message or "",
            self.backup_sheet or "",
        ]

    @classmethod
    def from_sheet_row(cls, row: list[str], headers: list[str]) -> "Group":
        v = {h: row[i] if i < len(row) else "" for i, h in enumerate(headers)}
        loser_ids = [x.strip() for x in v.get("loser_ids", "").split(",") if x.strip()]
        return cls(
            company_id=v["company_id"],
            # company_link рендерится в Sheets как текст TITLE — это нормально для отображения
            company_name=v.get("🏢 Компания", "") or "",
            inn=_none_if_empty(v.get("ИНН", "")),
            domain=_none_if_empty(v.get("domain", "")),
            winner_id=_none_if_empty(v.get("winner_id", "")),
            winner_stage=_none_if_empty(v.get("winner_stage", "")),
            winner_stage_name=_none_if_empty(v.get("winner_stage_name", "")),
            winner_closed=_bool_from(v.get("winner_closed", "")),
            loser_ids=loser_ids,
            n_total=_int(v.get("n_total", "")),
            n_winner=_int(v.get("n_winner", "")) or 1,
            status=Status(v.get("status", Status.NEW.value)),
            approved=_bool_from(v.get("approved", "")),
            approved_by=_none_if_empty(v.get("approved_by", "")),
            approved_at=_dt_from(v.get("approved_at", "")),
            n_activities_planned=_int(v.get("n_activities_planned", "")),
            n_timeline_planned=_int(v.get("n_timeline_planned", "")),
            n_contacts_planned=_int(v.get("n_contacts_planned", "")),
            n_sp_planned=_int(v.get("n_sp_planned", "")),
            last_action_at=_dt_from(v.get("last_action_at", "")),
            error_message=_none_if_empty(v.get("error_message", "")),
            backup_sheet=_none_if_empty(v.get("backup_sheet", "")),
        )


@dataclass
class InventoryRecord:
    company_id: str
    loser_id: str
    entity_type: str
    child_id: str
    child_subject: str
    details: str
    transferred: bool = False
    transferred_at: datetime | None = None
    note: str = ""

    def to_sheet_row(self) -> list[str]:
        return [
            self.company_id,
            self.loser_id,
            self.entity_type,
            self.child_id,
            (self.child_subject or "")[:200],
            self.details or "",
            _bool(self.transferred),
            _dt(self.transferred_at),
            self.note or "",
        ]


def _bool(v: bool) -> str:
    return "1" if v else "0"


def _bool_from(v: str) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y", "да", "✓"}


def _dt(v: datetime | None) -> str:
    if v is None:
        return ""
    if v.tzinfo is None:
        v = v.replace(tzinfo=MOSCOW_TZ)
    return v.astimezone(MOSCOW_TZ).isoformat(timespec="seconds")


def _dt_from(v: str) -> datetime | None:
    if not v:
        return None
    p = datetime.fromisoformat(v)
    return p.replace(tzinfo=MOSCOW_TZ) if p.tzinfo is None else p.astimezone(MOSCOW_TZ)


def _none_if_empty(v: str) -> str | None:
    s = str(v).strip()
    return s or None


def _int(v: str) -> int:
    s = str(v).strip()
    return int(s) if s else 0


def _pad(values: list[str], size: int) -> list[str]:
    return (values + [""] * size)[:size]
