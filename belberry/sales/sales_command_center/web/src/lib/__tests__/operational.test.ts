import { describe, expect, it } from 'vitest';
import {
  operationalMinutes,
  operationalScore,
  buildOperationalMatrix,
  type OperMemberInput,
  type OperDayInput,
} from '../operational';

describe('operationalMinutes / operationalScore (зеркало oper.py)', () => {
  it('суммирует живые минуты по весам действий', () => {
    // short=80→min(160,150)=150; call=100; chat=50; email=100; meet=120 = 520
    expect(operationalMinutes({ dials: 100, calls60: 20, messenger: 5, meetings: 2, emails: 10 })).toBe(520);
  });

  it('режет «механический» обзвон потолком 150 минут', () => {
    // short=1000→min(2000,150)=150
    expect(operationalMinutes({ dials: 1000, calls60: 0 })).toBe(150);
  });

  it('балл — нормировка к 300 мин, потолок 10, округление 0.1', () => {
    expect(operationalScore({ dials: 100, calls60: 20, messenger: 5, meetings: 2, emails: 10 })).toBe(10); // 520→cap
    expect(operationalScore({ dials: 50, calls60: 5 })).toBe(3.8); // short45×2=90(cap)+25=115 → 3.83→3.8
    expect(operationalScore({ dials: 0, calls60: 0, messenger: 3, meetings: 1, emails: 2 })).toBe(3.7); // 30+60+20=110→3.7
    expect(operationalScore({ dials: 0, calls60: 0 })).toBe(0);
  });
});

function member(
  id: number,
  name: string,
  isTm: boolean,
  days: Partial<OperDayInput>[],
  isActive = true,
): OperMemberInput {
  const byDate = new Map<string, OperDayInput>();
  for (const d of days) {
    byDate.set(d.date as string, {
      date: d.date as string,
      dials: d.dials ?? 0,
      calls60: d.calls60 ?? 0,
      messenger: d.messenger ?? 0,
      emails: d.emails ?? 0,
      meetings: d.meetings ?? 0,
    });
  }
  return { managerId: id, name, role: isTm ? 'Телемаркетинг' : 'Менеджер', isTm, isActive, byDate };
}

describe('buildOperationalMatrix', () => {
  const days = ['2026-05-26', '2026-05-27'];

  it('строит матрицу, секции ОП/ТМ, средние по строке/дню/отделу', () => {
    const op = member(1, 'Иванов', false, [
      { date: '2026-05-26', meetings: 3, emails: 4 }, // 180+40=220 → 7.3
      { date: '2026-05-27', meetings: 5 }, // 300 → 10
    ]);
    const tm = member(2, 'Петров', true, [
      { date: '2026-05-26', dials: 120, calls60: 30 }, // short90→min(180,150)=150; +150 =300 → 10.0
      // 27-го нет данных → null
    ]);
    const m = buildOperationalMatrix(days, [tm, op]);

    expect(m.rows.map((r) => r.name)).toEqual(['Иванов', 'Петров']); // ОП раньше ТМ
    expect(m.countOp).toBe(1);
    expect(m.countTm).toBe(1);

    const ivanov = m.rows[0];
    expect(ivanov.scores).toEqual([7.3, 10]);
    expect(ivanov.avg).toBe(8.7); // (7.3+10)/2=8.65→8.7

    const petrov = m.rows[1];
    expect(petrov.scores[1]).toBeNull(); // нет данных за 2-й день
    expect(petrov.avg).toBe(petrov.scores[0]); // единственный день

    expect(m.deptAvgByDay[1]).toBe(10); // только Иванов во 2-й день
    expect(m.best?.name).toBe('Петров'); // Петров avg 10.0 > Иванов 8.7 (лучший по среднему)
  });

  it('пустой состав → нулевые агрегаты без падения', () => {
    const m = buildOperationalMatrix(days, []);
    expect(m.avgScore).toBeNull();
    expect(m.loadPct).toBeNull();
    expect(m.best).toBeNull();
    expect(m.deptAvgByDay).toEqual([null, null]);
  });

  it('действующих показывает (вкл. новичка с малой активностью), уволенных-непроработавших скрывает', () => {
    const worker = member(1, 'Рабочий', false, [{ date: '2026-05-26', meetings: 3, emails: 4 }]); // 6.7, active
    const newbie = member(2, 'Новичок', false, [{ date: '2026-05-26', dials: 13 }]); // ~0.1, active → показываем
    const firedWorked = member(3, 'Уволенный-работал', false, [{ date: '2026-05-26', meetings: 5 }], false); // 10, но работал
    const firedIdle = member(4, 'Уволенный-простой', false, [{ date: '2026-05-26', emails: 1 }], false); // 0.2, уволен+простой → скрыт
    const names = buildOperationalMatrix(days, [worker, newbie, firedWorked, firedIdle]).rows.map((r) => r.name);

    expect(names).toContain('Новичок'); // действующий новичок виден даже с малой активностью
    expect(names).toContain('Уволенный-работал');
    expect(names).not.toContain('Уволенный-простой'); // уволенный без заметной работы скрыт
  });

  it('отпуск помечается leave и НЕ учитывается в среднем балле', () => {
    const m = buildOperationalMatrix(['2026-05-26', '2026-05-27'], [
      {
        managerId: 1, name: 'Отпускник', role: 'Менеджер по продажам', isTm: false, isActive: true,
        byDate: new Map([['2026-05-26', { date: '2026-05-26', dials: 0, calls60: 0, messenger: 0, emails: 0, meetings: 3 }]]),
        leaveDays: new Set(['2026-05-27']),
      },
    ]);
    const row = m.rows[0];
    expect(row.leave[1]).toBe(true); // 2-й день — отпуск
    expect(row.scores[1]).toBeNull(); // вне балла
    expect(row.avg).toBe(row.scores[0]); // среднее только по рабочему дню (3 встречи → 6.0)
    expect(m.deptAvgByDay[1]).toBeNull(); // в дне отпуска отдел тоже без балла
  });
});
