"""pytest-конфигурация для crm_company_enrich."""
from __future__ import annotations

import importlib

import pytest

_MODULES_WITH_LOG_DIR = (
    "crm_company_enrich.stages.auto_revive_lose",
    "crm_company_enrich.stages.auto_reject_telemarketing",
    "crm_company_enrich.stages.dedupe_contacts",
    "crm_company_enrich.stages.telemarketing_dedupe",
    "crm_company_enrich.stages.migrate_region_enum_ids",
    "crm_company_enrich.stages.migrate_revive_count_to_uf",
    "crm_company_enrich.bitrix_client",
    "crm_company_enrich.config",
)


@pytest.fixture(autouse=True)
def _isolate_log_dir(monkeypatch, tmp_path):
    """Ни один тест не должен писать в production belberry/bitrix24/logs."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    for module_path in _MODULES_WITH_LOG_DIR:
        try:
            module = importlib.import_module(module_path)
        except ImportError:
            continue
        if hasattr(module, "LOG_DIR"):
            monkeypatch.setattr(module, "LOG_DIR", log_dir)
    yield log_dir
