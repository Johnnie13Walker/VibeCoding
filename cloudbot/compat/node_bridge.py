"""Утилиты безопасного вызова существующих JS-модулей через Node.js."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def call_js_export(
    module_rel_path: str,
    export_name: str,
    method_name: str | None = None,
    args: list[Any] | None = None,
) -> Any:
    """Вызывает export из JS-модуля и возвращает JSON-результат."""
    module_abs_path = (REPO_ROOT / module_rel_path).resolve()
    payload = {
        "moduleUrl": module_abs_path.as_uri(),
        "exportName": export_name,
        "methodName": method_name,
        "args": args or [],
    }

    js_runner = """
const payload = JSON.parse(process.argv[1] || '{}');
const loaded = await import(payload.moduleUrl);
const target = loaded[payload.exportName];
if (target === undefined) {
  throw new Error(`Export not found: ${payload.exportName}`);
}

let callable = target;
if (payload.methodName) {
  callable = target?.[payload.methodName];
}
if (typeof callable !== 'function') {
  throw new Error(`Callable not found: ${payload.exportName}.${payload.methodName || ''}`);
}

const result = await callable(...(payload.args || []));
process.stdout.write(JSON.stringify(result ?? null));
""".strip()

    completed = subprocess.run(
        ["node", "--input-type=module", "-e", js_runner, json.dumps(payload, ensure_ascii=False)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise RuntimeError(stderr or "Не удалось выполнить JS-адаптер")

    stdout = (completed.stdout or "").strip()
    if not stdout:
        return None

    return json.loads(stdout)
