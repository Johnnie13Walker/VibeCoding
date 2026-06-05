import { describe, expect, it, vi } from 'vitest';

// Не поднимаем реальный postgres-клиент при импорте модуля.
vi.mock('@/db', () => ({ db: {} }));

import { buildFunnel, buildSalesFunnel } from '../dashboard';

describe('buildFunnel', () => {
  it('группирует открытые сделки по стадиям, считает количество и суммы', () => {
    const result = buildFunnel([
      { stage: 'C10:NEW', opportunity: 100, stuckDays: null },
      { stage: 'C10:NEW', opportunity: 200, stuckDays: 3 },
      { stage: 'C10:EXECUTING', opportunity: 50, stuckDays: null },
    ]);

    const newStage = result.find((s) => s.stage === 'C10:NEW');
    expect(newStage).toMatchObject({ label: 'Квалификация', count: 2, amount: 300 });

    const exec = result.find((s) => s.stage === 'C10:EXECUTING');
    expect(exec).toMatchObject({ label: 'Подготовка КП', count: 1, amount: 50 });
  });

  it('исключает незнакомые/закрытые стадии', () => {
    const result = buildFunnel([
      { stage: 'C10:NEW', opportunity: 100, stuckDays: null },
      { stage: 'C10:WON', opportunity: 999, stuckDays: null },
      { stage: 'C50:NEW', opportunity: 10, stuckDays: null },
    ]);

    expect(result).toHaveLength(1);
    expect(result[0].stage).toBe('C10:NEW');
  });

  it('сортирует стадии по порядку воронки', () => {
    const result = buildFunnel([
      { stage: 'C10:UC_KC7195', opportunity: 1, stuckDays: null },
      { stage: 'C10:NEW', opportunity: 1, stuckDays: null },
      { stage: 'C10:EXECUTING', opportunity: 1, stuckDays: null },
    ]);

    expect(result.map((s) => s.label)).toEqual([
      'Квалификация',
      'Подготовка КП',
      'Подготовка договора',
    ]);
  });
});

describe('buildSalesFunnel', () => {
  it('считает шаги, конверсии между ними и средний чек', () => {
    const f = buildSalesFunnel({
      dealsTotal: 40,
      dealsCold: 30,
      dealsIncoming: 10,
      firstMeetings: 20,
      presentations: 16,
      kpSent: 12,
      wonCount: 3,
      wonAmount: 600000,
    });

    expect(f.steps.map((s) => [s.key, s.count])).toEqual([
      ['deals', 40],
      ['first', 20],
      ['kp', 12],
      ['present', 16],
      ['won', 3],
    ]);
    // Первый шаг — без конверсии.
    expect(f.steps[0].convFromPrev).toBeNull();
    // first/deals=20/40, kp/first=12/20, present/kp=16/12, won/present=3/16.
    expect(f.steps[1].convFromPrev).toBe(50);
    expect(f.steps[2].convFromPrev).toBe(60);
    expect(f.steps[3].convFromPrev).toBe(133);
    expect(f.steps[4].convFromPrev).toBe(19);
    expect(f.steps[4].amount).toBe(600000);
    expect(f.avgCheck).toBe(200000);
    expect(f.dealsCold).toBe(30);
    expect(f.dealsIncoming).toBe(10);
  });

  it('конверсии не ограничены 100% (встречи опережают сделки)', () => {
    const f = buildSalesFunnel({
      dealsTotal: 9,
      dealsCold: 5,
      dealsIncoming: 4,
      firstMeetings: 14, // 14/9 = 156%
      presentations: 10,
      kpSent: 0,
      wonCount: 0,
      wonAmount: 0,
    });
    expect(f.steps[1].convFromPrev).toBe(156);
  });

  it('пустые данные не делят на ноль', () => {
    const f = buildSalesFunnel({
      dealsTotal: 0, dealsCold: 0, dealsIncoming: 0, firstMeetings: 0,
      presentations: 0, kpSent: 0, wonCount: 0, wonAmount: 0,
    });
    expect(f.steps.every((s) => s.count === 0)).toBe(true);
    expect(f.steps[1].convFromPrev).toBeNull();
    expect(f.avgCheck).toBe(0);
  });
});
