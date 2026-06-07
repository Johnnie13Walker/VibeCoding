import { describe, expect, it } from 'vitest';
import { buildSalesRejections, type MgrReasonRow } from '@/lib/sales-rejections';

const months = [
  { ym: '2026-01', label: 'янв', count: 0 },
  { ym: '2026-02', label: 'фев', count: 0 },
];

describe('buildSalesRejections', () => {
  const rows: MgrReasonRow[] = [
    { managerId: 100, reasonId: 8584, count: 10, amount: 1_000_000 }, // действующий продажник
    { managerId: 100, reasonId: 8588, count: 3, amount: 90_000 }, // СПАМ — исключаем
    { managerId: 200, reasonId: 8580, count: 6, amount: 600_000 }, // ТМ (передано) — не в списке
    { managerId: 300, reasonId: 8574, count: 4, amount: 200_000 }, // уволенный — не в списке
  ];
  const won = new Map<number, number>([
    [100, 10],
    [200, 0],
    [300, 0],
  ]);
  const names = new Map<number, string>([
    [100, 'Деговцова Елизавета'],
    [200, 'Вострецов Аркадий'],
    [300, 'id 300'],
  ]);
  const eligible = new Set<number>([100]); // только действующий продажник

  const r = buildSalesRejections(rows, won, names, months, '2026', eligible);

  it('СПАМ исключён из отказов и посчитан отдельно', () => {
    expect(r.spamExcluded).toBe(3);
    // отдел: 10 + 6 + 4 = 20 (без спама), деньги 1.8М
    expect(r.totalRejections).toBe(20);
    expect(r.lostAmount).toBe(1_800_000);
  });

  it('итоги отдела — по всем (вкл. ТМ и уволенных), доля по всем оплатам', () => {
    // wonTotal = 10 (только у 100), доля = 20/(20+10) = 67%
    expect(r.wonTotal).toBe(10);
    expect(r.lossRate).toBe(67);
  });

  it('список по менеджерам — только действующие продажники', () => {
    expect(r.managers).toHaveLength(1);
    expect(r.managers[0].managerId).toBe(100);
    expect(r.managers[0].rejections).toBe(10);
    expect(r.managers[0].topReason).toBe('Нехватка бюджета / нет финмодели');
  });

  it('итоги по показанным менеджерам отделены от итогов отдела', () => {
    expect(r.managersRejections).toBe(10);
    expect(r.managersLostAmount).toBe(1_000_000);
    // 10 / (10 + 10) = 50%
    expect(r.managersLossRate).toBe(50);
  });

  it('без фильтра (eligible=null) показываем всех', () => {
    const all = buildSalesRejections(rows, won, names, months, '2026', null);
    expect(all.managers).toHaveLength(3);
  });
});
