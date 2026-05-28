"""Политика выбора основной сделки при дедупликации Bitrix24."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Iterable, Mapping, Sequence

ATTRIBUTION_FIELDS = (
    "SOURCE_ID",
    "SOURCE_DESCRIPTION",
    "UTM_SOURCE",
    "UTM_MEDIUM",
    "UTM_CAMPAIGN",
    "UTM_CONTENT",
    "UTM_TERM",
)

DEFAULT_DOMAIN_FIELDS = (
    "domain",
    "domain_key",
    "site",
    "website",
    "url",
    "DOMAIN",
    "SITE",
    "WEBSITE",
    "URL",
)

_DOMAIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?([a-z0-9][a-z0-9-]*(?:\.[a-z0-9][a-z0-9-]*)*\.[a-z]{2,})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DealDuplicatePolicyConfig:
    """Настройки, которые можно уточнить после live-подтверждения Bitrix stage map."""

    sales_category_ids: frozenset[str] = frozenset({"10"})
    sales_category_markers: tuple[str, ...] = ("продажи", "sales")
    telemarketing_category_markers: tuple[str, ...] = ("телемаркетинг", "telemarketing", "tm")
    protected_category_markers: tuple[str, ...] = ("аккаунтинг", "аккаунт", "account", "retention")
    success_stage_markers: tuple[str, ...] = (
        "успех",
        "успешно реализовано",
        "сделка успешна",
        "получена оплата",
    )
    lost_stage_markers: tuple[str, ...] = (
        "отвал",
        "отказ",
        "провал",
        "проигран",
        "спам",
        "нецелев",
        "lose",
        "fail",
    )
    deferred_stage_markers: tuple[str, ...] = ("отложено", "отложенный спрос")
    active_client_stage_markers: tuple[str, ...] = ("действующий клиент", "текущий клиент")


@dataclass(frozen=True)
class DealContext:
    """Нормализованная сделка для policy-layer."""

    id: str
    title: str = ""
    category_id: str = ""
    category_name: str = ""
    stage_id: str = ""
    stage_name: str = ""
    semantic_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    product_signature: str = ""
    attribution: Mapping[str, str] = field(default_factory=dict)
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DealMergeAction:
    """Одна операция объединения в рамках группы дублей."""

    target_id: str
    duplicate_ids: tuple[str, ...]
    reason: str
    attribution_source_id: str | None
    attribution_updates: Mapping[str, str]


@dataclass(frozen=True)
class DealDuplicatePlan:
    """План по группе сделок одного домена."""

    domain_key: str | None
    actions: tuple[DealMergeAction, ...]
    protected_ids: tuple[str, ...] = ()
    skipped_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def has_actions(self) -> bool:
        return bool(self.actions)


def normalize_label(value: Any) -> str:
    raw = str(value or "").strip().casefold().replace("ё", "е")
    return " ".join(raw.split())


def infer_domain_key(deal: Mapping[str, Any], *, domain_fields: Sequence[str] = DEFAULT_DOMAIN_FIELDS) -> str | None:
    """Достаёт домен из явного поля или из названия сделки."""

    raw = _raw_mapping(deal)
    for field_name in domain_fields:
        value = _pick(deal, field_name, raw=raw)
        normalized = _normalize_domain(value)
        if normalized:
            return normalized

    return _normalize_domain(_pick(deal, "title", "TITLE", raw=raw))


def group_deals_by_domain(
    deals: Iterable[Mapping[str, Any]],
    *,
    domain_fields: Sequence[str] = DEFAULT_DOMAIN_FIELDS,
) -> dict[str, list[Mapping[str, Any]]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for deal in deals:
        domain_key = infer_domain_key(deal, domain_fields=domain_fields)
        if not domain_key:
            continue
        groups.setdefault(domain_key, []).append(deal)
    return {domain: items for domain, items in groups.items() if len(items) > 1}


def normalize_deal_context(
    deal: Mapping[str, Any],
    *,
    product_rows: Sequence[Mapping[str, Any]] | None = None,
) -> DealContext:
    raw = _raw_mapping(deal)
    attribution = {
        field_name: str(_pick(deal, field_name, field_name.lower(), raw=raw) or "").strip()
        for field_name in ATTRIBUTION_FIELDS
    }
    return DealContext(
        id=str(_pick(deal, "id", "ID", raw=raw) or "").strip(),
        title=str(_pick(deal, "title", "TITLE", raw=raw) or "").strip(),
        category_id=str(_pick(deal, "category_id", "CATEGORY_ID", "categoryId", raw=raw) or "").strip(),
        category_name=str(_pick(deal, "category_name", "CATEGORY_NAME", raw=raw) or "").strip(),
        stage_id=str(_pick(deal, "stage_id", "STAGE_ID", "STATUS_ID", raw=raw) or "").strip(),
        stage_name=str(_pick(deal, "stage_name", "STAGE_NAME", raw=raw) or "").strip(),
        semantic_id=str(_pick(deal, "semantic_id", "STAGE_SEMANTIC_ID", "STATUS_SEMANTIC_ID", raw=raw) or "").strip(),
        created_at=str(_pick(deal, "created_at", "DATE_CREATE", "CREATED_TIME", raw=raw) or "").strip(),
        updated_at=str(_pick(deal, "updated_at", "DATE_MODIFY", "UPDATED_TIME", "MOVED_TIME", raw=raw) or "").strip(),
        product_signature=_product_signature(product_rows or _pick(deal, "product_rows", "PRODUCT_ROWS", raw=raw) or ()),
        attribution={key: value for key, value in attribution.items() if value},
        raw=raw or deal,
    )


def plan_duplicate_group(
    deals: Sequence[Mapping[str, Any]],
    *,
    domain_key: str | None = None,
    product_rows_by_deal: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    config: DealDuplicatePolicyConfig = DealDuplicatePolicyConfig(),
) -> DealDuplicatePlan:
    """Строит dry-run план объединения для уже найденной группы дублей."""

    contexts = [
        normalize_deal_context(deal, product_rows=(product_rows_by_deal or {}).get(str(_pick(deal, "id", "ID") or "")))
        for deal in deals
    ]
    contexts = [deal for deal in contexts if deal.id]
    if len(contexts) < 2:
        return DealDuplicatePlan(domain_key=domain_key, actions=(), warnings=("В группе меньше двух сделок.",))

    protected = tuple(deal for deal in contexts if _is_protected_category(deal, config))
    candidates = tuple(deal for deal in contexts if deal not in protected)
    warnings: list[str] = []
    if protected:
        warnings.append("Сделки аккаунтинга/retention защищены и не включены в объединение.")
    if len(candidates) < 2:
        return DealDuplicatePlan(
            domain_key=domain_key,
            actions=(),
            protected_ids=tuple(deal.id for deal in protected),
            warnings=tuple(warnings or ["Нет двух незашищённых сделок для объединения."]),
        )

    success_plan = _plan_success_actions(candidates, domain_key=domain_key, config=config)
    if success_plan is not None:
        return _with_protected(success_plan, protected, warnings)

    target, reason = _select_non_success_target(candidates, has_protected=bool(protected), config=config)
    duplicates = tuple(deal for deal in candidates if deal.id != target.id)
    if not duplicates:
        return DealDuplicatePlan(
            domain_key=domain_key,
            actions=(),
            protected_ids=tuple(deal.id for deal in protected),
            warnings=tuple(warnings or ["Не найдено сделок для объединения."]),
        )

    action = _build_action(target, duplicates, reason)
    return DealDuplicatePlan(
        domain_key=domain_key,
        actions=(action,),
        protected_ids=tuple(deal.id for deal in protected),
        warnings=tuple(warnings),
    )


def _plan_success_actions(
    candidates: Sequence[DealContext],
    *,
    domain_key: str | None,
    config: DealDuplicatePolicyConfig,
) -> DealDuplicatePlan | None:
    success_deals = tuple(deal for deal in candidates if _is_success_stage(deal, config))
    if not success_deals:
        return None

    actions: list[DealMergeAction] = []
    skipped: list[str] = []
    warnings: list[str] = []
    success_by_product: dict[str, list[DealContext]] = {}
    without_product: list[DealContext] = []
    for deal in success_deals:
        if deal.product_signature:
            success_by_product.setdefault(deal.product_signature, []).append(deal)
        else:
            without_product.append(deal)

    if len(success_deals) > 1 and len(success_by_product) != len(success_deals):
        warnings.append("В успехе несколько сделок без полной продуктовой сигнатуры; часть дублей оставлена на ручную проверку.")

    if len(success_deals) == 1:
        target = success_deals[0]
        duplicates = tuple(deal for deal in candidates if deal.id != target.id)
        if duplicates:
            actions.append(_build_action(target, duplicates, "Основная сделка выбрана из стадии успеха."))
        return DealDuplicatePlan(domain_key=domain_key, actions=tuple(actions), skipped_ids=tuple(skipped), warnings=tuple(warnings))

    for product_signature, product_successes in sorted(success_by_product.items()):
        target = _freshest(product_successes)
        product_group = tuple(
            deal
            for deal in candidates
            if deal.id != target.id and deal.product_signature == product_signature
        )
        if product_group:
            actions.append(
                _build_action(
                    target,
                    product_group,
                    "Основная сделка выбрана из успеха с совпадающим продуктом.",
                )
            )

    success_ids = {deal.id for deal in success_deals}
    covered_ids = {item for action in actions for item in action.duplicate_ids} | {action.target_id for action in actions}
    for deal in candidates:
        if deal.id in covered_ids or deal.id in success_ids:
            continue
        if deal.product_signature and deal.product_signature not in success_by_product:
            skipped.append(deal.id)
            continue
        if not deal.product_signature:
            skipped.append(deal.id)

    if skipped:
        warnings.append("Часть сделок не объединена: есть несколько успехов по домену, но продукт не определён однозначно.")

    return DealDuplicatePlan(
        domain_key=domain_key,
        actions=tuple(actions),
        skipped_ids=tuple(skipped),
        warnings=tuple(warnings),
    )


def _select_non_success_target(
    candidates: Sequence[DealContext],
    *,
    has_protected: bool,
    config: DealDuplicatePolicyConfig,
) -> tuple[DealContext, str]:
    active_sales = tuple(
        deal
        for deal in candidates
        if _is_sales_category(deal, config) and not _is_lost_stage(deal, config)
    )
    if active_sales:
        return _freshest(active_sales), "Основная сделка выбрана из активной/отложенной воронки продаж ОП."

    active_clients = tuple(deal for deal in candidates if _is_active_client_stage(deal, config) and not _is_lost_stage(deal, config))
    if has_protected and active_clients:
        return _freshest(active_clients), "Основная сделка выбрана из стадии Действующий клиент при пересечении с аккаунтингом."

    telemarketing = tuple(deal for deal in candidates if _is_telemarketing_category(deal, config))
    if telemarketing and len(telemarketing) == len(candidates):
        return _freshest(telemarketing), "Дубли есть только в телемаркетинге; основная сделка самая свежая."

    return _freshest(candidates), "Основная сделка выбрана как самая свежая среди оставшихся дублей."


def _build_action(target: DealContext, duplicates: Sequence[DealContext], reason: str) -> DealMergeAction:
    attribution_source = _earliest((target, *duplicates))
    return DealMergeAction(
        target_id=target.id,
        duplicate_ids=tuple(deal.id for deal in duplicates),
        reason=reason,
        attribution_source_id=attribution_source.id if attribution_source else None,
        attribution_updates=dict(attribution_source.attribution) if attribution_source else {},
    )


def _with_protected(
    plan: DealDuplicatePlan,
    protected: Sequence[DealContext],
    warnings: Sequence[str],
) -> DealDuplicatePlan:
    return DealDuplicatePlan(
        domain_key=plan.domain_key,
        actions=plan.actions,
        protected_ids=tuple(deal.id for deal in protected),
        skipped_ids=plan.skipped_ids,
        warnings=tuple([*warnings, *plan.warnings]),
    )


def _is_sales_category(deal: DealContext, config: DealDuplicatePolicyConfig) -> bool:
    if deal.category_id and deal.category_id in config.sales_category_ids:
        return True
    return _contains_any(deal.category_name, config.sales_category_markers)


def _is_telemarketing_category(deal: DealContext, config: DealDuplicatePolicyConfig) -> bool:
    return _contains_any(deal.category_name, config.telemarketing_category_markers)


def _is_protected_category(deal: DealContext, config: DealDuplicatePolicyConfig) -> bool:
    return _contains_any(deal.category_name, config.protected_category_markers)


def _is_success_stage(deal: DealContext, config: DealDuplicatePolicyConfig) -> bool:
    semantic = normalize_label(deal.semantic_id)
    stage_id = normalize_label(deal.stage_id)
    return semantic == "s" or stage_id.endswith("won") or _contains_any(deal.stage_name, config.success_stage_markers)


def _is_lost_stage(deal: DealContext, config: DealDuplicatePolicyConfig) -> bool:
    semantic = normalize_label(deal.semantic_id)
    stage_id = normalize_label(deal.stage_id)
    return semantic == "f" or "lose" in stage_id or "fail" in stage_id or _contains_any(deal.stage_name, config.lost_stage_markers)


def _is_active_client_stage(deal: DealContext, config: DealDuplicatePolicyConfig) -> bool:
    return _contains_any(deal.stage_name, config.active_client_stage_markers)


def _contains_any(value: Any, markers: Sequence[str]) -> bool:
    label = normalize_label(value)
    return any(normalize_label(marker) in label for marker in markers)


def _freshest(deals: Sequence[DealContext]) -> DealContext:
    return max(deals, key=lambda deal: (_date_sort_key(deal.updated_at or deal.created_at), _id_sort_key(deal.id)))


def _earliest(deals: Sequence[DealContext]) -> DealContext | None:
    if not deals:
        return None
    return min(deals, key=lambda deal: (_date_sort_key(deal.created_at), _id_sort_key(deal.id)))


def _date_sort_key(value: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _id_sort_key(value: str) -> int:
    try:
        return int(str(value or "0").strip())
    except ValueError:
        return 0


def _product_signature(product_rows: Sequence[Mapping[str, Any]] | Any) -> str:
    if not isinstance(product_rows, Sequence) or isinstance(product_rows, (str, bytes)):
        return ""
    parts: list[str] = []
    for row in product_rows:
        if not isinstance(row, Mapping):
            continue
        raw = row.get("PRODUCT_ID") or row.get("product_id") or row.get("PRODUCT_NAME") or row.get("NAME") or row.get("name")
        label = normalize_label(raw)
        if label:
            parts.append(label)
    return "|".join(sorted(dict.fromkeys(parts)))


def _raw_mapping(deal: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = deal.get("raw")
    return raw if isinstance(raw, Mapping) else {}


def _pick(deal: Mapping[str, Any], *keys: str, raw: Mapping[str, Any] | None = None) -> Any:
    raw_data = raw if raw is not None else _raw_mapping(deal)
    for key in keys:
        if key in deal and deal.get(key) not in (None, ""):
            return deal.get(key)
        if key in raw_data and raw_data.get(key) not in (None, ""):
            return raw_data.get(key)
    return None


def _normalize_domain(value: Any) -> str | None:
    raw = str(value or "").strip().casefold()
    if not raw:
        return None
    match = _DOMAIN_RE.search(raw)
    if not match:
        return None
    domain = match.group(1).strip(".")
    if domain.endswith(".bitrix24.ru"):
        return None
    return domain.removeprefix("www.")
