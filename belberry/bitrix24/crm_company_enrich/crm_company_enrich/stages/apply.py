"""Stub стадии apply — WRITE-стадия отложена до завершения crm_deal_merge prod-run.

Контракт когда будет реализовано:
1. Для каждой APPROVED строки с target_action=CREATE_REQ:
   - Прочитать discovered_inn (нормализовать ещё раз через normalize_inn)
   - crm.requisite.add({
        ENTITY_TYPE_ID: 4, ENTITY_ID: row.company_id,
        RQ_INN: discovered_inn, NAME: discovered_name or row.company_name,
        PRESET_ID: <ИП/ЮЛ — выбрать по длине ИНН>,
     })
   - Записать в company_enrich_log событие APPLIED.
   - Перевести строку в Status.APPLIED.
2. Idempotency:
   - Перед add сделать search_requisite_by_inn(discovered_inn) и убедиться,
     что ничего не существует. Иначе → Status.FAILED.
3. Safety guards (см. спецификацию §5.5 в commit-message ветки):
   - in_active_deal_merge=1 → пропускаем.
   - is_valid_inn_format(discovered_inn) обязательно (10 или 12 цифр).
   - PRESET_ID должен быть валиден на портале — проверить через crm.requisite.preset.list.

См. README.md «Write-stages: статус».
"""
from __future__ import annotations

_STUB_MSG = (
    "apply stage is a stub — write to Bitrix отложен до завершения "
    "crm_deal_merge prod-run (PID 20750). Контракт описан в docstring файла "
    "crm_company_enrich/stages/apply.py."
)


def run(*args, **kwargs) -> int:  # pragma: no cover — заведомо неподдержано
    print(f"[apply] STUB: {_STUB_MSG}")
    raise NotImplementedError(_STUB_MSG)
