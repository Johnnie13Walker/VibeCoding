import { describe, expect, it } from 'vitest';
import type { AlertManager, BurningDeal, TaskItem } from '@/lib/alerts';
import { filterSection, filterTasks, sectionManagers, taskKind } from '@/lib/alerts-filter';

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

// Задача с заданными статусом/просрочкой для тестов типов.
const taskT = (taskId: number, managerId: number | null, status: number, overdue = false): TaskItem => ({
  taskId, title: `task ${taskId}`, dealId: null, managerId, manager: managerId ? `m${managerId}` : '—',
  deadline: null, status, statusLabel: 'x', overdue,
});

describe('taskKind', () => {
  it('просрочка важнее статуса', () => {
    expect(taskKind({ overdue: true, status: 2 })).toBe('overdue');
  });
  it('статус 4 → контроль (если не просрочена)', () => {
    expect(taskKind({ overdue: false, status: 4 })).toBe('control');
  });
  it('ждёт/в работе/отложена → await', () => {
    expect(taskKind({ overdue: false, status: 2 })).toBe('await');
    expect(taskKind({ overdue: false, status: 3 })).toBe('await');
    expect(taskKind({ overdue: false, status: 6 })).toBe('await');
  });
});

describe('filterTasks', () => {
  // 1 просрочена(10), 2 на контроле(20), 3 ждёт(10)
  const items = [taskT(1, 10, 2, true), taskT(2, 20, 4), taskT(3, 10, 2)];
  const allMgr = new Set([10, 20]);
  const allKind = new Set(['overdue', 'control', 'await'] as const);

  it('всё выбрано → все задачи', () => {
    expect(filterTasks(items, allMgr, 2, new Set(allKind), 50).map((t) => t.taskId)).toEqual([1, 2, 3]);
  });
  it('только тип «на контроле»', () => {
    expect(filterTasks(items, allMgr, 2, new Set(['control'] as const), 50).map((t) => t.taskId)).toEqual([2]);
  });
  it('тип И менеджер комбинируются (И между фильтрами)', () => {
    // просрочка + только менеджер 10 → задача 1 (у 20 нет просрочки)
    expect(filterTasks(items, new Set([10]), 2, new Set(['overdue'] as const), 50).map((t) => t.taskId)).toEqual([1]);
  });
  it('несколько типов = ИЛИ', () => {
    expect(filterTasks(items, allMgr, 2, new Set(['overdue', 'control'] as const), 50).map((t) => t.taskId)).toEqual([1, 2]);
  });
  it('пустой выбор типов → пусто', () => {
    expect(filterTasks(items, allMgr, 2, new Set(), 50)).toHaveLength(0);
  });
});
