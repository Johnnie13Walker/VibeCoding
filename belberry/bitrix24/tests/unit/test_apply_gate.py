from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from belberry.bitrix24.orchestration import ledger
from belberry.bitrix24.orchestration.apply_gate import validate_apply_preflight
from belberry.bitrix24.orchestration.dry_run import write_dry_run_package
from belberry.bitrix24.orchestration.ledger import MergeLedgerRecord
from belberry.bitrix24.orchestration.run import write_manifest
from belberry.bitrix24.policies.operation_key import POLICY_VERSION


class ApplyGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.run_id = "20260510-093000-MSK-abcdef12"
        self.operation_key = "sheet=sheet-123|domain=example.ru|target=10|ids=10,20|policy=2026.05.10"
        self.package = write_dry_run_package(
            workspace_root=self.root,
            run_id=self.run_id,
            created_at_msk="2026-05-10T09:30:00+03:00",
            sheet_id="sheet-123",
            operation_key=self.operation_key,
            domain="example.ru",
            target_id="10",
            deal_ids=["10", "20"],
            backup=self._backup(),
            policy_plan={"ok": True, "status": "ready", "target_id": "10"},
            risk={"ok": True, "status": "low_risk"},
        )
        self.ledger_path = self.root / "state" / "ledger.jsonl"

    def _backup(self) -> dict:
        return {
            "deals": [
                {"id": "10", "deal": {"ID": "10", "TITLE": "target"}},
                {"id": "20", "deal": {"ID": "20", "TITLE": "duplicate"}},
            ]
        }

    def _decision(self, **overrides):
        kwargs = dict(
            workspace_root=self.root,
            run_id=self.run_id,
            provided_token=self.package.manifest.confirm_token,
            current_live_fingerprint=self.package.manifest.fingerprint_at_dry_run,
            ledger_path=self.ledger_path,
            lock_acquired=True,
            apply_disabled=False,
        )
        kwargs.update(overrides)
        return validate_apply_preflight(**kwargs)

    def _ledger_record(self, *, status: str) -> MergeLedgerRecord:
        return MergeLedgerRecord(
            operation_key=self.operation_key,
            sheet_id="sheet-123",
            domain="example.ru",
            target_id="10",
            deal_ids=("10", "20"),
            policy_version=POLICY_VERSION,
            status=status,
            crm_status="started",
            sheet_status="not_ready",
            run_id=self.run_id,
            dry_run_artifact=self.package.manifest.dry_run_artifact,
        )

    def test_all_gates_pass_for_fresh_dry_run(self) -> None:
        decision = self._decision()

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reasons, ())
        self.assertEqual(decision.manifest, self.package.manifest)
        self.assertEqual(decision.artifact, self.package.artifact)

    def test_require_allowed_raises_when_blocked(self) -> None:
        decision = self._decision(provided_token="wrong")

        with self.assertRaisesRegex(RuntimeError, "invalid_apply_token_or_manifest"):
            decision.require_allowed()

    def test_missing_manifest_blocks_apply(self) -> None:
        decision = self._decision(run_id="20260510-093001-MSK-abcdef12")

        self.assertFalse(decision.allowed)
        self.assertIn("invalid_apply_token_or_manifest", decision.reasons)

    def test_invalid_run_id_blocks_before_manifest_path_read(self) -> None:
        decision = self._decision(run_id="../../outside")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reasons, ("invalid_run_id",))

    def test_wrong_token_blocks_apply(self) -> None:
        decision = self._decision(provided_token="MERGE_REANIMATION_wrong")

        self.assertFalse(decision.allowed)
        self.assertIn("invalid_apply_token_or_manifest", decision.reasons)

    def test_non_confirmable_manifest_blocks_apply(self) -> None:
        updated = self.package.manifest.__class__(
            **{**self.package.manifest.to_json(), "mode": "apply", "status": "apply_started"}
        )

        write_manifest(self.package.manifest_path.parent, updated)

        decision = self._decision()

        self.assertFalse(decision.allowed)
        self.assertIn("manifest_not_confirmable", decision.reasons)

    def test_confirm_pending_status_allows_apply_mode_manifest(self) -> None:
        updated = self.package.manifest.__class__(
            **{**self.package.manifest.to_json(), "mode": "apply", "status": "confirm_pending"}
        )

        write_manifest(self.package.manifest_path.parent, updated)

        decision = self._decision()

        self.assertTrue(decision.allowed)

    def test_missing_artifact_blocks_apply(self) -> None:
        self.package.artifact_path.unlink()

        decision = self._decision()

        self.assertFalse(decision.allowed)
        self.assertIn("dry_run_artifact_unreadable", decision.reasons)

    def test_absolute_artifact_path_inside_workspace_is_allowed(self) -> None:
        updated = self.package.manifest.__class__(
            **{**self.package.manifest.to_json(), "dry_run_artifact": str(self.package.artifact_path)}
        )
        write_manifest(self.package.manifest_path.parent, updated)

        decision = self._decision()

        self.assertTrue(decision.allowed)

    def test_fingerprint_mismatch_blocks_apply(self) -> None:
        decision = self._decision(current_live_fingerprint="0" * 64)

        self.assertFalse(decision.allowed)
        self.assertIn("fingerprint_mismatch", decision.reasons)

    def test_ledger_applied_status_blocks_apply(self) -> None:
        ledger.append_record(self.ledger_path, self._ledger_record(status="crm_applied_sheet_pending"))

        decision = self._decision()

        self.assertFalse(decision.allowed)
        self.assertIn("operation_already_applied", decision.reasons)

    def test_ledger_unknown_status_blocks_retry(self) -> None:
        ledger.append_record(self.ledger_path, self._ledger_record(status="apply_unknown_needs_reconcile"))

        decision = self._decision()

        self.assertFalse(decision.allowed)
        self.assertIn("operation_locked_for_retry", decision.reasons)

    def test_ledger_path_outside_workspace_blocks_apply(self) -> None:
        decision = self._decision(ledger_path=self.root.parent / "ledger.jsonl")

        self.assertFalse(decision.allowed)
        self.assertIn("ledger_path_outside_workspace", decision.reasons)

    def test_missing_process_lock_blocks_apply(self) -> None:
        decision = self._decision(lock_acquired=False)

        self.assertFalse(decision.allowed)
        self.assertIn("process_lock_not_acquired", decision.reasons)

    def test_apply_disabled_blocks_apply(self) -> None:
        decision = self._decision(apply_disabled=True)

        self.assertFalse(decision.allowed)
        self.assertIn("apply_disabled", decision.reasons)

    def test_artifact_operation_key_mismatch_blocks_apply(self) -> None:
        payload = self.package.artifact.to_json()
        payload["operation_key"] = "other"
        self.package.artifact_path.write_text(json.dumps(payload), encoding="utf-8")

        decision = self._decision()

        self.assertFalse(decision.allowed)
        self.assertIn("artifact_operation_key_mismatch", decision.reasons)


if __name__ == "__main__":
    unittest.main()
