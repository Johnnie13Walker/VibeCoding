import tempfile
import unittest
from pathlib import Path

from belberry.bitrix24.config import loader


def _valid_env(workspace_root: Path) -> dict[str, str]:
    return {
        "BELBERRY_BITRIX24_TIMEZONE": "Europe/Moscow",
        "BELBERRY_BITRIX24_PORTAL_BASE_URL": "https://example.bitrix24.ru/",
        "BELBERRY_BITRIX24_DEFAULT_MODE": "dry-run",
        "BELBERRY_BITRIX24_REQUIRE_APPLY_CONFIRMATION": "true",
        "BELBERRY_BITRIX24_PROCESS_LOCK_PATH": "state/duplicate-merge.lock",
        "BELBERRY_BITRIX24_LEDGER_PATH": "state/duplicate-merge-ledger.jsonl",
        "BELBERRY_BITRIX24_DUPLICATES_SHEET_ID": "1abcXYZ",
        "BELBERRY_BITRIX24_DUPLICATES_WORK_SHEET": "Дубли",
        "BELBERRY_BITRIX24_DUPLICATES_ARCHIVE_SHEET": "Объединено",
        "BELBERRY_BITRIX24_DUPLICATES_SOURCE_SHEET": "Источник",
        "BELBERRY_BITRIX24_GOOGLE_SERVICE_ACCOUNT_JSON": "state/google-sa.json",
        "BELBERRY_BITRIX24_APP_STATE_DIR": "state/bitrix-oauth",
    }


class AssertNoLegacyEnvTests(unittest.TestCase):
    def test_legacy_bitrix_namespace_rejected(self):
        with self.assertRaises(loader.ConfigError):
            loader.assert_no_legacy_env({"BITRIX_APP_STATE_DIR": "/opt/openclaw/state/bitrix_app"})

    def test_legacy_openclaw_namespace_rejected(self):
        with self.assertRaises(loader.ConfigError):
            loader.assert_no_legacy_env({"OPENCLAW_HOME": "/opt/openclaw"})

    def test_marketing_namespace_rejected(self):
        with self.assertRaises(loader.ConfigError):
            loader.assert_no_legacy_env({"MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON": "/tmp/x.json"})

    def test_belberry_namespace_accepted(self):
        loader.assert_no_legacy_env({"BELBERRY_BITRIX24_PORTAL_BASE_URL": "https://x"})


class EnforcePathInsideWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_relative_path_inside_workspace_accepted(self):
        result = loader.enforce_path_inside_workspace(Path("state/x.lock"), workspace_root=self.root)
        self.assertEqual(result, (self.root / "state/x.lock").resolve())

    def test_absolute_path_outside_workspace_rejected(self):
        with self.assertRaises(loader.ConfigError):
            loader.enforce_path_inside_workspace(Path("/etc/passwd"), workspace_root=self.root)

    def test_dotdot_traversal_rejected(self):
        with self.assertRaises(loader.ConfigError):
            loader.enforce_path_inside_workspace(Path("../../etc/passwd"), workspace_root=self.root)

    def test_legacy_openclaw_path_rejected(self):
        with self.assertRaises(loader.ConfigError):
            loader.enforce_path_inside_workspace(
                Path("/opt/openclaw/state/bitrix_app"),
                workspace_root=self.root,
            )


class IsApplyDisabledTests(unittest.TestCase):
    def test_default_when_missing_is_blocked(self):
        self.assertTrue(loader.is_apply_disabled({}))

    def test_explicit_true_blocks(self):
        self.assertTrue(loader.is_apply_disabled({"BELBERRY_BITRIX24_APPLY_DISABLED": "true"}))

    def test_only_explicit_false_unlocks(self):
        self.assertFalse(loader.is_apply_disabled({"BELBERRY_BITRIX24_APPLY_DISABLED": "false"}))

    def test_garbage_value_blocks(self):
        self.assertTrue(loader.is_apply_disabled({"BELBERRY_BITRIX24_APPLY_DISABLED": "maybe"}))

    def test_case_insensitive_false(self):
        self.assertFalse(loader.is_apply_disabled({"BELBERRY_BITRIX24_APPLY_DISABLED": "FALSE"}))


class LoadConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_load_config_normalizes_paths(self):
        cfg = loader.load_config(_valid_env(self.root), workspace_root=self.root)
        self.assertEqual(cfg.process_lock_path, (self.root / "state/duplicate-merge.lock").resolve())
        self.assertEqual(cfg.ledger_path, (self.root / "state/duplicate-merge-ledger.jsonl").resolve())
        self.assertEqual(cfg.portal_base_url, "https://example.bitrix24.ru")
        self.assertTrue(cfg.apply_disabled)
        self.assertEqual(cfg.default_mode, "dry-run")
        self.assertEqual(cfg.batch_limits.max_group_size, 2)

    def test_missing_required_key_raises(self):
        env = _valid_env(self.root)
        env.pop("BELBERRY_BITRIX24_LEDGER_PATH")
        with self.assertRaises(loader.ConfigError):
            loader.load_config(env, workspace_root=self.root)

    def test_legacy_env_present_raises(self):
        env = _valid_env(self.root)
        env["BITRIX_APP_STATE_DIR"] = "/opt/openclaw/state"
        with self.assertRaises(loader.ConfigError):
            loader.load_config(env, workspace_root=self.root)

    def test_invalid_timezone_rejected(self):
        env = _valid_env(self.root)
        env["BELBERRY_BITRIX24_TIMEZONE"] = "UTC"
        with self.assertRaises(loader.ConfigError):
            loader.load_config(env, workspace_root=self.root)

    def test_path_outside_workspace_rejected(self):
        env = _valid_env(self.root)
        env["BELBERRY_BITRIX24_LEDGER_PATH"] = "/tmp/ledger.jsonl"
        with self.assertRaises(loader.ConfigError):
            loader.load_config(env, workspace_root=self.root)

    def test_apply_unlocked_when_explicit_false(self):
        env = _valid_env(self.root)
        env["BELBERRY_BITRIX24_APPLY_DISABLED"] = "false"
        cfg = loader.load_config(env, workspace_root=self.root)
        self.assertFalse(cfg.apply_disabled)

    def test_invalid_default_mode_rejected(self):
        env = _valid_env(self.root)
        env["BELBERRY_BITRIX24_DEFAULT_MODE"] = "yolo"
        with self.assertRaises(loader.ConfigError):
            loader.load_config(env, workspace_root=self.root)

    def test_install_state_file_optional_and_path_guarded(self):
        env = _valid_env(self.root)
        env["BELBERRY_BITRIX24_APP_INSTALL_STATE_FILE"] = "state/bitrix-oauth/install.latest.json"
        cfg = loader.load_config(env, workspace_root=self.root)
        self.assertEqual(
            cfg.bitrix_app_install_state_file,
            (self.root / "state/bitrix-oauth/install.latest.json").resolve(),
        )

    def test_install_state_file_outside_workspace_rejected(self):
        env = _valid_env(self.root)
        env["BELBERRY_BITRIX24_APP_INSTALL_STATE_FILE"] = "/tmp/install.json"
        with self.assertRaises(loader.ConfigError):
            loader.load_config(env, workspace_root=self.root)


if __name__ == "__main__":
    unittest.main()
