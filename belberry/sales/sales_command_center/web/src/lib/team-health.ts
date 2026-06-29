import 'server-only';

import { cache } from 'react';
import { eq, sql } from 'drizzle-orm';
import { db } from '@/db';
import { teamTaskHealth } from '@/db/schema';

export type TeamGroup = 'sales' | 'tm';

export interface TeamMemberHealth {
  managerId: number;
  name: string;
  dept: string | null;
  group: TeamGroup;
  efficiencyPct: number | null;
  overdueTasks: number;
  overdueActivities: number;
  overdueTotal: number;
}

/** Группа сотрудника по должности: телемаркетинг vs отдел продаж (ОП+РОП). */
export function teamGroup(dept: string | null): TeamGroup {
  return (dept || '').toLowerCase().includes('телемарк') ? 'tm' : 'sales';
}

export interface TeamHealthData {
  snapshotDate: string | null;
  members: TeamMemberHealth[];
}

/**
 * Сортировка «сначала проблемные»: больше всего просрочек сверху, при равенстве —
 * ниже КПД выше. Пустой КПД (нет закрытых с дедлайном) уводим вниз (101).
 * Вынесено отдельно для юнит-теста (без БД).
 */
export function sortByProblems(members: TeamMemberHealth[]): TeamMemberHealth[] {
  return [...members].sort(
    (a, b) => b.overdueTotal - a.overdueTotal || (a.efficiencyPct ?? 101) - (b.efficiencyPct ?? 101),
  );
}

export const getTeamHealth = cache(async function getTeamHealth(): Promise<TeamHealthData> {
  const latest = await db
    .select({ d: sql<string>`max(${teamTaskHealth.reportDate})` })
    .from(teamTaskHealth);
  const snapshotDate = latest[0]?.d ?? null;
  if (!snapshotDate) return { snapshotDate: null, members: [] };

  const rows = await db.select().from(teamTaskHealth).where(eq(teamTaskHealth.reportDate, snapshotDate));
  const members: TeamMemberHealth[] = rows.map((r) => ({
    managerId: r.managerId,
    name: r.name ?? `#${r.managerId}`,
    dept: r.dept,
    group: teamGroup(r.dept),
    efficiencyPct: r.efficiencyPct == null ? null : Number(r.efficiencyPct),
    overdueTasks: r.overdueTasks,
    overdueActivities: r.overdueActivities,
    overdueTotal: r.overdueTasks + r.overdueActivities,
  }));
  return { snapshotDate, members: sortByProblems(members) };
});

export function findMember(data: TeamHealthData, managerId: number): TeamMemberHealth | null {
  return data.members.find((m) => m.managerId === managerId) ?? null;
}

/** Цветовой уровень КПД для UI: good ≥85, warn ≥60, bad <60, unknown — нет данных. */
export function effLevel(pct: number | null): 'good' | 'warn' | 'bad' | 'unknown' {
  if (pct == null) return 'unknown';
  if (pct >= 85) return 'good';
  if (pct >= 60) return 'warn';
  return 'bad';
}

// Владелец командного центра (видит данные всех, включая РОПа). Роли в users
// не всегда заполнены, поэтому держим явный id как запасной признак директора.
export const DIRECTOR_BITRIX_ID = 12; // Щемелёв Евгений

/** Сотрудник — РОП (по должности). Данные РОПа закрыты от рядовых менеджеров. */
export function isRopDept(dept: string | null): boolean {
  return (dept || '').trim().toLowerCase() === 'роп';
}

export interface Viewer {
  bitrixId?: number;
  role?: string | null;
}

/**
 * Видит ли зритель данные конкретного сотрудника. Все видят всех, КРОМЕ РОПа:
 * данные РОПа открыты только директору/владельцу (id 12) и самому РОПу.
 */
export function canViewMember(viewer: Viewer, member: { managerId: number; dept: string | null }): boolean {
  if (!isRopDept(member.dept)) return true;
  if (viewer.role === 'director' || viewer.bitrixId === DIRECTOR_BITRIX_ID) return true;
  return viewer.bitrixId === member.managerId;
}
