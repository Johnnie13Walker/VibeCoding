import 'server-only';

import { and, asc, eq, sql } from 'drizzle-orm';
import { db } from '@/db';
import { dealsSnapshot, meetingTasks, users } from '@/db/schema';
import { STAGE_META } from './dashboard';

export interface BurningDeal {
  dealId: number;
  title: string;
  stageLabel: string;
  amount: number;
  stuckDays: number;
  manager: string;
  severity: 'critical' | 'warning';
  reason: string;
}

export interface SilentDeal {
  dealId: number;
  title: string;
  stageLabel: string;
  amount: number;
  silenceDays: number;
  lastCommAt: string | null;
  manager: string;
  severity: 'critical' | 'warning';
  reason: string;
}

export interface TaskItem {
  taskId: number;
  title: string;
  dealId: number | null;
  manager: string;
  deadline: string | null;
  status: number | null;
  statusLabel: string;
  overdue: boolean;
}

export interface AlertsData {
  snapshotDate: string | null;
  burning: BurningDeal[];
  silent: SilentDeal[];
  tasks: TaskItem[];
  count: number;
}

/** Порог «тишины»: сделка без коммуникации с клиентом более стольких кал. дней. */
export const SILENCE_THRESHOLD_DAYS = 14;

/**
 * Дни тишины по сделке. Если есть дата последней коммуникации — кал. дни от неё до
 * снимка. Если коммуникации не было вовсе (lastCommAt = null) — берём возраст застоя
 * на стадии (stuckDays) как нижнюю оценку; если и он неизвестен → null (не судим).
 */
export function silenceDays(
  lastCommAt: string | null,
  stuckDays: number | null,
  snapshotDate: string,
): number | null {
  if (lastCommAt) {
    const from = new Date(`${lastCommAt}T00:00:00Z`).getTime();
    const to = new Date(`${snapshotDate}T00:00:00Z`).getTime();
    if (Number.isNaN(from) || Number.isNaN(to)) return null;
    const days = Math.floor((to - from) / 86_400_000);
    return days >= 0 ? days : 0;
  }
  if (stuckDays != null && stuckDays > 0) return stuckDays;
  return null;
}

export function silenceSeverity(days: number): 'critical' | 'warning' {
  return days >= 30 ? 'critical' : 'warning';
}

export function silenceReason(lastCommAt: string | null, days: number): string {
  return lastCommAt ? `молчит ${days} дн.` : 'контакта не было';
}

/** Причина риска по сделке (зеркало transform.risk_reason, web-сторона). */
export function dealReason(amount: number, stuckDays: number): string {
  if (amount <= 0) return 'нет бюджета';
  if (stuckDays >= 31) return 'критический возраст';
  return `застряла ${stuckDays} дн.`;
}

export function dealSeverity(amount: number, stuckDays: number): 'critical' | 'warning' {
  if (stuckDays >= 31 || (amount >= 500_000 && stuckDays >= 14)) return 'critical';
  return 'warning';
}

// Статусы Bitrix-задач: 2 ждёт выполнения, 3 выполняется, 4 ждёт контроля, 6 отложена.
const STATUS_LABEL: Record<number, string> = {
  2: 'ждёт выполнения',
  3: 'в работе',
  4: 'ждёт контроля',
  6: 'отложена',
};

export function isOverdue(deadline: Date | string | null | undefined, now: Date): boolean {
  if (!deadline) return false;
  const d = deadline instanceof Date ? deadline : new Date(deadline);
  return !Number.isNaN(d.getTime()) && d.getTime() < now.getTime();
}

export async function getAlerts(): Promise<AlertsData> {
  const latest = await db.select({ d: sql<string>`max(${dealsSnapshot.reportDate})` }).from(dealsSnapshot);
  const snapshotDate = latest[0]?.d ?? null;

  const userRows = await db.select({ id: users.bitrixId, name: users.name }).from(users);
  const userMap = new Map(userRows.map((u) => [u.id, u.name]));

  // Горящие сделки — открытые кат.10 на последнем снимке, застрявшие.
  const burning: BurningDeal[] = [];
  const silent: SilentDeal[] = [];
  if (snapshotDate) {
    const snapRows = await db
      .select({
        dealId: dealsSnapshot.dealId,
        stage: dealsSnapshot.stage,
        opportunity: dealsSnapshot.opportunity,
        stuckDays: dealsSnapshot.stuckDays,
        lastCommAt: dealsSnapshot.lastCommAt,
        managerId: dealsSnapshot.managerId,
        title: dealsSnapshot.title,
      })
      .from(dealsSnapshot)
      .where(and(eq(dealsSnapshot.reportDate, snapshotDate), eq(dealsSnapshot.categoryId, 10)));

    // Тишина — открытые кат.10 без коммуникации с клиентом >14 кал. дней.
    for (const r of snapRows) {
      if (!STAGE_META[r.stage]) continue;
      const days = silenceDays(r.lastCommAt, r.stuckDays, snapshotDate);
      if (days == null || days <= SILENCE_THRESHOLD_DAYS) continue;
      const amount = Number(r.opportunity ?? 0);
      silent.push({
        dealId: r.dealId,
        title: r.title ?? `Сделка #${r.dealId}`,
        stageLabel: STAGE_META[r.stage]?.label ?? r.stage,
        amount,
        silenceDays: days,
        lastCommAt: r.lastCommAt ?? null,
        manager: (r.managerId && userMap.get(r.managerId)) || '—',
        severity: silenceSeverity(days),
        reason: silenceReason(r.lastCommAt, days),
      });
    }
    silent.sort((a, b) => {
      if (a.severity !== b.severity) return a.severity === 'critical' ? -1 : 1;
      return b.silenceDays - a.silenceDays || b.amount - a.amount;
    });

    for (const r of snapRows) {
      if (!STAGE_META[r.stage] || (r.stuckDays ?? 0) <= 0) continue;
      const amount = Number(r.opportunity ?? 0);
      const stuckDays = r.stuckDays ?? 0;
      burning.push({
        dealId: r.dealId,
        title: r.title ?? `Сделка #${r.dealId}`,
        stageLabel: STAGE_META[r.stage]?.label ?? r.stage,
        amount,
        stuckDays,
        manager: (r.managerId && userMap.get(r.managerId)) || '—',
        severity: dealSeverity(amount, stuckDays),
        reason: dealReason(amount, stuckDays),
      });
    }
    burning.sort((a, b) => {
      if (a.severity !== b.severity) return a.severity === 'critical' ? -1 : 1;
      return b.stuckDays - a.stuckDays || b.amount - a.amount;
    });
  }

  // Задачи на контроле — открытые автозадачи из разбора встреч (meeting_tasks.closed=false).
  const now = new Date();
  const taskRows = await db
    .select({
      taskId: meetingTasks.taskId,
      title: meetingTasks.title,
      dealId: meetingTasks.dealId,
      responsibleId: meetingTasks.responsibleId,
      deadline: meetingTasks.deadline,
      status: meetingTasks.status,
    })
    .from(meetingTasks)
    .where(eq(meetingTasks.closed, false))
    .orderBy(asc(meetingTasks.deadline))
    .limit(50);

  const tasks: TaskItem[] = taskRows.map((t) => {
    const deadline = t.deadline ? new Date(t.deadline) : null;
    return {
      taskId: t.taskId,
      title: t.title ?? `Задача #${t.taskId}`,
      dealId: t.dealId,
      manager: (t.responsibleId && userMap.get(t.responsibleId)) || '—',
      deadline: deadline ? deadline.toISOString() : null,
      status: t.status,
      statusLabel: (t.status != null && STATUS_LABEL[t.status]) || 'в работе',
      overdue: isOverdue(deadline, now),
    };
  });

  const count =
    burning.filter((b) => b.severity === 'critical').length +
    silent.filter((s) => s.severity === 'critical').length +
    tasks.filter((t) => t.overdue).length;
  return { snapshotDate, burning: burning.slice(0, 12), silent: silent.slice(0, 15), tasks, count };
}
