"""Модели для crm_company_enrich.

QueueRow — основной dataclass строки в company_enrich_queue.
INN utilities — валидация ИНН (10/12 цифр + опциональная контрольная сумма).
Classification — has_valid_inn / empty_inn / no_requisite.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from zoneinfo import ZoneInfo

from .state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

# ----- INN validation -----

INN_10 = re.compile(r"^\d{10}$")
INN_12 = re.compile(r"^\d{12}$")
INN_ANYWHERE = re.compile(r"\b(\d{10}(?:\d{2})?)\b")
INN_LABELED = re.compile(
    r"(?:ИНН|INN)\s*[:№]?\s*(\d{10,12})",
    re.IGNORECASE,
)


def is_valid_inn_format(inn: str | None) -> bool:
    """True если строка — 10 или 12 цифр (без проверки контрольной суммы)."""
    if not inn:
        return False
    s = str(inn).strip()
    return bool(INN_10.match(s) or INN_12.match(s))


def normalize_inn(raw: str | None) -> str | None:
    """Привести ИНН к canonical-форме: только цифры, длиной 10 или 12.

    Возвращает None для невалидных значений.
    """
    if raw is None:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if INN_10.match(digits) or INN_12.match(digits):
        return digits
    return None


def inn_checksum_ok(inn: str) -> bool:
    """Контрольная сумма ИНН (10 или 12 знаков).

    https://ru.wikipedia.org/wiki/Идентификационный_номер_налогоплательщика
    Не используется как блокирующий guard (есть валидные ИНН с
    «нестандартными» цифрами в legacy-данных), но удобно для тестов.
    """
    if not is_valid_inn_format(inn):
        return False
    digits = [int(ch) for ch in inn]
    if len(digits) == 10:
        weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        s = sum(w * d for w, d in zip(weights, digits[:9]))
        return digits[9] == (s % 11) % 10
    # len == 12
    w1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    w2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    c1 = (sum(w * d for w, d in zip(w1, digits[:10])) % 11) % 10
    c2 = (sum(w * d for w, d in zip(w2, digits[:11])) % 11) % 10
    return digits[10] == c1 and digits[11] == c2


# ----- Classification of company-state -----

class CompanyClass(str, Enum):
    HAS_VALID_INN = "has_valid_inn"        # реквизит есть и RQ_INN валидный → пропускаем
    EMPTY_INN = "empty_inn"                # реквизит есть, RQ_INN пустой/невалидный → enrich
    NO_REQUISITE = "no_requisite"          # реквизита нет вообще → enrich + create


def classify_company(requisites: list[dict]) -> CompanyClass:
    """Классификация компании по списку её реквизитов.

    requisites — список dict из crm.requisite.list, может быть пустой.
    """
    if not requisites:
        return CompanyClass.NO_REQUISITE
    for req in requisites:
        if is_valid_inn_format(req.get("RQ_INN")):
            return CompanyClass.HAS_VALID_INN
    return CompanyClass.EMPTY_INN


# ----- target_action для classify-стадии -----

class TargetAction(str, Enum):
    CREATE_REQ = "CREATE_REQ"               # ИНН не найден в Bitrix → создаём реквизит
    MERGE_INTO = "MERGE_INTO"               # ИНН найден у другой компании → готовим merge
    SKIP_ALREADY = "SKIP_ALREADY"           # ИНН уже принадлежит этой же компании
    SKIP_NO_INN = "SKIP_NO_INN"             # enrich не нашёл ИНН — действий нет


# ----- Headers и dataclass очереди -----

QUEUE_HEADERS = [
    "company_id",
    "🏢 Компания",                  # HYPERLINK на Bitrix card
    "domain",                        # нормализованный домен из deal-merge группы
    "n_losers",                      # число LOSER-сделок в deal-merge группе
    "n_total_transferable",          # activity+timeline+contact+sp из deal-merge
    "current_inn",                   # значение из RQ_INN (если есть реквизит); пусто для no_requisite
    "web",                           # WEB-поле компании
    "uf_inn_candidate",              # любое UF_* содержащее 10/12-значное число
    "n_deals",
    "n_contacts",
    "in_active_deal_merge",          # 0/1: пересекается ли с активной строкой merge_groups
    "status",                        # см. state.Status
    "priority",                      # n_deals + n_contacts (для сортировки)
    "discovered_inn",                # выход enrich_web
    "discovered_name",               # выход enrich_web
    "discovered_source",             # uf | web | title | rusprofile
    "target_action",                 # выход classify
    "merge_target_company_id",       # для MERGE_INTO — id компании-приёмника
    "approved",                      # 0/1 — выставляет mark-approved
    "approved_by",
    "approved_at",
    "last_action_at",
    "error_message",
]


@dataclass
class QueueRow:
    company_id: str
    company_name: str = ""
    domain: str | None = None
    n_losers: int = 0
    n_total_transferable: int = 0
    current_inn: str | None = None
    web: str | None = None
    uf_inn_candidate: str | None = None
    n_deals: int = 0
    n_contacts: int = 0
    in_active_deal_merge: bool = False
    status: Status = Status.NEW
    priority: int = 0
    discovered_inn: str | None = None
    discovered_name: str | None = None
    discovered_source: str | None = None
    target_action: TargetAction | None = None
    merge_target_company_id: str | None = None
    approved: bool = False
    approved_by: str | None = None
    approved_at: datetime | None = None
    last_action_at: datetime | None = None
    error_message: str | None = None
    company_link_formula: str = ""

    def to_sheet_row(self) -> list[str]:
        return [
            self.company_id,
            self.company_link_formula or self.company_name or "",
            self.domain or "",
            str(self.n_losers),
            str(self.n_total_transferable),
            self.current_inn or "",
            self.web or "",
            self.uf_inn_candidate or "",
            str(self.n_deals),
            str(self.n_contacts),
            _bool(self.in_active_deal_merge),
            self.status.value,
            str(self.priority),
            self.discovered_inn or "",
            self.discovered_name or "",
            self.discovered_source or "",
            self.target_action.value if self.target_action else "",
            self.merge_target_company_id or "",
            _bool(self.approved),
            self.approved_by or "",
            _dt(self.approved_at),
            _dt(self.last_action_at),
            self.error_message or "",
        ]

    @classmethod
    def from_sheet_row(cls, row: list[str], headers: list[str]) -> "QueueRow":
        v = {h: row[i] if i < len(row) else "" for i, h in enumerate(headers)}
        ta = v.get("target_action", "").strip() or None
        return cls(
            company_id=str(v.get("company_id", "")).strip(),
            company_name=v.get("🏢 Компания", "") or "",
            domain=_none_if_empty(v.get("domain", "")),
            n_losers=_int(v.get("n_losers", "")),
            n_total_transferable=_int(v.get("n_total_transferable", "")),
            current_inn=_none_if_empty(v.get("current_inn", "")),
            web=_none_if_empty(v.get("web", "")),
            uf_inn_candidate=_none_if_empty(v.get("uf_inn_candidate", "")),
            n_deals=_int(v.get("n_deals", "")),
            n_contacts=_int(v.get("n_contacts", "")),
            in_active_deal_merge=_bool_from(v.get("in_active_deal_merge", "")),
            status=Status(v.get("status", Status.NEW.value) or Status.NEW.value),
            priority=_int(v.get("priority", "")),
            discovered_inn=_none_if_empty(v.get("discovered_inn", "")),
            discovered_name=_none_if_empty(v.get("discovered_name", "")),
            discovered_source=_none_if_empty(v.get("discovered_source", "")),
            target_action=TargetAction(ta) if ta else None,
            merge_target_company_id=_none_if_empty(v.get("merge_target_company_id", "")),
            approved=_bool_from(v.get("approved", "")),
            approved_by=_none_if_empty(v.get("approved_by", "")),
            approved_at=_dt_from(v.get("approved_at", "")),
            last_action_at=_dt_from(v.get("last_action_at", "")),
            error_message=_none_if_empty(v.get("error_message", "")),
        )


@dataclass
class CompanyInventory:
    """Внутреннее представление состояния компании, собранное discover-стадией."""
    company_id: str
    title: str
    web: str | None = None
    uf_inn_candidate: str | None = None
    requisites: list[dict] = field(default_factory=list)
    n_deals: int = 0
    n_contacts: int = 0

    def classification(self) -> CompanyClass:
        return classify_company(self.requisites)

    def current_inn(self) -> str | None:
        for req in self.requisites:
            inn = normalize_inn(req.get("RQ_INN"))
            if inn:
                return inn
        return None


# ----- sheet-helpers -----

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


# ----- WEB field parsing -----

WEB_DELIMITERS = re.compile(r"[|;,\n]+")


def extract_web_url(web_field) -> str | None:
    """Достать URL из поля WEB Bitrix.

    Bitrix REST реально возвращает multi-field как list[dict]:
        [{"ID": "...", "VALUE": "https://example.ru", "VALUE_TYPE": "WORK"}, ...]

    Legacy/fixture-формат: строка "https://foo.ru|WORK\\nhttps://bar.ru|HOME".

    Возвращаем первое непустое значение либо None.
    """
    if not web_field:
        return None
    # Bitrix REST multi-field format: list of {"VALUE": "...", "VALUE_TYPE": "WORK"}
    if isinstance(web_field, list):
        for item in web_field:
            if isinstance(item, dict):
                url = (item.get("VALUE") or item.get("URL") or "").strip()
                if url:
                    return url
            elif item:
                url = str(item).split("|", 1)[0].strip()
                if url:
                    return url
        return None
    if isinstance(web_field, dict):
        url = (web_field.get("VALUE") or web_field.get("URL") or "").strip()
        return url or None
    # legacy/string fallback (kept for backward-compat with old fixtures)
    for chunk in WEB_DELIMITERS.split(str(web_field)):
        chunk = chunk.strip()
        if not chunk:
            continue
        url = chunk.split("|", 1)[0].strip()
        if url:
            return url
    return None


# ----- Cleanup discovered_name / bitrix_title before sending to crm.requisite.add -----

# Регэкспы — case-insensitive, без re.MULTILINE. Применяются последовательно,
# каждый «съедает» хвост строки целиком (`$`). Порядок важен: сначала длинные
# узкоспецифичные хвосты, потом более общие.
_NAME_CLEANUP_PATTERNS: tuple[re.Pattern[str], ...] = (
    # «- результаты поиска на Rusprofile.ru»
    re.compile(
        r"\s*[-—–]\s*результаты\s+поиска\s+на\s+Rusprofile\.ru\s*$",
        re.IGNORECASE,
    ),
    # «(ИНН 1234567890) адрес, официальный сайт и телефон»
    re.compile(
        r"\s*\(ИНН\s*\d{10,12}\)\s*адрес,?\s*официальный\s+сайт\s+и?\s*телефон\s*$",
        re.IGNORECASE,
    ),
    # «(ИНН 1234567890)»
    re.compile(r"\s*\(ИНН\s*\d{10,12}\)\s*$", re.IGNORECASE),
    # «адрес, официальный сайт и телефон» без скобок
    re.compile(
        r"\s+адрес,?\s+официальный\s+сайт\s+и?\s*телефон\s*$",
        re.IGNORECASE,
    ),
    # HTML-title trail после ` | ...` (режем от первого пайпа до конца)
    re.compile(r"\s+\|\s+.*$"),
)


def clean_company_name_for_requisite(raw: str | None) -> str | None:
    """Очистить строку discovered_name/bitrix_title перед записью в RQ_COMPANY_NAME_FULL.

    Шаги:
      1. None/пусто → None.
      2. html.unescape (&quot; → ", &amp; → &).
      3. Поочерёдное снятие известных SEO-хвостов (rusprofile, «адрес, официальный
         сайт и телефон», HTML-title trail после ` | `).
      4. Нормализация whitespace + проверка минимальной длины (>= 2 символа).

    Возвращает очищенную строку или None, если после чистки осталось < 2 символов.
    """
    if not raw:
        return None
    s = html.unescape(str(raw)).strip()
    if not s:
        return None
    for pattern in _NAME_CLEANUP_PATTERNS:
        s = pattern.sub("", s).strip()
    # Сжать повторяющиеся пробельные символы
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) < 2:
        return None
    return s


def find_uf_inn_candidate(company: dict) -> str | None:
    """Просканировать все UF_*-поля компании и вернуть первое валидное по формату ИНН."""
    for key, value in company.items():
        if not str(key).startswith("UF_"):
            continue
        # values могут быть list/dict/scalar
        for candidate in _iter_scalars(value):
            normalized = normalize_inn(candidate)
            if normalized:
                return normalized
    return None


def _iter_scalars(v):
    if v is None:
        return
    if isinstance(v, (list, tuple)):
        for item in v:
            yield from _iter_scalars(item)
    elif isinstance(v, dict):
        for item in v.values():
            yield from _iter_scalars(item)
    else:
        yield v


# ----- Brand classification (Belberry vs Acoola Team) -----
#
# Бизнес-правило: Belberry — медицинский сегмент (клиники, врачи,
# мед.диагностика, стоматология, косметология, аптеки и т.п.). Всё остальное —
# Acoola Team (автосервис, ритейл, IT, общепит и т.д.). При неоднозначности
# выбираем Belberry — наш основной сегмент.

# Медицинские маркеры. Сопоставляем подстрокой по lowercased blob: ловим как
# словоформы («клиника», «клиники», «клиник»), так и латинские fragments
# («clinic», «medic», «dent»). Порядок не важен — first-match.
_MEDICAL_KEYWORDS: tuple[str, ...] = (
    "клиник", "стомат", "стом-", "дент", "медиц", "мед-", "мед.ц", "мед.центр",
    "мед/", "врач", "диагност", "терапи", "космет", "эстетик", "здоров",
    "пластич", "омолож", "оптик", "аптек", "лабор", "рентген", "мрт", "узи",
    "ктг", "хирург", "онко", "кардио", "лор", "гастро", "гинеколог",
    "дерматолог", "эндокринол", "педиатр", "психиатр", "психолог", "неврол",
    "проктолог", "уролог",
    "doctor", "clinic", "medic", "health", "cosm", "dent", "surg", "derma",
    "ortho", "pharm", "healthcare", "hospital", "medspa", "beauty", "wellness",
    "youcanlive", "healthgarden", "oncocareclinic",
)

# Не-медицинские «сильные» маркеры. Срабатывают только если в blob НЕТ
# медицинских keywords (медицина перевешивает): иначе «Клиника-Сервис» вместе
# с «автосервис» выпадает в Acoola по ошибке.
_NON_MEDICAL_KEYWORDS: tuple[str, ...] = (
    "автосервис", "авторемонт", "мфо", "микрокредит", "кредит наличными",
    "лизинг", "страхование осаго", "недвижимость застройка", "ритейл",
    "общепит", "мебель", "реклама агентство",
)


def is_medical_company(
    bitrix_title: str | None = None,
    discovered_name: str | None = None,
    web: str | None = None,
    domain: str | None = None,
) -> bool:
    """Эвристика: True если компания относится к медицинскому сегменту (Belberry).

    Объединяет все non-None сигналы в lowercased text-blob и применяет
    keyword-фильтры:
      1. Если есть совпадение с медицинским keyword → True.
      2. Если есть non-medical strong keyword (и НЕТ медицинского) → False.
      3. Default → True (Belberry — наш основной сегмент).

    Caller сам мапит bool на UF_CRM_684FE59BA3C8C ID (2444 / 2442).
    """
    parts = [p for p in (bitrix_title, discovered_name, web, domain) if p]
    blob = " ".join(str(p) for p in parts).lower()
    if not blob.strip():
        return True  # пустые сигналы — default Belberry

    for kw in _MEDICAL_KEYWORDS:
        if kw in blob:
            return True

    for kw in _NON_MEDICAL_KEYWORDS:
        if kw in blob:
            return False

    return True
