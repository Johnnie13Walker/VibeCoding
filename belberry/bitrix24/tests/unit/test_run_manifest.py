from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from belberry.bitrix24.orchestration.run import (
    ApplyForbidden,
    RunManifest,
    create_manifest,
    generate_run_id,
    load_manifest,
    validate_apply_request,
    write_manifest,
)
from belberry.bitrix24.policies.operation_key import POLICY_VERSION


class RunManifestTests(unittest.TestCase):
    def _manifest(self) -> RunManifest:
        return create_manifest(
            run_id="20260510-093000-MSK-abcdef12",
            started_at_msk="2026-05-10T09:30:00+03:00",
            sheet_id="sheet-123",
            operation_key="sheet=sheet-123|domain=example.ru|target=1|ids=1,2|policy=2026.05.10",
            mode="dry-run",
            dry_run_artifact="state/runs/20260510-093000-MSK-abcdef12/dry-run.json",
            fingerprint_at_dry_run="fp-1",
        )

    def test_generate_run_id_uses_msk_timestamp_and_hex_suffix(self) -> None:
        now = datetime(2026, 5, 10, 6, 30, 0, tzinfo=timezone.utc)
        with patch("belberry.bitrix24.orchestration.run.secrets.token_hex", return_value="a1b2c3d4"):
            run_id = generate_run_id(now)

        self.assertEqual(run_id, "20260510-093000-MSK-a1b2c3d4")

    def test_generate_run_id_matches_contract(self) -> None:
        run_id = generate_run_id(datetime(2026, 5, 10, 9, 30, 0))

        self.assertRegex(run_id, r"^20260510-093000-MSK-[0-9a-f]{8}$")

    def test_create_manifest_sets_confirm_token_and_defaults(self) -> None:
        manifest = create_manifest(
            run_id="20260510-093000-MSK-abcdef12",
            sheet_id="sheet-123",
            operation_key="operation-key",
            mode="dry-run",
            dry_run_artifact="state/runs/20260510-093000-MSK-abcdef12/dry-run.json",
        )

        self.assertEqual(manifest.confirm_token, "MERGE_REANIMATION_20260510-093000-MSK-abcdef12")
        self.assertEqual(manifest.policy_version, POLICY_VERSION)
        self.assertEqual(manifest.status, "dry_run_written")
        self.assertIn("+03:00", manifest.started_at_msk)

    def test_create_manifest_rejects_invalid_run_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "run_id"):
            create_manifest(
                run_id="20260510-093000-UTC-abcdef12",
                sheet_id="sheet-123",
                operation_key="operation-key",
                mode="dry-run",
                dry_run_artifact="state/runs/run/dry-run.json",
            )

    def test_create_manifest_rejects_invalid_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "mode"):
            create_manifest(
                run_id="20260510-093000-MSK-abcdef12",
                sheet_id="sheet-123",
                operation_key="operation-key",
                mode="preview",
                dry_run_artifact="state/runs/run/dry-run.json",
            )

    def test_create_manifest_rejects_missing_dry_run_artifact(self) -> None:
        with self.assertRaisesRegex(ValueError, "dry_run_artifact"):
            create_manifest(
                run_id="20260510-093000-MSK-abcdef12",
                sheet_id="sheet-123",
                operation_key="operation-key",
                mode="dry-run",
                dry_run_artifact="",
            )

    def test_create_manifest_accepts_datetime_started_at_msk(self) -> None:
        manifest = create_manifest(
            run_id="20260510-093000-MSK-abcdef12",
            started_at_msk=datetime(2026, 5, 10, 6, 30, 0, tzinfo=timezone.utc),
            sheet_id="sheet-123",
            operation_key="operation-key",
            mode="dry-run",
            dry_run_artifact="state/runs/run/dry-run.json",
        )

        self.assertEqual(manifest.started_at_msk, "2026-05-10T09:30:00+03:00")

    def test_create_manifest_rejects_empty_started_at_msk(self) -> None:
        with self.assertRaisesRegex(ValueError, "started_at_msk"):
            create_manifest(
                run_id="20260510-093000-MSK-abcdef12",
                started_at_msk="",
                sheet_id="sheet-123",
                operation_key="operation-key",
                mode="dry-run",
                dry_run_artifact="state/runs/run/dry-run.json",
            )

    def test_create_manifest_rejects_invalid_run_id_calendar_date(self) -> None:
        with self.assertRaisesRegex(ValueError, "timestamp"):
            create_manifest(
                run_id="20260230-093000-MSK-abcdef12",
                sheet_id="sheet-123",
                operation_key="operation-key",
                mode="dry-run",
                dry_run_artifact="state/runs/run/dry-run.json",
            )

    def test_write_manifest_writes_json_with_private_permissions(self) -> None:
        manifest = self._manifest()
        with tempfile.TemporaryDirectory() as tmp:
            path = write_manifest(Path(tmp) / manifest.run_id, manifest)

            self.assertEqual(path.name, "manifest.json")
            self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["run_id"], manifest.run_id)
            self.assertEqual(payload["confirm_token"], manifest.confirm_token)

    def test_write_manifest_replaces_existing_file(self) -> None:
        manifest = self._manifest()
        with tempfile.TemporaryDirectory() as tmp:
            manifest_dir = Path(tmp) / manifest.run_id
            path = write_manifest(manifest_dir, manifest)
            second = create_manifest(
                run_id=manifest.run_id,
                started_at_msk=manifest.started_at_msk,
                sheet_id=manifest.sheet_id,
                operation_key=manifest.operation_key,
                mode="apply",
                dry_run_artifact=manifest.dry_run_artifact,
                fingerprint_at_dry_run="fp-2",
                status="apply_token_confirmed",
            )

            replaced = write_manifest(manifest_dir, second)

            self.assertEqual(replaced, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["mode"], "apply")
            self.assertEqual(payload["fingerprint_at_dry_run"], "fp-2")
            self.assertEqual(list(manifest_dir.glob("*.tmp")), [])

    def test_load_manifest_roundtrip(self) -> None:
        manifest = self._manifest()
        with tempfile.TemporaryDirectory() as tmp:
            path = write_manifest(Path(tmp) / manifest.run_id, manifest)

            loaded = load_manifest(path)

        self.assertEqual(loaded, manifest)

    def test_load_manifest_rejects_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text("{broken", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                load_manifest(path)

    def test_load_manifest_rejects_non_object_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text("[]", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "JSON object"):
                load_manifest(path)

    def test_load_manifest_rejects_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "cannot be read"):
                load_manifest(Path(tmp) / "missing-manifest.json")

    def test_load_manifest_rejects_missing_required_field(self) -> None:
        manifest = self._manifest().to_json()
        del manifest["operation_key"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "operation_key"):
                load_manifest(path)

    def test_load_manifest_rejects_mismatched_confirm_token(self) -> None:
        manifest = self._manifest().to_json()
        manifest["confirm_token"] = "MERGE_REANIMATION_wrong"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "confirm_token"):
                load_manifest(path)

    def test_validate_apply_request_accepts_exact_token_and_run_id(self) -> None:
        manifest = self._manifest()

        validate_apply_request(
            manifest,
            provided_token=manifest.confirm_token,
            provided_run_id=manifest.run_id,
        )

    def test_validate_apply_request_rejects_wrong_run_id(self) -> None:
        manifest = self._manifest()

        with self.assertRaisesRegex(ApplyForbidden, "run_id"):
            validate_apply_request(
                manifest,
                provided_token=manifest.confirm_token,
                provided_run_id="20260510-093001-MSK-abcdef12",
            )

    def test_validate_apply_request_rejects_wrong_token(self) -> None:
        manifest = self._manifest()

        with self.assertRaisesRegex(ApplyForbidden, "confirm token"):
            validate_apply_request(
                manifest,
                provided_token="MERGE_REANIMATION_wrong",
                provided_run_id=manifest.run_id,
            )

    def test_run_id_pattern_stays_strict(self) -> None:
        generated = generate_run_id(datetime(2026, 5, 10, 9, 30, 0))

        self.assertTrue(re.fullmatch(r"\d{8}-\d{6}-MSK-[0-9a-f]{8}", generated))
        self.assertNotIn(os.sep, generated)


if __name__ == "__main__":
    unittest.main()
