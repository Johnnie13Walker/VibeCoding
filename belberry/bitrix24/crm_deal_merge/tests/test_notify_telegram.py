from __future__ import annotations

import json
import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "notify_telegram.py"
spec = importlib.util.spec_from_file_location("notify_telegram", SCRIPT_PATH)
notify_telegram = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(notify_telegram)


def test_build_message_contains_digest_numbers() -> None:
    message = notify_telegram.build_message(
        {
            "trash_companies": 7581,
            "previous_snapshot_rows": 8576,
            "new_vs_previous": 0,
            "gone_vs_previous": 995,
            "updated_at_msk": "2026-05-24T13:16:26+03:00",
        }
    )

    assert "Пустых: 7581" in message
    assert "Новых: +0" in message
    assert "Обогащено/удалено: -995" in message
    assert "13L0gqwkNzrWacYeI5TzkOxZuRuXn5bBCtfxx-uzHH_4" in message


def test_notify_dry_run_prints_message(tmp_path, capsys) -> None:
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"trash_companies": 1}), encoding="utf-8")

    assert notify_telegram.main(["--summary", str(summary), "--dry-run"]) == 0
    assert "Пустых: 1" in capsys.readouterr().out
