import type { AlertManager } from './alerts';

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
