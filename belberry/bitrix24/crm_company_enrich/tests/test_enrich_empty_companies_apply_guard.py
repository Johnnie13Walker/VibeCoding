"""Регрессионные тесты guard'а run_apply: не дописывать чужой ИНН компании,
у которой уже есть свой валидный ИНН (корень контаминации реквизитов)."""
from __future__ import annotations

import pytest

from crm_company_enrich.stages import enrich_empty_companies as stage


class _FakeBitrix:
    def __init__(self, existing):
        self._existing = [dict(r) for r in existing]
        self.added_requisites: list[dict] = []
        self.updated_companies: list[tuple[str, dict]] = []

    def get_company(self, company_id):
        return {"ID": str(company_id), "TITLE": "ООО Тест"}

    def list_company_requisites(self, company_id):
        return [dict(r) for r in self._existing]

    def add_requisite(self, fields):
        self.added_requisites.append(dict(fields))
        rid = str(70000 + len(self.added_requisites))
        self._existing.append({"ID": rid, **fields})
        return rid

    def update_company(self, company_id, fields):
        self.updated_companies.append((str(company_id), dict(fields)))
        return True


def _row(company_id="10", inn="7700000002"):
    return {
        "company_id": company_id,
        "title": "ООО Тест",
        "score": 5,
        "inn_candidate": inn,
        "brand_predicted": "Belberry",
        "classification": "READY_TO_APPLY",
        "apply_status": "",
    }


@pytest.fixture
def patched(monkeypatch):
    def _apply(bx, row_dict):
        monkeypatch.setattr(stage.time, "sleep", lambda *_a, **_k: None)
        monkeypatch.setattr(stage, "_load_state", lambda: {"results": [row_dict]})
        monkeypatch.setattr(stage, "_save_state", lambda *a, **k: None, raising=False)
        monkeypatch.setattr(stage, "BitrixClient", lambda *a, **k: bx)
        monkeypatch.setattr(stage, "_list_requisites_by_inn", lambda *a, **k: [])
        monkeypatch.setattr(stage, "_duplicate_info_from_requisites", lambda *a, **k: {})
        monkeypatch.setattr(stage, "_backup_before_apply_snapshot", lambda *a, **k: "backup/none")
        monkeypatch.setattr(stage, "_start_bp_first_entry", lambda *a, **k: "skipped:test")
        monkeypatch.setattr(stage, "_start_bp_update", lambda *a, **k: "skipped:test")
        monkeypatch.setattr(stage, "_verify_with_retries", lambda *a, **k: (True, {"RQ_INN": "x", "RQ_OGRN": "1"}, "APPLIED"))
        monkeypatch.setattr(stage, "_cleanup_trigger_requisites", lambda *a, **k: 0)
        monkeypatch.setattr(stage, "_fill_company_address_fields", lambda *a, **k: {})
    return _apply


def test_apply_skips_when_company_has_other_valid_inn(patched):
    # У компании уже есть СВОЙ валидный ИНН; пытаемся дописать ДРУГОЙ (чужой) — должно SKIP.
    bx = _FakeBitrix(existing=[{"ID": "500", "ENTITY_ID": "10", "RQ_INN": "7700000001", "RQ_OGRN": "1027700000000"}])
    patched(bx, _row(inn="7700000002"))

    stage.run_apply(dry_run=False, throttle_s=0)

    assert bx.added_requisites == []  # чужой ИНН НЕ дописан — контаминация предотвращена


def test_apply_adds_when_company_has_no_inn(patched):
    # Пустая компания (нет реквизитов) — guard НЕ мешает, ИНН дописывается как раньше.
    bx = _FakeBitrix(existing=[])
    patched(bx, _row(inn="7700000002"))

    stage.run_apply(dry_run=False, throttle_s=0)

    assert len(bx.added_requisites) == 1
    assert bx.added_requisites[0]["RQ_INN"] == "7700000002"
