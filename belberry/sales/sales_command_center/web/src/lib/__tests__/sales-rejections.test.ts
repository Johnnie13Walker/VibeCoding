import { describe, expect, it } from 'vitest';
import {
  aggregateSelected,
  managersFromPerManager,
  type SalesRejectionPerManager,
} from '@/lib/sales-rejections-shared';

const monthsSkeleton = [
  { ym: '2026-01', label: 'янв' },
  { ym: '2026-02', label: 'фев' },
];

const perManager: SalesRejectionPerManager[] = [
  {
    managerId: 100,
    name: 'Деговцова Елизавета',
    isActive: true,
    rejections: 10,
    lostAmount: 1_000_000,
    spam: 3,
    won: 10,
    monthCounts: { '2026-01': 4, '2026-02': 6 },
    reasonCounts: { '8584': 7, '8580': 3 },
  },
  {
    managerId: 200,
    name: 'Дудин Петр',
    isActive: false, // уволенный продажник — всё равно показываем
    rejections: 5,
    lostAmount: 500_000,
    spam: 1,
    won: 0,
    monthCounts: { '2026-02': 5 },
    reasonCounts: { '8580': 5 },
  },
];

describe('aggregateSelected', () => {
  it('оба менеджера — суммирует KPI, помесячно и причины', () => {
    const v = aggregateSelected(perManager, new Set([100, 200]), monthsSkeleton, '2026');
    expect(v.totalRejections).toBe(15);
    expect(v.lostAmount).toBe(1_500_000);
    expect(v.spamExcluded).toBe(4);
    // доля = 15 / (15 + 10) = 60%
    expect(v.lossRate).toBe(60);
    expect(v.avgLoss).toBe(100_000);
    expect(v.months.map((m) => m.count)).toEqual([4, 11]);
    // причины: 8580 = 3+5 = 8 (топ), 8584 = 7
    expect(v.reasons[0].count).toBe(8);
    expect(v.reasons[0].label).toBe('Ушли к конкурентам');
  });

  it('один менеджер — только его данные', () => {
    const v = aggregateSelected(perManager, new Set([200]), monthsSkeleton, '2026');
    expect(v.totalRejections).toBe(5);
    expect(v.lossRate).toBe(100); // won=0
    expect(v.months.map((m) => m.count)).toEqual([0, 5]);
  });

  it('никто не выбран — нули', () => {
    const v = aggregateSelected(perManager, new Set(), monthsSkeleton, '2026');
    expect(v.totalRejections).toBe(0);
    expect(v.lossRate).toBeNull();
    expect(v.reasons).toHaveLength(0);
  });
});

describe('managersFromPerManager', () => {
  it('строит таблицу с топ-причиной и долей, сортирует по отказам', () => {
    const rows = managersFromPerManager(perManager);
    expect(rows[0].managerId).toBe(100);
    expect(rows[0].topReason).toBe('Нехватка бюджета / нет финмодели'); // 8584=7 топ у 100
    expect(rows[0].lossRate).toBe(50); // 10/(10+10)
    expect(rows[0].isActive).toBe(true);
    expect(rows[1].lossRate).toBe(100); // 5/(5+0)
    expect(rows[1].isActive).toBe(false); // Дудин — уволен
  });
});
