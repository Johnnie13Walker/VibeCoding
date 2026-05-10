from __future__ import annotations

import io
import json
import runpy
import sys
import tempfile
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
    artifact_path: Path = Path("unused")
    manifest_path: Path = Path("unused")


class DuplicateMergeBatchCliTests(unittest.TestCase):
    def test_apply_mode_exits_without_calling_engine(self) -> None:
        with self.assertRaisesRegex(SystemExit, "apply not implemented"):
            duplicate_merge_batch.main(["--mode", "apply", "--run-id", "run", "--confirm-apply", "token"])

    def test_dry_run_prints_structured_summary(self) -> None:
        workspace_root = Path.cwd()
        result = BatchEngineResult(
            run_id="20260510-123000-MSK-aaaaaaaa",
            mode="dry-run",
            packages=(
                FakePackage(
                    artifact_path=workspace_root / "outputs" / "runs" / "x" / "dry_run_plan.json",
                    manifest_path=workspace_root / "state" / "runs" / "x" / "manifest.json",
                ),
            ),  # type: ignore[arg-type]
            skipped_groups=({"domain": "old.ru", "operation_key": "key"},),
            errors=(),
        )
        config = SimpleNamespace(portal_base_url="https://portal.example")

        with (
            patch.object(duplicate_merge_batch, "load_config", return_value=config),
            patch.object(duplicate_merge_batch.BitrixOAuth, "from_env", return_value=object()),
            patch.object(duplicate_merge_batch.GoogleSheetsClient, "from_env", return_value=object()),
            patch.object(duplicate_merge_batch, "ReconcileSettings", return_value=object()),
            patch.object(duplicate_merge_batch, "BatchEngineDeps", return_value=object()),
            patch.object(duplicate_merge_batch, "get_logger", return_value=object()),
            patch.object(duplicate_merge_batch, "_workspace_root", return_value=workspace_root),
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
        self.assertEqual(payload["packages"][0]["artifact"], "outputs/runs/x/dry_run_plan.json")
        self.assertEqual(payload["packages"][0]["manifest"], "state/runs/x/manifest.json")
        self.assertFalse(payload["packages"][0]["artifact"].startswith("/"))
        self.assertFalse(payload["packages"][0]["manifest"].startswith("/"))
        self.assertEqual(payload["skipped_groups"][0]["domain"], "old.ru")

    def test_logger_is_passed_to_engine(self) -> None:
        logger = object()
        deps = object()
        result = BatchEngineResult("run", "dry-run", (), (), ())
        config = SimpleNamespace(portal_base_url="https://portal.example")

        with (
            patch.object(duplicate_merge_batch, "load_config", return_value=config),
            patch.object(duplicate_merge_batch.BitrixOAuth, "from_env", return_value=object()),
            patch.object(duplicate_merge_batch.GoogleSheetsClient, "from_env", return_value=object()),
            patch.object(duplicate_merge_batch, "ReconcileSettings", return_value=object()),
            patch.object(duplicate_merge_batch, "get_logger", return_value=logger) as get_logger,
            patch.object(duplicate_merge_batch, "BatchEngineDeps", return_value=deps) as deps_factory,
            patch.object(duplicate_merge_batch, "_workspace_root", return_value=Path.cwd()),
            patch.object(duplicate_merge_batch, "run_dry_run_batch", return_value=result),
        ):
            with redirect_stdout(io.StringIO()):
                duplicate_merge_batch.main(["--mode", "dry-run"])

        get_logger.assert_called_once_with(component="duplicate_merge_batch")
        self.assertIs(deps_factory.call_args.kwargs["logger"], logger)

    def test_summary_keeps_external_paths_when_relative_to_fails(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir, tempfile.TemporaryDirectory() as outside_dir:
            outside = Path(outside_dir) / "dry_run_plan.json"

            self.assertEqual(
                duplicate_merge_batch._display_path(outside, workspace_root=Path(workspace_dir)),
                str(outside),
            )

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
