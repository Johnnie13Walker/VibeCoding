"""Воркер аудита сделок: подхватывает задания deal_audits (страница /audit) и
прогоняет audit_engine.audit_deal — собирает сделку, считает шанс возврата,
расшифровывает звонки/видео (если SCC_AUDIO=1), даёт LLM-разбор.

Запуск:  python -m src.audit_worker --once   # один проход (для крона)
         python -m src.audit_worker          # то же самое

Зависимости на проде: LLM-ключ (как у daily_runner), Bitrix-state, DATABASE_URL.
Для анализа аудио — SCC_AUDIO=1 + faster-whisper; для видео встреч — доступ
сервис-аккаунта Google к папке записей (GOOGLE_SA_JSON).
"""

from __future__ import annotations

import json
import sys

from . import audit_engine

PICK_SQL = """
UPDATE deal_audits SET status = 'collecting', updated_at = now()
WHERE id = (
  SELECT id FROM deal_audits WHERE status = 'pending'
  ORDER BY created_at LIMIT 1
  FOR UPDATE SKIP LOCKED
)
RETURNING id, deal_id
"""

OK_SQL = (
    "UPDATE deal_audits SET status='ready', title=%s, company=%s, score=%s, band=%s, "
    "expected_value=%s, result=%s, error=NULL, updated_at=now() WHERE id=%s"
)
ERR_SQL = "UPDATE deal_audits SET status='error', error=%s, updated_at=now() WHERE id=%s"
NOTFOUND_SQL = (
    "UPDATE deal_audits SET status='error', error='Сделка не найдена', updated_at=now() WHERE id=%s"
)


def process_one(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute(PICK_SQL)
        row = cur.fetchone()
        conn.commit()
    if not row:
        return False
    audit_id, deal_id = row
    print(f"▶ deal_audit #{audit_id}: сделка {deal_id}")
    try:
        result = audit_engine.audit_deal(int(deal_id), with_llm=True)
        if not result:
            with conn.cursor() as cur:
                cur.execute(NOTFOUND_SQL, (audit_id,))
                conn.commit()
            print("  ✗ сделка не найдена")
            return True
        rec = result["recovery"]
        with conn.cursor() as cur:
            cur.execute(OK_SQL, (
                result.get("title"), result.get("company"),
                rec["score"], rec["band"], rec["expected_value"],
                json.dumps(result, ensure_ascii=False, default=str), audit_id,
            ))
            conn.commit()
        print(f"  ✓ ready: шанс {rec['score']}% ({rec['band']}), EV {rec['expected_value']} ₽")
    except Exception as e:  # noqa: BLE001 — статус error вместо падения воркера
        with conn.cursor() as cur:
            cur.execute(ERR_SQL, (str(e)[:800], audit_id))
            conn.commit()
        print(f"  ✗ error: {e}")
    return True


def main() -> int:
    from . import db  # ленивый импорт: psycopg нужен только на проде

    with db.connect() as conn:
        n = 0
        while process_one(conn):
            n += 1
        print(f"обработано аудитов: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
