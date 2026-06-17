import { describe, expect, it } from 'vitest';
import type { AlertManager, BurningDeal, TaskItem } from '@/lib/alerts';
import { filterSection, sectionManagers } from '@/lib/alerts-filter';

const burning = (dealId: number, managerId: number | null, severity: BurningDeal['severity'] = 'warning'): BurningDeal => ({
  dealId, title: `deal ${dealId}`, stageLabel: 'КП', amount: 100_000, stuckDays: 10,
  managerId, manager: managerId ? `m${managerId}` : '—', severity, reason: 'застряла 10 дн.',
});
const task = (taskId: number, managerId: number | null, overdue = false): TaskItem => ({
  taskId, title: `task ${taskId}`, dealId: null, managerId, manager: managerId ? `m${managerId}` : '—',
  deadline: null, status: 2, statusLabel: 'ждёт выполнения', overdue,
});

const lookup = new Map<number, AlertManager>([
  [10, { managerId: 10, name: 'Алла', isActive: true }],
  [20, { managerId: 20, name: 'Борис', isActive: true }],
  [30, { managerId: 30, name: 'Вера', isActive: false }],
]);

describe('sectionManagers', () => {
  it('уникальные менеджеры секции по алфавиту, без null', () => {
    const items = [burning(1, 30), burning(2, 10), burning(3, 10), burning(4, null)];
    const mgrs = sectionManagers(items, lookup);
    expect(mgrs.map((m) => m.name)).toEqual(['Алла', 'Вера']);
    expect(mgrs.find((m) => m.managerId === 30)?.isActive).toBe(false);
  });

  it('пустой список → пусто (пикер скрыт)', () => {
    expect(sectionManagers([], lookup)).toEqual([]);
  });
});

describe('filterSection', () => {
  const items = [burning(1, 10, 'critical'), burning(2, 20), burning(3, 30), burning(4, null)];

  it('все выбраны → всё, включая элемент без менеджера', () => {
    const r = filterSection(items, new Set([10, 20, 30]), 3, 12);
    expect(r.map((b) => b.dealId)).toEqual([1, 2, 3, 4]);
  });

  it('один менеджер → только его', () => {
    const r = filterSection(items, new Set([10]), 3, 12);
    expect(r.map((b) => b.dealId)).toEqual([1]);
  });

  it('подмножество скрывает элемент без менеджера', () => {
    const r = filterSection(items, new Set([10, 20]), 3, 12);
    expect(r.map((b) => b.dealId)).toEqual([1, 2]);
  });

  it('пустой выбор → пусто', () => {
    expect(filterSection(items, new Set(), 3, 12)).toHaveLength(0);
  });

  it('секции независимы: фильтр одной не трогает другую', () => {
    const tasks = [task(6, 10, true), task(7, 20)];
    const burnSel = new Set([20]); // в «Горит» оставили Бориса
    const taskSel = new Set([10, 20]); // в «Задачах» — всех
    expect(filterSection(items, burnSel, 3, 12).map((b) => b.dealId)).toEqual([2]);
    expect(filterSection(tasks, taskSel, 2, 50).map((t) => t.taskId)).toEqual([6, 7]);
  });

  it('режет до топ-N после фильтра', () => {
    const many = Array.from({ length: 20 }, (_, i) => burning(100 + i, 10));
    expect(filterSection(many, new Set([10]), 1, 12)).toHaveLength(12);
  });
});
