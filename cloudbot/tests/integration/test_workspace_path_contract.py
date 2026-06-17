from __future__ import annotations

import stat
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class WorkspacePathContractTests(unittest.TestCase):
    def test_larisa_finalize_does_not_pin_old_engineer_root(self) -> None:
        script = ROOT / "scripts" / "larisa_finalize.sh"
        text = script.read_text(encoding="utf-8")

        self.assertNotIn("/Users/pro2kuror/Desktop/OpenClo/projects/engineer", text)
        self.assertIn("CLOUDBOT_ENGINEER_ROOT", text)
        self.assertIn('cd "$REPO_ROOT"', text)

    def test_codex_workspace_verify_script_is_non_destructive(self) -> None:
        script = ROOT / "scripts" / "verify_codex_workspace.sh"
        text = script.read_text(encoding="utf-8")

        self.assertTrue(script.stat().st_mode & stat.S_IXUSR)
        self.assertIn("/Users/pro2kuror/Desktop/CODEX", text)
        self.assertNotIn(" rm ", text)
        self.assertNotIn(" rmdir ", text)
        self.assertNotIn(" mv ", text)


if __name__ == "__main__":
    unittest.main()
