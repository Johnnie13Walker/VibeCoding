import type { AlertManager, TaskItem } from './alerts';

/** Срез топ-N для каждого раздела — применяется ПОСЛЕ фильтра по менеджерам. */
export const BURNING_TOP = 12;
export const SILENT_TOP = 15;
export const TASKS_TOP = 50;

export interface HasManager {
  managerId: number | null;
}

/** Уникальные менеджеры, встречающиеся в списке секции, по алфавиту. */
export function sectionManagers(items: HasManager[], lookup: Map<number, AlertManager>): AlertManager[] {
  const seen = new Map<number, AlertManager>();
  for (const it of items) {
    const id = it.managerId;
    if (id == null || seen.has(id)) continue;
    seen.set(id, lookup.get(id) ?? { managerId: id, name: `#${id}`, isActive: true });
  }
  return [...seen.values()].sort((a, b) => a.name.localeCompare(b.name, 'ru'));
}

/**
 * Фильтрует список одной секции по выбранным менеджерам и режет до топ-N.
 * «Все выбраны» (selected.size === managerCount) → показываем всё, включая элементы
 * без менеджера; иначе — только те, чей managerId попал в выбор.
 */
export function filterSection<T extends HasManager>(
  items: T[],
  selected: Set<number>,
  managerCount: number,
  topN: number,
): T[] {
  const allSelected = managerCount > 0 && selected.size === managerCount;
  return items
    .filter((it) => allSelected || (it.managerId != null && selected.has(it.managerId)))
    .slice(0, topN);
}

/** Тип задачи для фильтра: просрочена / на контроле / ждёт выполнения. */
export type TaskKind = 'overdue' | 'control' | 'await';

export const TASK_KINDS: TaskKind[] = ['overdue', 'control', 'await'];

/** Классификация задачи по типу: просрочка важнее статуса; статус 4 → контроль;
 * остальное (ждёт/в работе/отложена) → «ждёт выполнения». */
export function taskKind(t: Pick<TaskItem, 'overdue' | 'status'>): TaskKind {
  if (t.overdue) return 'overdue';
  if (t.status === 4) return 'control';
  return 'await';
}

/**
 * Фильтр задач по менеджерам И типам, затем срез топ-N. Внутри фильтра — ИЛИ
 * (любой отмеченный), между фильтрами — И. «Все выбраны» по менеджерам → включая
 * задачи без менеджера.
 */
export function filterTasks(
  items: TaskItem[],
  selectedManagers: Set<number>,
  managerCount: number,
  selectedKinds: Set<TaskKind>,
  topN: number,
): TaskItem[] {
  const allManagers = managerCount > 0 && selectedManagers.size === managerCount;
  return items
    .filter((t) => allManagers || (t.managerId != null && selectedManagers.has(t.managerId)))
    .filter((t) => selectedKinds.has(taskKind(t)))
    .slice(0, topN);
}
