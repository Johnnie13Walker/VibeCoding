#!/usr/bin/env python3
"""Dry-run smoke утреннего morning_sales_dispatch по fixture-контракту."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.lev_petrovich.legacy_sales_agent.report_contract import SALES_DISPATCH_SEQUENCE
from cloudbot.business_day import MOSCOW_TZ
from cloudbot.devops.sales_dispatch_health import evaluate_morning_dispatch

WORKFLOW = ROOT / "infra" / "orchestrator" / "workflows" / "sales_morning_report.sh"
FIXTURE = ROOT / "tests" / "fixtures" / "bitrix_crm_fixtures.json"


def _load_log_records(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _rewrite_log_timestamps(path: Path, *, dispatch_date: datetime) -> None:
    records = _load_log_records(path)
    base = dispatch_date.replace(hour=9, minute=30, second=0, microsecond=0)
    for index, record in enumerate(records):
        record["ts_msk"] = (base + timedelta(seconds=index)).isoformat(timespec="seconds")
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    if not FIXTURE.exists():
        raise SystemExit(f"Не найден fixture файл для sales smoke: {FIXTURE}")

    tmp_parent = Path(os.environ.get("SALES_SMOKE_TMP_DIR") or tempfile.gettempdir())
    tmp_parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="sales-morning-dispatch-smoke-", dir=tmp_parent) as tmp_dir:
        temp_root = Path(tmp_dir)
        log_path = temp_root / "sales_agent.log"
        report_dir = temp_root / "reports"

        env = os.environ.copy()
        env.update(
            {
                "TZ": "Europe/Moscow",
                "PYTHON_BIN": sys.executable,
                "ENV_INTEGRATIONS_FILE": str(temp_root / "absent.env"),
                "SALES_RUNTIME_ENV_FILE": str(temp_root / "absent-sales.env"),
                "BITRIX_CRM_FIXTURES_FILE": str(FIXTURE),
                "SALES_TELEGRAM_DRY_RUN": "1",
                "SALES_TELEGRAM_CHAT_ID": "700700",
                "SALES_TRIGGER": "scheduled",
                "SALES_JOB_NAME": "morning_sales_dispatch",
                "SALES_WORKFLOW_NAME": "infra/orchestrator/workflows/sales_morning_report.sh",
                "SALES_LOG_FILE": str(log_path),
                "REPORT_DIR": str(report_dir),
            }
        )

        completed = subprocess.run(
            ["bash", str(WORKFLOW)],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or f"rc={completed.returncode}").strip()
            raise SystemExit(f"morning_sales_dispatch smoke завершился ошибкой: {detail}")
        if not log_path.exists():
            raise SystemExit("morning_sales_dispatch smoke не создал sales log")

        now = datetime.now(MOSCOW_TZ)
        _rewrite_log_timestamps(log_path, dispatch_date=now)

        records = _load_log_records(log_path)
        sent_reports = [
            str(record.get("report_type") or "").strip().lower()
            for record in records
            if record.get("event") == "sales_report_sent"
        ]
        if sent_reports != list(SALES_DISPATCH_SEQUENCE):
            raise SystemExit(
                "Нарушен контракт sales_report_sent в dry-run smoke: "
                f"ожидалось {list(SALES_DISPATCH_SEQUENCE)}, получено {sent_reports}"
            )

        dispatch_complete = next(
            (record for record in records if record.get("event") == "sales_dispatch_complete"),
            {},
        )
        if list(dispatch_complete.get("sent_reports") or []) != list(SALES_DISPATCH_SEQUENCE):
            raise SystemExit(
                "sales_dispatch_complete не зафиксировал полный пакет: "
                f"{dispatch_complete.get('sent_reports') or []}"
            )

        health = evaluate_morning_dispatch(
            now=now.replace(hour=9, minute=40, second=0, microsecond=0),
            log_path=log_path,
        )
        if not health.get("ok"):
            raise SystemExit(
                "sales_dispatch_health не подтвердил dry-run dispatch: "
                + json.dumps(health, ensure_ascii=False)
            )

    print("sales_morning_dispatch smoke OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
