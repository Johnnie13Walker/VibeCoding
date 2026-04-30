"""Локальный backup-снапшот конфигурации Cloudbot."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from shutil import copy2


def create_backup(root_dir: str) -> dict[str, str]:
    root = Path(root_dir).resolve()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / "reports" / f"backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for file_name in ("README.md", ".env.example", ".gitignore"):
        src = root / file_name
        if src.exists():
            copy2(src, backup_dir / file_name)
            copied += 1

    return {
        "status": "ok",
        "backup_dir": str(backup_dir),
        "files_copied": str(copied),
    }
