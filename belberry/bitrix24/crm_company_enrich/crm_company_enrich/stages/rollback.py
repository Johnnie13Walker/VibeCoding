"""Stub стадии rollback — WRITE escape hatch.

Когда будет реализовано:

  rollback --company-id X --confirm-rollback

  Для APPLIED (CREATE_REQ путь):
    - найти реквизит, созданный нашим apply (по company_enrich_log)
    - crm.requisite.delete

  Для MERGED (MERGE_INTO путь):
    - восстановить связи source ← target из backup-листа
      (apply должен сохранить backup ДО merge, иначе rollback невозможен)
    - удалить наш timeline-маркер у target

  Затем Status.ROLLED_BACK + запись в log.

Безопасность:
  - --confirm-rollback обязателен.
  - rollback без backup → ValueError.
"""
from __future__ import annotations

_STUB_MSG = (
    "rollback stage is a stub — реализация отложена. "
    "Контракт описан в docstring файла crm_company_enrich/stages/rollback.py."
)


def run(*args, **kwargs) -> int:  # pragma: no cover
    print(f"[rollback] STUB: {_STUB_MSG}")
    raise NotImplementedError(_STUB_MSG)
