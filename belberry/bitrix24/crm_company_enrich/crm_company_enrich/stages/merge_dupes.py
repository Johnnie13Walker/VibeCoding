"""Stub стадии merge-dupes — слияние двух компаний с одинаковым ИНН.

WRITE-стадия отложена. Контракт:

Для каждой APPROVED строки с target_action=MERGE_INTO:
  source = row.company_id          (компания без реквизита — будет «свёрнута»)
  target = row.merge_target_company_id  (компания с валидным реквизитом)

1. Read-only sanity: target ещё имеет валидный реквизит, source — нет
   (повторная проверка перед действием).
2. Перенос связей source → target:
   - все сделки COMPANY_ID=source → перепривязать на target через crm.deal.update
   - все контакты — через crm.company.contact.add (target) + .delete (source)
   - smart-processes с parentId3=source → relink на target (см. deal-merge
     паттерн в bitrix_client.relink_smart_item)
3. timeline-комментарий маркер в target с marker COMMENT="[company_enrich merge from #{source}]".
4. После успешного переноса:
   - Установить флаг UF_DELETED у source или физически удалить crm.company.delete
     (политику выбрать в продакшен-флаге CCE_DELETE_SOURCE_COMPANY, по умолчанию keep).
5. Запись в company_enrich_log + Status.MERGED.

Безопасность:
- DELETE никогда без явного флага.
- in_active_deal_merge=1 → пропуск (компания может быть LOSER в deal-merge).
- crm.deal.update должен переноситься группами и каждая партия проверяется
  на наличие COMPANY_ID==target после.

См. также: rollback.py stub — обратная операция должна быть симметричной.
"""
from __future__ import annotations

_STUB_MSG = (
    "merge-dupes stage is a stub — write to Bitrix отложен до завершения "
    "crm_deal_merge prod-run. Контракт описан в docstring файла "
    "crm_company_enrich/stages/merge_dupes.py."
)


def run(*args, **kwargs) -> int:  # pragma: no cover
    print(f"[merge-dupes] STUB: {_STUB_MSG}")
    raise NotImplementedError(_STUB_MSG)
