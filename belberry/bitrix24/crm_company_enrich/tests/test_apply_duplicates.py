from __future__ import annotations

import json

from crm_company_enrich.stages import enrich_empty_companies as stage


class FakeDuplicateBitrix:
    def __init__(
        self,
        *,
        current_company_id: str = "3064",
        inn: str = "7728264185",
        current_requisites: list[dict] | None = None,
        duplicate_requisites: list[dict] | None = None,
        duplicate_deals: dict[str, list[dict]] | None = None,
        verified_after_bp: bool = True,
    ):
        self.current_company_id = current_company_id
        self.inn = inn
        self.current_requisites = list(current_requisites or [])
        self.duplicate_requisites = list(duplicate_requisites or [])
        self.duplicate_deals = duplicate_deals or {}
        self.verified_after_bp = verified_after_bp
        self.added_requisites: list[dict] = []
        self.workflow_calls: list[tuple[int, list]] = []
        self.updated_companies: list[tuple[str, dict]] = []
        self.deleted_requisites: list[str] = []
        self.add_deal_calls: list[dict] = []

    def get_company(self, company_id):
        return {
            "ID": str(company_id),
            "TITLE": "Дубль компании",
            "UF_CRM_ORG_STATUS": "8850",
            "INDUSTRY": "",
            "REVENUE": "1000",
        }

    def list_requisites_by_inn(self, inn):
        return [
            *self.current_requisites,
            *self.duplicate_requisites,
        ]

    def list_company_requisites(self, company_id):
        if str(company_id) != self.current_company_id:
            return []
        if self.verified_after_bp and any(tpl == 8612 for tpl, _ in self.workflow_calls):
            return [
                {
                    "ID": "8001",
                    "ENTITY_ID": self.current_company_id,
                    "RQ_INN": self.inn,
                    "RQ_KPP": "772801001",
                    "RQ_OGRN": "1027700000000",
                }
            ]
        return list(self.current_requisites)

    def list_company_deals(self, company_id, select=None):
        return list(self.duplicate_deals.get(str(company_id), []))

    def add_requisite(self, payload):
        self.added_requisites.append(dict(payload))
        req = {
            "ID": str(7000 + len(self.added_requisites)),
            "ENTITY_ID": str(payload["ENTITY_ID"]),
            "RQ_INN": payload["RQ_INN"],
        }
        self.current_requisites.append(req)
        return req["ID"]

    def start_workflow(self, template_id, document_type):
        self.workflow_calls.append((int(template_id), list(document_type)))
        return {"workflow_id": f"wf-{template_id}"}

    def update_company(self, company_id, fields):
        self.updated_companies.append((str(company_id), dict(fields)))
        return True

    def delete_requisite(self, requisite_id):
        self.deleted_requisites.append(str(requisite_id))
        return True


def _state(company_id: str = "3064", inn: str = "7728264185") -> dict:
    return {
        "results": [
            {
                "company_id": company_id,
                "title": "Дубль компании",
                "score": 3,
                "source": "manual_site",
                "inn_candidate": inn,
                "geo_verified": True,
                "brand_predicted": "Belberry",
                "brand_evidence": "test",
                "classification": "READY_TO_APPLY",
                "evidence": {"signals": {}},
                "apply_status": "",
            }
        ]
    }


def _patch_apply(monkeypatch, fake_bx, state):
    written: dict = {}
    backups: list[dict] = []

    def write_json(path, data):
        written["path"] = path
        written["data"] = data

    def backup(*args, duplicate_info=None, **kwargs):
        backups.append(duplicate_info or {})
        return "backup.json"

    monkeypatch.setattr(stage, "BitrixClient", lambda *args, **kwargs: fake_bx)
    monkeypatch.setattr(stage, "_load_state", lambda: state)
    monkeypatch.setattr(stage, "_write_json", write_json)
    monkeypatch.setattr(stage, "run_upload_plan", lambda: None)
    monkeypatch.setattr(stage, "_backup_before_apply_snapshot", backup)
    monkeypatch.setattr(stage.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(stage, "CCE_BIZPROC_WAIT_S", 1)
    monkeypatch.setattr(stage, "CCE_COMPANY_TOUCH", False)
    return written, backups


def test_same_inn_in_other_company_does_not_skip_current_company_enrichment(monkeypatch):
    fake_bx = FakeDuplicateBitrix(
        duplicate_requisites=[
            {"ID": "9001", "ENTITY_ID": "9634", "RQ_INN": "7728264185", "RQ_KPP": "772801001"}
        ],
    )
    state = _state()
    written, backups = _patch_apply(monkeypatch, fake_bx, state)

    summary = stage.run_apply(dry_run=False)
    result = written["data"]["results"][0]

    assert summary["applied"] == 1
    assert result["apply_status"] in {"APPLIED", "APPLIED_LIQUIDATED"}
    assert result["apply_status"] != "SKIPPED_ALREADY_HAS_INN"
    assert fake_bx.added_requisites[0]["ENTITY_ID"] == 3064
    assert [call[0] for call in fake_bx.workflow_calls[:2]] == [5938, 8612]
    assert result["duplicate_company_ids"] == ["9634"]
    assert backups[0]["duplicate_company_ids"] == ["9634"]


def test_duplicate_company_with_active_deal_enriches_company_but_does_not_create_new_deal(monkeypatch):
    fake_bx = FakeDuplicateBitrix(
        duplicate_requisites=[
            {"ID": "9001", "ENTITY_ID": "9634", "RQ_INN": "7728264185", "RQ_KPP": "772801001"}
        ],
        duplicate_deals={
            "9634": [
                {
                    "ID": "2188",
                    "COMPANY_ID": "9634",
                    "CLOSED": "N",
                    "STAGE_ID": "C50:NEW",
                    "CATEGORY_ID": "50",
                }
            ]
        },
    )
    state = _state()
    written, _backups = _patch_apply(monkeypatch, fake_bx, state)

    summary = stage.run_apply(dry_run=False)
    result = written["data"]["results"][0]

    assert summary["applied"] == 1
    assert result["apply_status"] == "APPLIED"
    assert result["duplicate_active_deals"] == [
        {"company_id": "9634", "deal_id": "2188", "stage_id": "C50:NEW", "category_id": "50"}
    ]
    assert fake_bx.add_deal_calls == []


def test_current_company_existing_valid_requisite_still_skips_requisite_creation(monkeypatch):
    fake_bx = FakeDuplicateBitrix(
        current_requisites=[
            {
                "ID": "8001",
                "ENTITY_ID": "3064",
                "RQ_INN": "7728264185",
                "RQ_KPP": "772801001",
                "RQ_OGRN": "1027700000000",
            }
        ],
    )
    state = _state()
    written, _backups = _patch_apply(monkeypatch, fake_bx, state)

    summary = stage.run_apply(dry_run=False)
    result = written["data"]["results"][0]

    assert summary["applied"] == 1
    assert fake_bx.added_requisites == []
    assert result["apply_status"] == "APPLIED"
    assert fake_bx.workflow_calls == []


def test_duplicate_evidence_is_written_to_backup(tmp_path, monkeypatch):
    monkeypatch.setattr(stage, "WORKSPACE_ROOT", tmp_path)
    row = stage.PlanRow(
        company_id="3064",
        title="Дубль компании",
        score=3,
        inn_candidate="7728264185",
        classification="READY_TO_APPLY",
    )
    duplicate_info = {
        "duplicate_company_ids": ["9634"],
        "duplicate_active_deals": [
            {"company_id": "9634", "deal_id": "2188", "stage_id": "C50:NEW", "category_id": "50"}
        ],
        "duplicate_requisite_ids": ["9001"],
        "duplicate_reason": "enrich-only: active deal 2188 on company 9634",
    }

    backup_path = stage._backup_before_apply_snapshot(
        object(),
        row,
        {"ID": "3064"},
        [],
        duplicate_info=duplicate_info,
    )

    payload = json.loads(stage.Path(backup_path).read_text(encoding="utf-8"))
    assert payload["duplicate_info"] == duplicate_info
