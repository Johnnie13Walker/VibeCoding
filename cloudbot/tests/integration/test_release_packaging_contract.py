from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LIB_SH = ROOT / "infra" / "orchestrator" / "lib.sh"

REQUIRED_RUNTIME_PATHS = {
    "agents/larisa_ivanovna",
    "agents/lev_petrovich",
    "agents/sales_agent",
    "apps/finansist",
    "apps/larisa_ivanovna",
    "apps/lev_petrovich",
    "cloudbot/business_day.py",
    "infra/orchestrator/lib.sh",
    "infra/orchestrator/run_workflow.sh",
    "scripts/run_sales_copilot.py",
    "shared/contracts",
    "shared/time",
}


def _runtime_files_from_lib() -> set[str]:
    text = LIB_SH.read_text(encoding="utf-8")
    match = re.search(r"cloudbot_runtime_files\(\)\s*\{\s*cat <<'EOF'\n(?P<body>.*?)\n\s*EOF\n\}", text, re.DOTALL)
    if not match:
        raise AssertionError("Не найден cloudbot_runtime_files() manifest в infra/orchestrator/lib.sh")
    return {line.strip() for line in match.group("body").splitlines() if line.strip()}


class ReleasePackagingContractTests(unittest.TestCase):
    def test_runtime_manifest_includes_canonical_apps_and_shared_layers(self) -> None:
        runtime_files = _runtime_files_from_lib()
        missing = sorted(REQUIRED_RUNTIME_PATHS - runtime_files)

        self.assertEqual(missing, [], "Release archive manifest misses required runtime paths")

    def test_required_runtime_paths_exist_locally(self) -> None:
        missing = sorted(path for path in REQUIRED_RUNTIME_PATHS if not (ROOT / path).exists())

        self.assertEqual(missing, [], "Required runtime paths are listed but missing locally")
