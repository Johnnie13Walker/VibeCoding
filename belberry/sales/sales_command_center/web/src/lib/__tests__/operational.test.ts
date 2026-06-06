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
    // short=80→min(20,90)=20; call=100; chat=50; email=50; meet=120 = 340
    expect(operationalMinutes({ dials: 100, calls60: 20, messenger: 5, meetings: 2, emails: 10 })).toBe(340);
  });

  it('режет «механический» обзвон потолком 90 минут', () => {
    // short=1000→min(250,90)=90
    expect(operationalMinutes({ dials: 1000, calls60: 0 })).toBe(90);
  });

  it('балл — нормировка к 300 мин, потолок 10, округление 0.1', () => {
    expect(operationalScore({ dials: 100, calls60: 20, messenger: 5, meetings: 2, emails: 10 })).toBe(10); // 340→cap
    expect(operationalScore({ dials: 50, calls60: 5 })).toBe(1.2); // 36.25/300*10=1.208→1.2
    expect(operationalScore({ dials: 0, calls60: 0, messenger: 3, meetings: 1, emails: 2 })).toBe(3.3); // 100→3.3
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
      { date: '2026-05-26', meetings: 3, emails: 4 }, // 180+20=200 → 6.7
      { date: '2026-05-27', meetings: 5 }, // 300 → 10
    ]);
    const tm = member(2, 'Петров', true, [
      { date: '2026-05-26', dials: 120, calls60: 30 }, // short90→min(22.5,90)=22.5; 150 =172.5→5.75→5.8 (round)
      // 27-го нет данных → null
    ]);
    const m = buildOperationalMatrix(days, [tm, op]);

    expect(m.rows.map((r) => r.name)).toEqual(['Иванов', 'Петров']); // ОП раньше ТМ
    expect(m.countOp).toBe(1);
    expect(m.countTm).toBe(1);

    const ivanov = m.rows[0];
    expect(ivanov.scores).toEqual([6.7, 10]);
    expect(ivanov.avg).toBe(8.4); // (6.7+10)/2=8.35→8.4

    const petrov = m.rows[1];
    expect(petrov.scores[1]).toBeNull(); // нет данных за 2-й день
    expect(petrov.avg).toBe(petrov.scores[0]); // единственный день

    expect(m.deptAvgByDay[1]).toBe(10); // только Иванов во 2-й день
    expect(m.best?.name).toBe('Иванов');
  });

  it('пустой состав → нулевые агрегаты без падения', () => {
    const m = buildOperationalMatrix(days, []);
    expect(m.avgScore).toBeNull();
    expect(m.loadPct).toBeNull();
    expect(m.best).toBeNull();
    expect(m.deptAvgByDay).toEqual([null, null]);
  });

  it('скрывает только непроработавших; уволенных показывает (история общая)', () => {
    const worker = member(1, 'Рабочий', false, [{ date: '2026-05-26', meetings: 3, emails: 4 }]); // 6.7
    const idle = member(2, 'Простой', false, [{ date: '2026-05-26', emails: 1 }]); // 5 мин → 0.2 < порога
    const fired = member(3, 'Уволенный', false, [{ date: '2026-05-26', meetings: 5 }], false); // 10, isActive=false — но работал
    const m = buildOperationalMatrix(days, [worker, idle, fired]);

    expect(m.rows.map((r) => r.name)).toEqual(['Уволенный', 'Рабочий']); // по avg ↓; простой скрыт порогом
    expect(m.countOp).toBe(2);
  });
});
