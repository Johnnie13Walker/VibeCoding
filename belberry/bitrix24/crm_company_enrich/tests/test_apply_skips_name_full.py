"""apply.RQ_COMPANY_NAME_FULL: default-conservative skip + CCE_WRITE_NAME_FULL opt-in.

Покрытие:
  1. По умолчанию (env unset, write_name_full=False): payload НЕ содержит
     ключа RQ_COMPANY_NAME_FULL — даже если discovered_name «чистый»
     и discovered_source = rusprofile_verified.
  2. С write_name_full=True: payload содержит cleaned discovered_name.
"""
from __future__ import annotations

from crm_company_enrich.models import QueueRow, TargetAction
from crm_company_enrich.stages import apply
from crm_company_enrich.state import Status

# Reuse fakes
from tests.test_apply_create_req import FakeBitrix, FakeSheets


def _row(
    cid: str = "10",
    inn: str = "7707083893",
    discovered_name: str | None = "ООО Тест",
    discovered_source: str | None = "rusprofile_verified",
) -> QueueRow:
    return QueueRow(
        company_id=cid,
        company_name=f"Bitrix-title {cid}",
        discovered_inn=inn,
        discovered_name=discovered_name,
        discovered_source=discovered_source,
        target_action=TargetAction.CREATE_REQ,
        status=Status.APPROVED,
        approved=True,
    )


# ----- 1. Default: no RQ_COMPANY_NAME_FULL -----


def test_default_payload_excludes_rq_company_name_full():
    """По умолчанию apply не пишет RQ_COMPANY_NAME_FULL даже при «чистом» имени."""
    row = _row(discovered_name="ООО Чистое Имя", discovered_source="rusprofile_verified")
    bx = FakeBitrix(existing_requisites={"10": []})
    sheets = FakeSheets([row])

    summary = apply.run(bx, sheets, sleep_s=0, bizproc_template_id=None)

    assert summary["applied"] == 1
    payload = bx.add_calls[0]
    assert "RQ_COMPANY_NAME_FULL" not in payload
    # Базовые поля payload присутствуют как обычно
    assert payload["RQ_INN"] == "7707083893"
    assert payload["NAME"] == "Реквизиты ЮЛ"


def test_default_payload_excludes_rq_company_name_full_for_web_source_too():
    row = _row(discovered_name="ООО Что-то", discovered_source="web")
    bx = FakeBitrix(existing_requisites={"10": []})
    sheets = FakeSheets([row])

    apply.run(bx, sheets, sleep_s=0, bizproc_template_id=None)
    payload = bx.add_calls[0]
    assert "RQ_COMPANY_NAME_FULL" not in payload


# ----- 2. Opt-in: kwarg write_name_full=True restores old behavior -----


def test_opt_in_write_name_full_includes_cleaned_name():
    row = _row(
        discovered_name="ООО Ромашка - результаты поиска на Rusprofile.ru",
        discovered_source="rusprofile_verified",
    )
    bx = FakeBitrix(existing_requisites={"10": []})
    sheets = FakeSheets([row])

    apply.run(
        bx, sheets, sleep_s=0, bizproc_template_id=None, write_name_full=True
    )
    payload = bx.add_calls[0]
    assert payload["RQ_COMPANY_NAME_FULL"] == "ООО Ромашка"  # cleaned hash-trail


def test_opt_in_via_env_var(monkeypatch):
    """Проверяем, что CCE_WRITE_NAME_FULL=1 в env читается config'ом.

    config.py читает env при импорте, поэтому нужно перезагрузить модуль.
    """
    import importlib

    monkeypatch.setenv("CCE_WRITE_NAME_FULL", "1")
    from crm_company_enrich import config as cfg

    importlib.reload(cfg)
    assert cfg.CCE_WRITE_NAME_FULL is True

    # сброс — чтобы не протекало в другие тесты
    monkeypatch.delenv("CCE_WRITE_NAME_FULL", raising=False)
    importlib.reload(cfg)
    assert cfg.CCE_WRITE_NAME_FULL is False
