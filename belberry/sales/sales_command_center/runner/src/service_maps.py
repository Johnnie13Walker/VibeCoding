"""Справочники услуг для брифов (СП1056) и КП (СП1106) — единый источник.

У брифа и КП РАЗНЫЕ enum-поля и РАЗНЫЕ наборы id (сверено с Bitrix). Использует
live.py (режим «Сегодня») и transform.py (дневной/flow-раннер → kp_briefs.service),
чтобы услуга совпадала в live и в истории.
"""

from __future__ import annotations

from typing import Any

# Бриф (1056) «Список услуг» — enumeration ufCrm20_1753290430.
BRIEF_SERVICE_FIELD = "ufCrm20_1753290430"
BRIEF_SERVICE_MAP = {
    2722: "Дзен", 2724: "Копирайтинг", 2726: "Контекстная реклама", 2728: "GEO",
    2730: "SEO", 2732: "ORM", 2734: "SMM", 2736: "Разработка сайта",
    2738: "Техподдержка", 2740: "Лендинг", 2742: "Фирменный стиль", 9538: "AEO",
}

# КП (1106) «Список услуг» — enumeration ufCrm44_1774430907621 (свой набор id).
KP_SERVICE_FIELD = "ufCrm44_1774430907621"
KP_SERVICE_MAP = {
    8652: "SEO", 8654: "Дзен", 8656: "Копирайтинг", 8658: "Контекстная реклама",
    8660: "GEO", 8662: "ORM", 8664: "SMM", 8666: "Разработка сайта",
    8668: "Техподдержка", 8670: "Лендинг", 8672: "Фирменный стиль", 9540: "AEO",
}


def _enum_int(value: Any) -> int:
    """enum приходит как int/str/[..] — берём первый и приводим к int (0 — пусто)."""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def brief_service(item: dict[str, Any]) -> str:
    """Название услуги брифа (1056); '' если не выбрана."""
    return BRIEF_SERVICE_MAP.get(_enum_int(item.get(BRIEF_SERVICE_FIELD)), "")


def kp_service(item: dict[str, Any]) -> str:
    """Название услуги КП (1106); '' если не выбрана."""
    return KP_SERVICE_MAP.get(_enum_int(item.get(KP_SERVICE_FIELD)), "")
