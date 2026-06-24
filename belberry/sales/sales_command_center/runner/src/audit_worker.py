"""Воркер аудита сделок: подхватывает задания deal_audits (страница /audit) и
прогоняет audit_engine.audit_deal — собирает сделку, считает шанс возврата,
расшифровывает звонки/видео (если SCC_AUDIO=1), даёт LLM-разбор.

Запуск:  python -m src.audit_worker --once   # один проход (для крона)
         python -m src.audit_worker          # то же самое

Зависимости на проде: LLM-ключ (как у daily_runner), Bitrix-state, DATABASE_URL.
Для анализа аудио — SCC_AUDIO=1 + faster-whisper; для видео встреч — доступ
сервис-аккаунта Google к папке записей (GOOGLE_SA_JSON).

Устойчивость к транзиентным сбоям: временная ошибка (LLM 429/quota/rate-limit,
таймаут, 5xx/overloaded, обрыв связи) или смерть воркера mid-run НЕ хоронят аудит
в error — он возвращается в pending с линейным backoff (attempts*5 мин) и повторяется
до MAX_ATTEMPTS. Так разовый сбой квоты OpenAI самозалечивается без ручного перезапуска.
"""

from __future__ import annotations

import json
import sys

from . import audit_engine

# Сколько всего попыток на один аудит до окончательного error. Каждый повтор ждёт
# attempts*5 мин (см. PICK_SQL) → 6 попыток покрывают ~1.5 ч окна (5+10+15+20+25 мин).
MAX_ATTEMPTS = 6

# Маркеры транзиентных (повторяемых) сбоев в тексте/коде исключения. insufficient_quota
# включён намеренно: на практике это бывает временное исчерпание лимита аккаунта,
# которое отпускает за минуты-часы (инцидент 24.06 с ключом OpenAI).
_RETRYABLE_MARKERS = (
    "429", "rate limit", "rate_limit", "ratelimit", "insufficient_quota", "quota",
    "overloaded", "529", "503", "502", "500", "504", "timeout", "timed out",
    "connection", "econnreset", "temporarily", "try again",
)
_RETRYABLE_CODES = {429, 500, 502, 503, 504, 529}


def _is_retryable(exc: Exception) -> bool:
    """True для временных сбоев, которые имеет смысл повторить (квота/лимит/сеть/5xx)."""
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    try:
        if int(code) in _RETRYABLE_CODES:
            return True
    except (TypeError, ValueError):
        pass
    msg = str(exc).lower()
    return any(m in msg for m in _RETRYABLE_MARKERS)


# Застрявшие в collecting (воркер упал/убит mid-run) — транзиентный сбой: возвращаем
# в pending для повтора, пока есть попытки; исчерпали — error. 20 мин заведомо больше
# бюджета одного аудита (≤6 звонков + LLM).
REAP_REQUEUE_SQL = """
UPDATE deal_audits SET status='pending', attempts=attempts+1,
  error='Аудит прервался (таймаут/сбой воркера) — повтор автоматически.', updated_at=now()
WHERE status='collecting' AND updated_at < now() - interval '20 minutes' AND attempts + 1 < %s
"""
REAP_FAIL_SQL = """
UPDATE deal_audits SET status='error', attempts=attempts+1,
  error='Аудит прерывался несколько раз (таймаут/сбой воркера). Запусти заново.', updated_at=now()
WHERE status='collecting' AND updated_at < now() - interval '20 minutes' AND attempts + 1 >= %s
"""

# Берём самый старый pending, чей backoff истёк: свежий (attempts=0) — сразу,
# повторный — не раньше attempts*5 мин после прошлой неудачи (защита от долбёжки API).
PICK_SQL = """
UPDATE deal_audits SET status = 'collecting', updated_at = now()
WHERE id = (
  SELECT id FROM deal_audits
  WHERE status = 'pending'
    AND (attempts = 0 OR updated_at < now() - make_interval(mins => attempts * 5))
  ORDER BY created_at LIMIT 1
  FOR UPDATE SKIP LOCKED
)
RETURNING id, deal_id, attempts
"""

OK_SQL = (
    "UPDATE deal_audits SET status='ready', title=%s, company=%s, score=%s, band=%s, "
    "expected_value=%s, result=%s, error=NULL, updated_at=now() WHERE id=%s"
)
# Повтор: возвращаем в pending, наращиваем attempts (backoff в PICK_SQL отсчитывается от него).
RETRY_SQL = "UPDATE deal_audits SET status='pending', attempts=%s, error=%s, updated_at=now() WHERE id=%s"
ERR_SQL = "UPDATE deal_audits SET status='error', attempts=%s, error=%s, updated_at=now() WHERE id=%s"
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
    audit_id, deal_id, attempts = row
    print(f"▶ deal_audit #{audit_id}: сделка {deal_id} (попытка {attempts + 1}/{MAX_ATTEMPTS})")
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
    except Exception as e:  # noqa: BLE001 — статус error/повтор вместо падения воркера
        new_attempts = (attempts or 0) + 1
        retry = _is_retryable(e) and new_attempts < MAX_ATTEMPTS
        with conn.cursor() as cur:
            if retry:
                cur.execute(RETRY_SQL, (
                    new_attempts, f"повтор {new_attempts}/{MAX_ATTEMPTS} (временный сбой): {str(e)[:600]}", audit_id))
                print(f"  ↻ повтор {new_attempts}/{MAX_ATTEMPTS}: {e}")
            else:
                cur.execute(ERR_SQL, (new_attempts, str(e)[:800], audit_id))
                print(f"  ✗ error: {e}")
            conn.commit()
    return True


def main() -> int:
    from . import db  # ленивый импорт: psycopg нужен только на проде

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(REAP_REQUEUE_SQL, (MAX_ATTEMPTS,))
            cur.execute(REAP_FAIL_SQL, (MAX_ATTEMPTS,))
            conn.commit()
        n = 0
        while process_one(conn):
            n += 1
        print(f"обработано аудитов: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
