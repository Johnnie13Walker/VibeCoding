import { describe, expect, it, vi } from 'vitest';

// Не поднимаем реальный postgres-клиент при импорте модуля.
vi.mock('@/db', () => ({ db: {} }));

import { buildFunnel } from '../dashboard';

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
