from __future__ import annotations

import io
import json
import runpy
import sys
import unittest
import warnings
from types import SimpleNamespace
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from belberry.bitrix24.orchestration.batch_engine import BatchEngineResult
from belberry.bitrix24.scripts import duplicate_merge_batch


@dataclass(frozen=True)
class FakeArtifact:
    domain: str = "example.ru"
    target_id: str = "10"
    deal_ids: tuple[str, ...] = ("10", "20")
    risk: dict = None
    policy_plan: dict = None

    def __post_init__(self):
        object.__setattr__(self, "risk", self.risk or {"status": "low_risk"})
        object.__setattr__(self, "policy_plan", self.policy_plan or {"status": "ready"})


@dataclass(frozen=True)
class FakeManifest:
    run_id: str = "20260510-123000-MSK-aaaaaaaa"


@dataclass(frozen=True)
class FakePackage:
    manifest: FakeManifest = FakeManifest()
    artifact: FakeArtifact = FakeArtifact()
    artifact_path: Path = Path("/workspace/outputs/runs/x/dry_run_plan.json")
    manifest_path: Path = Path("/workspace/state/runs/x/manifest.json")


class DuplicateMergeBatchCliTests(unittest.TestCase):
    def test_apply_mode_exits_without_calling_engine(self) -> None:
        with self.assertRaisesRegex(SystemExit, "apply not implemented"):
            duplicate_merge_batch.main(["--mode", "apply", "--run-id", "run", "--confirm-apply", "token"])

    def test_dry_run_prints_structured_summary(self) -> None:
        result = BatchEngineResult(
            run_id="20260510-123000-MSK-aaaaaaaa",
            mode="dry-run",
            packages=(FakePackage(),),  # type: ignore[arg-type]
            skipped_groups=({"domain": "old.ru", "operation_key": "key"},),
            errors=(),
        )

        with (
            patch.object(duplicate_merge_batch, "load_config", return_value=SimpleNamespace(portal_base_url="https://portal.example")),
            patch.object(duplicate_merge_batch.BitrixOAuth, "from_env", return_value=object()),
            patch.object(duplicate_merge_batch.GoogleSheetsClient, "from_env", return_value=object()),
            patch.object(duplicate_merge_batch, "ReconcileSettings", return_value=object()),
            patch.object(duplicate_merge_batch, "BatchEngineDeps", return_value=object()),
            patch.object(duplicate_merge_batch, "run_dry_run_batch", return_value=result) as run_batch,
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = duplicate_merge_batch.main(["--mode", "dry-run", "--group-domain", "example.ru", "--max-groups", "3"])

        self.assertEqual(exit_code, 0)
        run_batch.assert_called_once()
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["mode"], "dry-run")
        self.assertEqual(payload["packages"][0]["domain"], "example.ru")
        self.assertEqual(payload["skipped_groups"][0]["domain"], "old.ru")

    def test_parser_defaults_max_groups_to_one(self) -> None:
        args = duplicate_merge_batch.build_parser().parse_args(["--mode", "dry-run"])

        self.assertEqual(args.max_groups, 1)
        self.assertIsNone(args.group_domain)

    def test_module_entrypoint_raises_system_exit(self) -> None:
        with patch.object(sys, "argv", ["duplicate_merge_batch.py", "--mode", "apply"]):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                with self.assertRaisesRegex(SystemExit, "apply not implemented"):
                    runpy.run_module("belberry.bitrix24.scripts.duplicate_merge_batch", run_name="__main__")


if __name__ == "__main__":
    unittest.main()
