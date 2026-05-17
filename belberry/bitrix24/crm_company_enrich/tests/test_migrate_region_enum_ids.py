from __future__ import annotations

from crm_company_enrich.config import COMPANY_UF_REGION
from crm_company_enrich.stages import migrate_region_enum_ids as stage


class FakeBitrix:
    def __init__(self, companies: list[dict], *, fail_ids: set[str] | None = None):
        self.companies = companies
        self.fail_ids = fail_ids or set()
        self.update_company_calls: list[tuple[str, dict]] = []

    def paginate(self, method: str, params: dict):
        assert method == "crm.company.list"
        for company in self.companies:
            if str(company.get(COMPANY_UF_REGION) or "").strip():
                yield dict(company)

    def get_company_user_fields(self):
        return [
            {
                "FIELD_NAME": COMPANY_UF_REGION,
                "LIST": [{"ID": item_id} for item_id in ["9234", "9290", "9172", "9212"]],
            }
        ]

    def update_company(self, company_id: str, fields: dict) -> bool:
        if str(company_id) in self.fail_ids:
            raise RuntimeError(f"update failed for {company_id}")
        self.update_company_calls.append((str(company_id), dict(fields)))
        for company in self.companies:
            if str(company.get("ID")) == str(company_id):
                company.update(fields)
                break
        return True


def test_dry_run_reports_orphans_without_writing():
    bx = FakeBitrix(
        [
            {"ID": "1", "TITLE": "Москва old", COMPANY_UF_REGION: "9008"},
            {"ID": "2", "TITLE": "Татарстан current", COMPANY_UF_REGION: "9290"},
            {"ID": "3", "TITLE": "Без региона", COMPANY_UF_REGION: ""},
        ]
    )

    summary = stage.run(bx)

    assert summary["dry_run_migrations"] == 1
    assert bx.update_company_calls == []
    assert summary["outcomes"][0]["status"] == "DRY_RUN"
    assert summary["outcomes"][0]["old_id"] == "9008"
    assert summary["outcomes"][0]["new_id"] == "9234"


def test_live_migrates_orphan_to_current_enum():
    bx = FakeBitrix([{"ID": "1", "TITLE": "Москва old", COMPANY_UF_REGION: "9008"}])

    summary = stage.run(bx, dry_run=False)

    assert summary["migrated"] == 1
    assert bx.update_company_calls == [("1", {COMPANY_UF_REGION: "9234"})]


def test_unknown_old_id_reported_not_migrated():
    bx = FakeBitrix([{"ID": "1", "TITLE": "Unknown", COMPANY_UF_REGION: "99999"}])

    summary = stage.run(bx)

    assert summary["unknown"] == 1
    assert summary["outcomes"][0]["status"] == "UNKNOWN_OLD_ID"
    assert summary["unknown_old_ids"] == ["99999"]
    assert bx.update_company_calls == []


def test_idempotent_rerun_after_migration():
    bx = FakeBitrix([{"ID": "1", "TITLE": "Москва old", COMPANY_UF_REGION: "9008"}])

    first = stage.run(bx, dry_run=False)
    second = stage.run(bx, dry_run=False)

    assert first["migrated"] == 1
    assert second["migrated"] == 0
    assert second["outcomes"] == []


def test_actual_enum_id_not_touched():
    bx = FakeBitrix([{"ID": "1", "TITLE": "Татарстан current", COMPANY_UF_REGION: "9290"}])

    summary = stage.run(bx, dry_run=False)

    assert summary["migrated"] == 0
    assert summary["outcomes"] == []
    assert bx.update_company_calls == []


def test_audit_csv_written_for_migrated(tmp_path):
    bx = FakeBitrix([{"ID": "1", "TITLE": "Москва old", COMPANY_UF_REGION: "9008"}])

    stage.run(bx, dry_run=False)

    path = tmp_path / "logs" / "migrate_region_enum_ids.csv"
    text = path.read_text(encoding="utf-8")
    assert "company_id,title,old_id,new_id,status" in text
    assert "1,Москва old,9008,9234,MIGRATED" in text


def test_failure_during_update_does_not_block_others():
    bx = FakeBitrix(
        [
            {"ID": "1", "TITLE": "Москва old", COMPANY_UF_REGION: "9008"},
            {"ID": "2", "TITLE": "Амурская old", COMPANY_UF_REGION: "8962"},
        ],
        fail_ids={"1"},
    )

    summary = stage.run(bx, dry_run=False)

    assert summary["failed"] == 1
    assert summary["migrated"] == 1
    assert [outcome["status"] for outcome in summary["outcomes"]] == ["FAILED", "MIGRATED"]
    assert bx.update_company_calls == [("2", {COMPANY_UF_REGION: "9172"})]
