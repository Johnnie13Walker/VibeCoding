#!/usr/bin/env python3
"""Профилирование выгрузки 1С по заявкам (ВМ-Логистик).

Вход: data/perevozki_raw.xls (BIFF8, лист 'Лист_1', 65 колонок).
Данные в git НЕ коммитятся (см. .gitignore) — содержат клиентов, маржу, контакты.

Запуск:  .venv/bin/python scripts/profile_perevozki.py
Срезы: финансы по каналам, продуктивность логистов, повторяемость СПОТ-маршрутов,
       маржа Гарантии по клиентам, дисбаланс регионов (обратная загрузка).
"""
import xlrd, datetime
from collections import Counter, defaultdict

PATH = "data/perevozki_raw.xls"


def load():
    sh = xlrd.open_workbook(PATH).sheet_by_index(0)
    hdr = [str(sh.cell_value(0, c)).strip() for c in range(sh.ncols)]
    H = {h: i for i, h in enumerate(hdr)}  # дубли имён — last-wins
    N = sh.nrows - 1
    def V(name):
        c = H[name]
        return [sh.cell_value(r, c) for r in range(1, sh.nrows)]
    return V, N


def pdate(x):
    try:
        return datetime.datetime.strptime(str(x).strip(), "%d.%m.%Y").date()
    except Exception:
        return None


def fnum(x):
    s = str(x).strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def rub(x):
    return f"{x:,.0f}".replace(",", " ")


def main():
    V, N = load()
    st = V("Статус заявки"); ch = V("Канал продаж"); rt = V("Маршрут")
    cl = V("Клиент"); au = V("Автор"); tk = V("Тариф клиента")
    pr = V("Прибыль по клиенту руб"); rz = V("Регион загрузка"); rv = V("Регион выгрузка")
    conf = lambda i: str(st[i]).strip() == "Подтверждена"

    # Финансы по каналам
    agg = defaultdict(lambda: [0, 0.0, 0.0])
    for i in range(N):
        if not conf(i):
            continue
        k = str(ch[i]).strip() or "(пусто)"
        agg[k][0] += 1; agg[k][1] += fnum(tk[i]) or 0; agg[k][2] += fnum(pr[i]) or 0
    print("== Каналы (подтв.) ==")
    for k, v in sorted(agg.items(), key=lambda kv: -kv[1][1]):
        m = 100 * v[2] / v[1] if v[1] else 0
        print(f"  {k:12s} {v[0]:5d} | выр {rub(v[1]):>14s} | приб {rub(v[2]):>13s} | {m:5.1f}%")

    # Повторяемость СПОТ-маршрутов (кандидаты на авто-торги, контур B)
    spot = defaultdict(lambda: [0, 0.0])
    for i in range(N):
        if conf(i) and str(ch[i]).strip() == "СПОТ" and str(rt[i]).strip():
            spot[str(rt[i]).strip()][0] += 1; spot[str(rt[i]).strip()][1] += fnum(pr[i]) or 0
    rec = {r: v for r, v in spot.items() if v[0] >= 10}
    print(f"\n== СПОТ-маршрутов с ≥10 повторов: {len(rec)} из {len(spot)} ==")

    # Маржа Гарантии по клиентам (где утекает)
    g = defaultdict(lambda: [0, 0.0, 0.0])
    for i in range(N):
        if conf(i) and str(ch[i]).strip() == "Гарантия":
            g[str(cl[i]).strip()][0] += 1; g[str(cl[i]).strip()][1] += fnum(tk[i]) or 0; g[str(cl[i]).strip()][2] += fnum(pr[i]) or 0
    print("\n== Гарантия — топ-клиенты по марже ==")
    for c, v in sorted(g.items(), key=lambda kv: -kv[1][1])[:10]:
        m = 100 * v[2] / v[1] if v[1] else 0
        print(f"  {c[:30]:30s} {v[0]:4d} | {rub(v[1]):>12s} | {m:5.1f}%")

    # Дисбаланс регионов (обратная загрузка, идея Артёма)
    load_c, unload_c = Counter(), Counter()
    for i in range(N):
        if not conf(i):
            continue
        if str(rz[i]).strip():
            load_c[str(rz[i]).strip()] += 1
        if str(rv[i]).strip():
            unload_c[str(rv[i]).strip()] += 1
    print("\n== Дефицит обратного груза (выгрузка-загрузка, топ-8) ==")
    bal = [(r, load_c[r], unload_c[r], unload_c[r] - load_c[r]) for r in set(load_c) | set(unload_c)]
    for r, l, u, d in sorted(bal, key=lambda x: -x[3])[:8]:
        print(f"  {r[:24]:24s} загр {l:5d} выгр {u:5d}  дисбаланс {d:+5d}")


if __name__ == "__main__":
    main()
