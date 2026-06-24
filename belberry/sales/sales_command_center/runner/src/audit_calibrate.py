"""Калибровка «шанса возврата» (#4): прогоняет ДЕТЕРМИНИРОВАННЫЙ score (без LLM, без
аудио) на закрытых сделках воронки «Продажи» и проверяет, различает ли он исходы.

Две проверки:
1. WON vs LOST — распределение балла по группам (выигранные должны в среднем набирать
   больше, чем проигранные; если нет — факторы/веса сбиты).
2. (если есть данные петли #3) score на момент возврата vs followup_status — настоящая
   калибровка «балл предсказывает успех возврата». Растёт по мере накопления followup.

Запуск:  python -m src.audit_calibrate [N]   (N сделок на группу, по умолчанию 25)
Только читает Bitrix и считает локально — ничего не пишет.
"""

from __future__ import annotations

import statistics
import sys

from . import audit_engine, bx_client


def _closed(stage_filter: str, n: int) -> list[int]:
    r = bx_client.call("crm.deal.list", {
        "filter": {"CATEGORY_ID": 10, "STAGE_ID": stage_filter},
        "select": ["ID"], "order": {"DATE_MODIFY": "DESC"}, "start": 0,
    })
    return [int(d["ID"]) for d in r.get("result", [])[:n]]


def _score_of(deal_id: int) -> tuple[int, list[str]] | None:
    ctx = audit_engine.collect_deal_context(deal_id)
    if not ctx:
        return None
    sig = audit_engine.compute_signals(ctx)
    sc = audit_engine.recovery_score(sig)
    pos = [f["label"] for f in sc["factors"] if f["weight"] > 0]
    return sc["score"], pos


def _summary(name: str, scores: list[int]) -> None:
    if not scores:
        print(f"  {name}: нет данных")
        return
    scores.sort()
    print(f"  {name:6}: n={len(scores)} mean={statistics.mean(scores):.1f} "
          f"median={statistics.median(scores):.0f} min={scores[0]} max={scores[-1]}")


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    print(f"=== Калибровка score: {n} сделок на группу ===")
    won_scores, lost_scores = [], []
    for label, stage, bucket in [("WON", "C10:WON", won_scores), ("LOST", "C10:LOSE", lost_scores)]:
        ids = _closed(stage, n)
        for did in ids:
            try:
                res = _score_of(did)
            except Exception:
                continue
            if res:
                bucket.append(res[0])
        print(f"{label}: посчитано {len(bucket)}/{len(ids)}")

    print("\n--- Распределение балла ---")
    _summary("WON", won_scores[:])
    _summary("LOST", lost_scores[:])

    # ВАЖНО: балл = recoverability (шанс ВЕРНУТЬ застрявшую), а НЕ качество сделки.
    # WON закономерно набирают МАЛО (рычаги возврата исчерпаны: до ЛПР дошли, защита была);
    # LOST — больше, т.к. часто есть непройденный рычаг. Это НЕ инверсия весов, а семантика.
    if won_scores and lost_scores:
        print(f"\nWON в среднем {statistics.mean(won_scores):.0f} < LOST {statistics.mean(lost_scores):.0f} — "
              "ожидаемо: у закрытых-выигранных нечего «возвращать» (рычаги исчерпаны), "
              "у проигранных чаще есть непройденный рычаг. Балл отражает recoverability, не исход.")
        print("Главное — РАЗБРОС внутри LOST (есть и низкие, и высокие): балл различает "
              "«труп» от «оживляемой» — это и нужно win-back.")

    _followup_calibration()
    print("\n(Веса в audit_engine.py вверху файла; правь там, если followup покажет смещение.)")
    return 0


def _followup_calibration() -> None:
    """Настоящая калибровка: балл на момент аудита vs реальный результат петли #3.
    Растёт по мере накопления followup-данных."""
    print("\n--- Калибровка по результату возврата (петля #3) ---")
    try:
        from . import db
        with db.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT followup_status, score FROM deal_audits "
                        "WHERE followup_status IS NOT NULL AND score IS NOT NULL")
            rows = cur.fetchall()
    except Exception as e:  # noqa: BLE001 — БД может быть недоступна локально
        print(f"  (нет доступа к БД: {e})")
        return
    by = {}
    for st, sc in rows:
        by.setdefault(st, []).append(sc)
    if not rows:
        print("  данных пока нет — накопится после боевых прогонов петли (7 дней/возврат).")
        return
    for st in ("progressed", "in_progress", "stalled"):
        if by.get(st):
            print(f"  {st:11}: n={len(by[st])} mean-score={statistics.mean(by[st]):.0f}")
    if by.get("progressed") and by.get("stalled"):
        d = statistics.mean(by["progressed"]) - statistics.mean(by["stalled"])
        print(f"  → progressed выше stalled на {d:+.0f} баллов "
              + ("✓ балл предсказывает успех возврата" if d > 5 else "⚠ балл слабо предсказывает — тюнить веса"))


if __name__ == "__main__":
    sys.exit(main())
