"""Воркер КП-движка: подхватывает задания kp_jobs (страница /kp) и собирает фактуру.

Гонит стадии СБОРА ДАННЫХ через CLI движка belberry/sales/kp (kp_pipeline.py):
bitrix → audit (PR-CY) → metrika → assemble. Сборку деки/сметы НЕ делает —
это локальный шаг движка (build.sh требует Chrome). Результат — kp_data jsonb
(факты строго с источниками + чек-лист ручных шагов) и статус ready/error.

Запуск:  python -m src.kp_worker --once     # один проход (для крона)
         python -m src.kp_worker            # то же самое (алиас)

Зависимости на проде: ключ PR-CY (~/.config/vibecoding/assistant/secrets/prcy.env
или PRCY_API_KEY), токен Метрики (опционально — без него стадия пропускается),
Bitrix-state (bx_client). Путь до движка: env KP_ENGINE_DIR либо ../kp от
sales_command_center.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# sales_command_center/runner/src → … /belberry/sales/kp
_DEFAULT_KP_DIR = Path(__file__).resolve().parents[2].parent / "kp"
KP_ENGINE_DIR = Path(os.environ.get("KP_ENGINE_DIR", _DEFAULT_KP_DIR))

PICK_SQL = """
UPDATE kp_jobs SET status = 'collecting', updated_at = now()
WHERE id = (
  SELECT id FROM kp_jobs WHERE status = 'pending'
  ORDER BY created_at LIMIT 1
  FOR UPDATE SKIP LOCKED
)
RETURNING id, deal_id, brand, service
"""


def finish_sql(ok: bool) -> str:
    if ok:
        return ("UPDATE kp_jobs SET status = 'ready', stage = %s, kp_data = %s, "
                "error = NULL, updated_at = now() WHERE id = %s")
    return ("UPDATE kp_jobs SET status = 'error', stage = %s, error = %s, "
            "updated_at = now() WHERE id = %s")


def run_collect(deal_id: int, brand: str, service: str, workdir: Path) -> dict:
    """Стадии сбора через CLI движка; возвращает kp_data. Бросает RuntimeError."""
    if not (KP_ENGINE_DIR / "kp_pipeline.py").exists():
        raise RuntimeError(f"движок КП не найден: {KP_ENGINE_DIR} (задай KP_ENGINE_DIR)")
    cmd = [sys.executable, str(KP_ENGINE_DIR / "kp_pipeline.py"), str(deal_id),
           "--client", workdir.name, "--brand", brand,
           "--service", service or "seo", "--skip-prodoctorov"]
    # папку клиента пайплайн делает в KP_ENGINE_DIR/clients/<имя> — направим во временную
    r = subprocess.run(cmd, cwd=KP_ENGINE_DIR, capture_output=True, text=True, timeout=1500)  # polish-стадия (LLM по слайдам) добавляет до ~5 мин
    if r.returncode != 0:
        tail = (r.stdout + "\n" + r.stderr).strip().splitlines()[-6:]
        raise RuntimeError("pipeline: " + " | ".join(tail))
    data_path = KP_ENGINE_DIR / "clients" / workdir.name / "kp_data.json"
    if not data_path.exists():
        raise RuntimeError("pipeline отработал, но kp_data.json не появился")
    return json.loads(data_path.read_text(encoding="utf-8"))


def process_one(conn) -> bool:
    """Берёт одно pending-задание; True если было что обрабатывать."""
    with conn.cursor() as cur:
        cur.execute(PICK_SQL)
        row = cur.fetchone()
        conn.commit()
    if not row:
        return False
    job_id, deal_id, brand, service = row
    print(f"▶ kp_job #{job_id}: сделка {deal_id}, бренд {brand}, услуга {service}")
    workname = f"_job_{job_id}_{deal_id}"
    try:
        data = run_collect(deal_id, brand, service, Path(workname))
        with conn.cursor() as cur:
            cur.execute(finish_sql(True), ("assemble", json.dumps(data, ensure_ascii=False), job_id))
            conn.commit()
        print(f"  ✓ ready: фактов {len(data.get('facts', []))}")
    except Exception as e:  # noqa: BLE001 — статус error вместо падения воркера
        with conn.cursor() as cur:
            cur.execute(finish_sql(False), ("collect", str(e)[:800], job_id))
            conn.commit()
        print(f"  ✗ error: {e}")
    return True


def main() -> int:
    from . import db  # ленивый импорт: psycopg нужен только на проде

    with db.connect() as conn:
        n = 0
        while process_one(conn):
            n += 1
        print(f"обработано заданий: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
