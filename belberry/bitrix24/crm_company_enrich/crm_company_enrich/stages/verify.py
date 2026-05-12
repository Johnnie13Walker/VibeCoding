"""Stub стадии verify — read-only проверка результата apply / merge-dupes.

Когда будет реализовано — verify исключительно READ-only:

  Для каждой APPLIED строки:
    - bx.list_company_requisites(row.company_id) должен содержать
      реквизит с RQ_INN == row.discovered_inn → Status.VERIFIED иначе FAILED.

  Для каждой MERGED строки:
    - source компания: crm.deal.list filter[COMPANY_ID]=source.id должен
      вернуть пусто (или только новые сделки с DATE_CREATE > merged_at)
    - target компания: содержит valid реквизит
    - timeline target содержит маркер company_enrich

Verify можно вызывать многократно — он не пишет в Bitrix.
"""
from __future__ import annotations

_STUB_MSG = (
    "verify stage is a stub — реализация отложена. "
    "Контракт описан в docstring файла crm_company_enrich/stages/verify.py."
)


def run(*args, **kwargs) -> int:  # pragma: no cover
    print(f"[verify] STUB: {_STUB_MSG}")
    raise NotImplementedError(_STUB_MSG)
