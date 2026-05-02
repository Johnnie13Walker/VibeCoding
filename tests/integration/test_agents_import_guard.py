from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

SCAN_ROOTS = (
    "apps",
    "cloudbot",
    "checks",
    "infra",
    "scripts",
    "shared",
)

SCAN_SUFFIXES = {".py", ".sh", ".js", ".mjs"}

AGENTS_IMPORT_RE = re.compile(r"^\s*(?:from\s+agents\.|import\s+agents\.)", re.MULTILINE)

ALLOWED_PATHS = {
    # Compatibility packages intentionally re-export canonical apps.
    "agents",
    # Existing workflow sends a one-off note through the Larisa compatibility provider.
    # Keep this explicit until wrapper cutover moves it to apps.larisa_ivanovna.
    "infra/orchestrator/workflows/larisa_send_note.sh",
}


def _is_allowed(relative_path: str) -> bool:
    return relative_path == "agents" or relative_path.startswith("agents/") or relative_path in ALLOWED_PATHS


class AgentsImportGuardTests(unittest.TestCase):
    def test_production_code_does_not_add_new_agents_imports(self) -> None:
        violations: list[str] = []

        for root_name in SCAN_ROOTS:
            root = ROOT / root_name
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
                    continue
                relative_path = path.relative_to(ROOT).as_posix()
                if _is_allowed(relative_path):
                    continue
                text = path.read_text(encoding="utf-8")
                if AGENTS_IMPORT_RE.search(text):
                    violations.append(relative_path)

        self.assertEqual(
            violations,
            [],
            "Новые production imports через agents.* запрещены; используйте canonical apps/* или добавьте явный compatibility exception.",
        )
