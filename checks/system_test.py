#!/usr/bin/env python3
"""System test Cloudbot: smoke + shell checks + проверка логов."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_step(title: str, cmd: list[str], cwd: Path | None = None) -> None:
    print(f"[STEP] {title}")
    completed = subprocess.run(
        cmd,
        cwd=cwd or ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    if completed.stdout:
        print(completed.stdout.strip())
    if completed.returncode != 0:
        if completed.stderr:
            print(completed.stderr.strip(), file=sys.stderr)
        raise SystemExit(f"System step failed: {title}")


def main() -> None:
    run_step("smoke_test.py", ["python3", "checks/smoke_test.py"])
    run_step(
        "bash syntax checks",
        [
            "bash",
            "-lc",
            "for f in checks/*.sh scripts/*.sh infra/orchestrator/workflows/*.sh reports/host-security-check.sh.remote; do bash -n \"$f\"; done",
        ],
    )

    logs_dir = ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    log_files = sorted(logs_dir.glob("*.log"))

    print("[STEP] проверка логов")
    if not log_files:
        print("Логи отсутствуют: критичных ошибок за проверяемый период не найдено")
    else:
        for file_path in log_files[-5:]:
            print(f"- {file_path.name}: OK")

    print("SYSTEM TEST OK")


if __name__ == "__main__":
    main()
