from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from belberry.bitrix24.orchestration.dry_run import (
    DRY_RUN_ARTIFACT_FILENAME,
    DryRunArtifact,
    _ensure_inside_workspace,
    backup_fingerprint,
    build_dry_run_artifact,
    load_dry_run_artifact,
    write_dry_run_artifact,
    write_dry_run_package,
)
from belberry.bitrix24.orchestration.run import load_manifest
from belberry.bitrix24.policies.operation_key import POLICY_VERSION


class DryRunTests(unittest.TestCase):
    def _backup(self) -> dict:
        return {
            "deals": [
                {
                    "id": "20",
                    "deal": {"ID": "20", "TITLE": "Дубль", "DATE_CREATE": "2026-05-09T10:00:00+03:00"},
                    "contacts": [{"CONTACT_ID": "300", "SORT": "10"}],
                    "product_rows": [],
                    "activities": [{"ID": "a2"}],
                    "timeline_comments": [],
                },
                {
                    "id": "10",
                    "deal": {"ID": "10", "TITLE": "Цель", "DATE_CREATE": "2026-05-08T10:00:00+03:00"},
                    "contacts": [{"CONTACT_ID": "200", "SORT": "10"}],
                    "product_rows": [],
                    "activities": [{"ID": "a1"}],
                    "timeline_comments": [],
                },
            ],
            "meta": {"source": "unit"},
        }

    def _plan(self) -> dict:
        return {
            "ok": True,
            "status": "ready",
            "target_id": "10",
            "deal_updates": [{"deal_id": "20", "fields": {"TITLE": "Цель"}}],
            "contact_additions": [],
        }

    def _risk(self) -> dict:
        return {
            "ok": True,
            "status": "low_risk",
            "metrics": {"group_size": 2},
            "reasons": [],
        }

    def _artifact(self) -> DryRunArtifact:
        return build_dry_run_artifact(
            run_id="20260510-093000-MSK-abcdef12",
            created_at_msk="2026-05-10T09:30:00+03:00",
            sheet_id="sheet-123",
            operation_key="operation-key",
            domain="example.ru",
            target_id="10",
            deal_ids=["10", "20"],
            backup=self._backup(),
            policy_plan=self._plan(),
            risk=self._risk(),
        )

    def test_backup_fingerprint_is_stable_for_same_backup(self) -> None:
        first = backup_fingerprint(self._backup())
        second = backup_fingerprint(self._backup())

        self.assertEqual(first, second)
        self.assertRegex(first, r"^[0-9a-f]{64}$")

    def test_backup_fingerprint_ignores_deal_order(self) -> None:
        backup = self._backup()
        backup["deals"] = list(reversed(backup["deals"]))

        self.assertEqual(backup_fingerprint(self._backup()), backup_fingerprint(backup))

    def test_backup_fingerprint_changes_when_live_state_changes(self) -> None:
        backup = self._backup()
        backup["deals"][0]["deal"]["TITLE"] = "Изменено"

        self.assertNotEqual(backup_fingerprint(self._backup()), backup_fingerprint(backup))

    def test_backup_fingerprint_rejects_non_mapping(self) -> None:
        with self.assertRaisesRegex(ValueError, "backup"):
            backup_fingerprint(["not", "mapping"])  # type: ignore[arg-type]

    def test_build_dry_run_artifact_sets_policy_version_and_fingerprint(self) -> None:
        artifact = self._artifact()

        self.assertEqual(artifact.policy_version, POLICY_VERSION)
        self.assertEqual(artifact.backup_fingerprint, backup_fingerprint(self._backup()))
        self.assertEqual(artifact.deal_ids, ("10", "20"))
        self.assertEqual(artifact.status, "dry_run_written")

    def test_build_dry_run_artifact_rejects_single_deal_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "deal_ids"):
            build_dry_run_artifact(
                run_id="20260510-093000-MSK-abcdef12",
                sheet_id="sheet-123",
                operation_key="operation-key",
                domain="example.ru",
                target_id="10",
                deal_ids=["10"],
                backup=self._backup(),
                policy_plan=self._plan(),
                risk=self._risk(),
            )

    def test_build_dry_run_artifact_rejects_missing_required_text(self) -> None:
        with self.assertRaisesRegex(ValueError, "operation_key"):
            build_dry_run_artifact(
                run_id="20260510-093000-MSK-abcdef12",
                sheet_id="sheet-123",
                operation_key="",
                domain="example.ru",
                target_id="10",
                deal_ids=["10", "20"],
                backup=self._backup(),
                policy_plan=self._plan(),
                risk=self._risk(),
            )

    def test_write_dry_run_artifact_writes_private_json(self) -> None:
        artifact = self._artifact()
        with tempfile.TemporaryDirectory() as tmp:
            path = write_dry_run_artifact(Path(tmp) / artifact.run_id, artifact)

            self.assertEqual(path.name, DRY_RUN_ARTIFACT_FILENAME)
            self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["backup_fingerprint"], artifact.backup_fingerprint)
            self.assertEqual(payload["deal_ids"], ["10", "20"])

    def test_load_dry_run_artifact_roundtrip(self) -> None:
        artifact = self._artifact()
        with tempfile.TemporaryDirectory() as tmp:
            path = write_dry_run_artifact(Path(tmp) / artifact.run_id, artifact)

            loaded = load_dry_run_artifact(path)

        self.assertEqual(loaded, artifact)

    def test_load_dry_run_artifact_rejects_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / DRY_RUN_ARTIFACT_FILENAME
            path.write_text("{broken", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                load_dry_run_artifact(path)

    def test_load_dry_run_artifact_rejects_non_object_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / DRY_RUN_ARTIFACT_FILENAME
            path.write_text("[]", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "JSON object"):
                load_dry_run_artifact(path)

    def test_load_dry_run_artifact_rejects_missing_field(self) -> None:
        payload = self._artifact().to_json()
        del payload["risk"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / DRY_RUN_ARTIFACT_FILENAME
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "risk"):
                load_dry_run_artifact(path)

    def test_load_dry_run_artifact_rejects_non_list_deal_ids(self) -> None:
        payload = self._artifact().to_json()
        payload["deal_ids"] = "10,20"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / DRY_RUN_ARTIFACT_FILENAME
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "deal_ids"):
                load_dry_run_artifact(path)

    def test_load_dry_run_artifact_rejects_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "cannot be read"):
                load_dry_run_artifact(Path(tmp) / DRY_RUN_ARTIFACT_FILENAME)

    def test_write_dry_run_package_writes_artifact_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            package = write_dry_run_package(
                workspace_root=root,
                run_id="20260510-093000-MSK-abcdef12",
                created_at_msk="2026-05-10T09:30:00+03:00",
                sheet_id="sheet-123",
                operation_key="operation-key",
                domain="example.ru",
                target_id="10",
                deal_ids=["10", "20"],
                backup=self._backup(),
                policy_plan=self._plan(),
                risk=self._risk(),
            )

            self.assertTrue(package.artifact_path.exists())
            self.assertTrue(package.manifest_path.exists())
            self.assertEqual(package.artifact_path.relative_to(root), Path("outputs/runs/20260510-093000-MSK-abcdef12/dry_run_plan.json"))
            self.assertEqual(package.manifest_path.relative_to(root), Path("state/runs/20260510-093000-MSK-abcdef12/manifest.json"))
            self.assertEqual(package.manifest.dry_run_artifact, "outputs/runs/20260510-093000-MSK-abcdef12/dry_run_plan.json")
            self.assertEqual(package.manifest.fingerprint_at_dry_run, package.artifact.backup_fingerprint)
            self.assertEqual(load_manifest(package.manifest_path), package.manifest)
            self.assertEqual(load_dry_run_artifact(package.artifact_path), package.artifact)

    def test_write_dry_run_package_requires_existing_workspace_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "workspace_root"):
                write_dry_run_package(
                    workspace_root=Path(tmp) / "missing",
                    run_id="20260510-093000-MSK-abcdef12",
                    sheet_id="sheet-123",
                    operation_key="operation-key",
                    domain="example.ru",
                    target_id="10",
                    deal_ids=["10", "20"],
                    backup=self._backup(),
                    policy_plan=self._plan(),
                    risk=self._risk(),
                )

    def test_path_guard_rejects_path_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with self.assertRaisesRegex(ValueError, "outside workspace"):
                _ensure_inside_workspace(root.parent / "outside", workspace_root=root)

    def test_artifact_paths_do_not_contain_absolute_workspace_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = write_dry_run_package(
                workspace_root=Path(tmp),
                run_id="20260510-093000-MSK-abcdef12",
                sheet_id="sheet-123",
                operation_key="operation-key",
                domain="example.ru",
                target_id="10",
                deal_ids=["10", "20"],
                backup=self._backup(),
                policy_plan=self._plan(),
                risk=self._risk(),
            )

            self.assertFalse(package.manifest.dry_run_artifact.startswith(os.sep))


if __name__ == "__main__":
    unittest.main()
