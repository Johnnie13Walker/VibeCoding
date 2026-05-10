import json
import tempfile
import unittest
from pathlib import Path

from belberry.bitrix24.providers import logging as jsonl_logger


class MaskingTests(unittest.TestCase):
    def test_mask_secret_short_returns_stars(self):
        self.assertEqual(jsonl_logger.mask_secret("abc"), "***")

    def test_mask_secret_long_keeps_edges(self):
        self.assertEqual(jsonl_logger.mask_secret("0123456789abcdef"), "0123***cdef")

    def test_mask_secret_empty_returns_empty(self):
        self.assertEqual(jsonl_logger.mask_secret(""), "")
        self.assertEqual(jsonl_logger.mask_secret(None), "")

    def test_mask_url_strips_path(self):
        self.assertEqual(
            jsonl_logger.mask_url("https://example.com/rest/abc/secret/method.json"),
            "https://example.com/***",
        )

    def test_mask_url_invalid_returns_stars(self):
        self.assertEqual(jsonl_logger.mask_url("not-a-url"), "***")


class SanitizeTests(unittest.TestCase):
    def test_secret_keys_masked_in_dict(self):
        result = jsonl_logger.sanitize({
            "access_token": "abcdefghij1234567890",
            "refresh_token": "xyz123abc456def789",
            "domain": "example.bitrix24.ru",
        })
        self.assertEqual(result["access_token"], "abcd***7890")
        self.assertEqual(result["refresh_token"], "xyz1***f789")
        self.assertEqual(result["domain"], "example.bitrix24.ru")

    def test_nested_secrets_masked(self):
        result = jsonl_logger.sanitize({
            "auth": {
                "auth[access_token]": "abcdefghij1234567890",
                "domain": "example.ru",
            },
            "items": [{"api_key": "supersecretkey1234"}],
        })
        self.assertEqual(result["auth"]["auth[access_token]"], "abcd***7890")
        self.assertEqual(result["auth"]["domain"], "example.ru")
        self.assertEqual(result["items"][0]["api_key"], "supe***1234")

    def test_url_in_string_value_masked(self):
        result = jsonl_logger.sanitize({"message": "Failed: https://example.com/rest/abc/method.json"})
        self.assertIn("https://example.com/***", result["message"])
        self.assertNotIn("/rest/abc/method.json", result["message"])

    def test_non_secret_strings_preserved(self):
        result = jsonl_logger.sanitize({"deal_id": "12345", "domain": "example.ru"})
        self.assertEqual(result, {"deal_id": "12345", "domain": "example.ru"})

    def test_private_key_masked_in_service_account_payload(self):
        result = jsonl_logger.sanitize({
            "client_email": "sa@example.iam.gserviceaccount.com",
            "private_key": "-----BEGIN PRIVATE KEY-----\nMIIE...secret...\n-----END PRIVATE KEY-----",
        })
        self.assertEqual(result["client_email"], "sa@example.iam.gserviceaccount.com")
        self.assertNotIn("MIIE", result["private_key"])
        self.assertEqual(result["private_key"][:4], "----")


class JsonlLoggerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "log.jsonl"

    def _read_lines(self) -> list[dict]:
        text = self.path.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(line) for line in text]

    def test_info_writes_jsonl_record(self):
        log = jsonl_logger.JsonlLogger(path=self.path, component="batch_engine", run_id="r1")
        log.info("dry_run_started", group_size=2)
        records = self._read_lines()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["level"], "info")
        self.assertEqual(records[0]["component"], "batch_engine")
        self.assertEqual(records[0]["event"], "dry_run_started")
        self.assertEqual(records[0]["run_id"], "r1")
        self.assertEqual(records[0]["group_size"], 2)
        self.assertIn("ts_msk", records[0])

    def test_secrets_in_fields_masked(self):
        log = jsonl_logger.JsonlLogger(path=self.path, component="oauth")
        log.info("oauth_refresh", access_token="abcdefghij1234567890", domain="ex.ru")
        record = self._read_lines()[0]
        self.assertEqual(record["access_token"], "abcd***7890")
        self.assertEqual(record["domain"], "ex.ru")

    def test_extra_context_merged_into_each_record(self):
        log = jsonl_logger.JsonlLogger(
            path=self.path,
            component="ledger",
            run_id="r2",
            extra={"sheet_id": "s1", "policy_version": "v"},
        )
        log.warn("group_skipped", reason="manual_review")
        record = self._read_lines()[0]
        self.assertEqual(record["sheet_id"], "s1")
        self.assertEqual(record["policy_version"], "v")
        self.assertEqual(record["reason"], "manual_review")
        self.assertEqual(record["level"], "warn")

    def test_url_in_message_masked(self):
        log = jsonl_logger.JsonlLogger(path=self.path, component="x")
        log.error("http_failed", message="POST https://example.com/rest/abc/m.json returned 500")
        record = self._read_lines()[0]
        self.assertIn("https://example.com/***", record["message"])
        self.assertNotIn("/rest/abc", record["message"])

    def test_log_path_parent_created_automatically(self):
        nested = Path(self.tmp.name) / "a" / "b" / "c" / "log.jsonl"
        log = jsonl_logger.JsonlLogger(path=nested, component="x")
        log.info("hi")
        self.assertTrue(nested.exists())


if __name__ == "__main__":
    unittest.main()
