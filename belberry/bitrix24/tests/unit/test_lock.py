from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from belberry.bitrix24.orchestration.lock import (
    LockBusy,
    LockHolder,
    _is_stale,
    acquire_lock,
    inspect_lock,
    process_lock,
    release_lock,
)


class ProcessLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lock_path = Path(self.tmp.name) / "state" / "process.lock"
        self.now = datetime(2026, 5, 10, 9, 30, 0, tzinfo=timezone.utc)

    def test_acquire_creates_atomic_lock_with_private_permissions(self) -> None:
        holder = acquire_lock(self.lock_path, ttl_sec=1800, now_msk=self.now)

        self.assertTrue(self.lock_path.exists())
        self.assertEqual(oct(self.lock_path.stat().st_mode & 0o777), "0o600")
        payload = json.loads(self.lock_path.read_text(encoding="utf-8"))
        self.assertEqual(payload, holder.to_json())
        self.assertEqual(holder.started_at_msk, "2026-05-10T12:30:00+03:00")
        self.assertEqual(holder.ttl_sec, 1800)
        self.assertEqual(holder.pid, os.getpid())

    def test_inspect_lock_returns_holder(self) -> None:
        holder = acquire_lock(self.lock_path, ttl_sec=60, now_msk=self.now)

        self.assertEqual(inspect_lock(self.lock_path), holder)

    def test_inspect_lock_returns_none_for_missing_invalid_or_incomplete_file(self) -> None:
        self.assertIsNone(inspect_lock(self.lock_path))

        self.lock_path.parent.mkdir(parents=True)
        self.lock_path.write_text("{broken", encoding="utf-8")
        self.assertIsNone(inspect_lock(self.lock_path))

        self.lock_path.write_text("[]", encoding="utf-8")
        self.assertIsNone(inspect_lock(self.lock_path))

        self.lock_path.write_text(json.dumps({"pid": 1}), encoding="utf-8")
        self.assertIsNone(inspect_lock(self.lock_path))

    def test_concurrent_acquire_raises_lock_busy(self) -> None:
        first = acquire_lock(self.lock_path, ttl_sec=1800, now_msk=self.now)

        with self.assertRaisesRegex(LockBusy, str(first.pid)):
            acquire_lock(self.lock_path, ttl_sec=1800, now_msk=self.now)

        self.assertEqual(inspect_lock(self.lock_path), first)

    def test_stale_takeover_after_ttl_expiry(self) -> None:
        first = acquire_lock(self.lock_path, ttl_sec=10, now_msk=self.now)
        later = datetime(2026, 5, 10, 9, 30, 11, tzinfo=timezone.utc)

        second = acquire_lock(self.lock_path, ttl_sec=20, now_msk=later)

        self.assertNotEqual(second.started_at_msk, first.started_at_msk)
        self.assertEqual(inspect_lock(self.lock_path), second)
        self.assertEqual(second.ttl_sec, 20)

    def test_lock_is_busy_until_ttl_strictly_expires(self) -> None:
        acquire_lock(self.lock_path, ttl_sec=10, now_msk=self.now)
        before_expiry = datetime(2026, 5, 10, 9, 30, 9, tzinfo=timezone.utc)

        with self.assertRaises(LockBusy):
            acquire_lock(self.lock_path, ttl_sec=20, now_msk=before_expiry)

    def test_unreadable_lock_file_is_taken_over_as_stale(self) -> None:
        self.lock_path.parent.mkdir(parents=True)
        self.lock_path.write_text("{broken", encoding="utf-8")

        holder = acquire_lock(self.lock_path, ttl_sec=60, now_msk=self.now)

        self.assertEqual(inspect_lock(self.lock_path), holder)

    def test_racing_stale_takeover_raises_busy_when_new_file_appears(self) -> None:
        acquire_lock(self.lock_path, ttl_sec=1, now_msk=self.now)
        later = datetime(2026, 5, 10, 9, 30, 2, tzinfo=timezone.utc)
        original_unlink = Path.unlink

        def recreate_after_unlink(path: Path, *args, **kwargs):
            original_unlink(path, *args, **kwargs)
            if path == self.lock_path:
                path.write_text(
                    json.dumps(
                        {
                            "pid": 999,
                            "hostname": "other",
                            "started_at_msk": "2026-05-10T12:30:02+03:00",
                            "ttl_sec": 60,
                        }
                    ),
                    encoding="utf-8",
                )

        with patch.object(Path, "unlink", recreate_after_unlink):
            with self.assertRaises(LockBusy):
                acquire_lock(self.lock_path, ttl_sec=60, now_msk=later)

    def test_stale_takeover_handles_file_deleted_before_unlink(self) -> None:
        acquire_lock(self.lock_path, ttl_sec=1, now_msk=self.now)
        later = datetime(2026, 5, 10, 9, 30, 2, tzinfo=timezone.utc)
        original_unlink = Path.unlink
        deleted_once = {"done": False}

        def delete_before_unlink(path: Path, *args, **kwargs):
            if path == self.lock_path and not deleted_once["done"]:
                deleted_once["done"] = True
                original_unlink(path, *args, **kwargs)
                raise FileNotFoundError
            return original_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", delete_before_unlink):
            holder = acquire_lock(self.lock_path, ttl_sec=60, now_msk=later)

        self.assertEqual(inspect_lock(self.lock_path), holder)

    def test_release_lock_removes_only_matching_holder(self) -> None:
        holder = acquire_lock(self.lock_path, ttl_sec=60, now_msk=self.now)

        release_lock(self.lock_path, holder)

        self.assertIsNone(inspect_lock(self.lock_path))

    def test_release_lock_does_not_remove_foreign_holder(self) -> None:
        holder = acquire_lock(self.lock_path, ttl_sec=60, now_msk=self.now)
        foreign = LockHolder(
            pid=holder.pid,
            hostname=holder.hostname,
            started_at_msk="2026-05-10T12:31:00+03:00",
            ttl_sec=holder.ttl_sec,
        )

        release_lock(self.lock_path, foreign)

        self.assertEqual(inspect_lock(self.lock_path), holder)

    def test_release_missing_or_invalid_lock_is_noop(self) -> None:
        holder = LockHolder(pid=1, hostname="h", started_at_msk="2026-05-10T12:30:00+03:00", ttl_sec=60)

        release_lock(self.lock_path, holder)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.write_text("{broken", encoding="utf-8")
        release_lock(self.lock_path, holder)

        self.assertTrue(self.lock_path.exists())

    def test_release_handles_file_deleted_between_inspect_and_unlink(self) -> None:
        holder = acquire_lock(self.lock_path, ttl_sec=60, now_msk=self.now)
        original_unlink = Path.unlink

        def delete_before_unlink(path: Path, *args, **kwargs):
            original_unlink(path, *args, **kwargs)
            raise FileNotFoundError

        with patch.object(Path, "unlink", delete_before_unlink):
            release_lock(self.lock_path, holder)

        self.assertFalse(self.lock_path.exists())

    def test_process_lock_context_releases_on_success_and_exception(self) -> None:
        with process_lock(self.lock_path, ttl_sec=60, now_msk=self.now) as holder:
            self.assertEqual(inspect_lock(self.lock_path), holder)
        self.assertIsNone(inspect_lock(self.lock_path))

        with self.assertRaisesRegex(RuntimeError, "boom"):
            with process_lock(self.lock_path, ttl_sec=60, now_msk=self.now):
                raise RuntimeError("boom")
        self.assertIsNone(inspect_lock(self.lock_path))

    def test_ttl_must_be_positive(self) -> None:
        with self.assertRaisesRegex(ValueError, "ttl_sec"):
            acquire_lock(self.lock_path, ttl_sec=0, now_msk=self.now)

    def test_empty_started_at_is_invalid_for_stale_check(self) -> None:
        holder = LockHolder(pid=1, hostname="h", started_at_msk="", ttl_sec=60)

        with self.assertRaisesRegex(ValueError, "started_at_msk"):
            _is_stale(holder, now_msk=self.now)

    def test_stale_lock_with_invalid_timestamp_is_taken_over(self) -> None:
        self.lock_path.parent.mkdir(parents=True)
        self.lock_path.write_text(
            json.dumps(
                {
                    "pid": 1,
                    "hostname": "host",
                    "started_at_msk": "invalid",
                    "ttl_sec": 60,
                }
            ),
            encoding="utf-8",
        )

        holder = acquire_lock(self.lock_path, ttl_sec=60, now_msk=self.now)

        self.assertEqual(inspect_lock(self.lock_path), holder)

    def test_failed_exclusive_write_cleans_partial_lock_file(self) -> None:
        with patch("belberry.bitrix24.orchestration.lock.os.fsync", side_effect=OSError("disk")):
            with self.assertRaisesRegex(OSError, "disk"):
                acquire_lock(self.lock_path, ttl_sec=60, now_msk=self.now)

        self.assertFalse(self.lock_path.exists())


if __name__ == "__main__":
    unittest.main()
