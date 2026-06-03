import 'server-only';

import { and, desc, eq, gte, sql } from 'drizzle-orm';
import { db } from '@/db';
import { dealsSnapshot, meetings, users } from '@/db/schema';
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

export interface PromiseItem {
  meetingId: number;
  dealId: number | null;
  dealTitle: string | null;
  what: string;
  who: string | null;
  deadline: string | null;
  manager: string;
  reportDate: string;
  overdue: boolean;
}

export interface AlertsData {
  snapshotDate: string | null;
  burning: BurningDeal[];
  promises: PromiseItem[];
  count: number;
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

/** Просрочено ли обещание: дедлайн-дата уже прошла (today в МСК). Свободный текст → не считаем. */
export function isPromiseOverdue(deadline: string | null | undefined, today: string): boolean {
  if (!deadline) return false;
  const iso = String(deadline).trim().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return false;
  return iso < today;
}

function todayMsk(): string {
  // Дата в МСК в формате YYYY-MM-DD.
  const parts = new Intl.DateTimeFormat('en-CA', {
    year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'Europe/Moscow',
  }).format(new Date());
  return parts;
}

export async function getAlerts(): Promise<AlertsData> {
  const latest = await db.select({ d: sql<string>`max(${dealsSnapshot.reportDate})` }).from(dealsSnapshot);
  const snapshotDate = latest[0]?.d ?? null;
  if (!snapshotDate) {
    return { snapshotDate: null, burning: [], promises: [], count: 0 };
  }

  const userRows = await db.select({ id: users.bitrixId, name: users.name }).from(users);
  const userMap = new Map(userRows.map((u) => [u.id, u.name]));

  // Горящие сделки — открытые кат.10 на последнем снимке, застрявшие.
  const snapRows = await db
    .select({
      dealId: dealsSnapshot.dealId,
      stage: dealsSnapshot.stage,
      opportunity: dealsSnapshot.opportunity,
      stuckDays: dealsSnapshot.stuckDays,
      managerId: dealsSnapshot.managerId,
      title: dealsSnapshot.title,
    })
    .from(dealsSnapshot)
    .where(and(eq(dealsSnapshot.reportDate, snapshotDate), eq(dealsSnapshot.categoryId, 10)));

  const burning: BurningDeal[] = snapRows
    .filter((r) => STAGE_META[r.stage] && (r.stuckDays ?? 0) > 0)
    .map((r) => {
      const amount = Number(r.opportunity ?? 0);
      const stuckDays = r.stuckDays ?? 0;
      return {
        dealId: r.dealId,
        title: r.title ?? `Сделка #${r.dealId}`,
        stageLabel: STAGE_META[r.stage]?.label ?? r.stage,
        amount,
        stuckDays,
        manager: (r.managerId && userMap.get(r.managerId)) || '—',
        severity: dealSeverity(amount, stuckDays),
        reason: dealReason(amount, stuckDays),
      };
    })
    .sort((a, b) => {
      if (a.severity !== b.severity) return a.severity === 'critical' ? -1 : 1;
      return b.stuckDays - a.stuckDays || b.amount - a.amount;
    })
    .slice(0, 12);

  // Обещания клиентам — следующие шаги из разборов встреч за последние ~21 день.
  const [sy, sm, sd] = snapshotDate.split('-').map(Number);
  const since = new Date(Date.UTC(sy, sm - 1, sd)); // месяц 0-индексный
  since.setUTCDate(since.getUTCDate() - 21);
  const sinceStr = since.toISOString().slice(0, 10);
  const today = todayMsk();

  const titleByDeal = new Map(snapRows.map((r) => [r.dealId, r.title ?? null]));

  const meetingRows = await db
    .select({
      meetingId: meetings.meetingId,
      dealId: meetings.dealId,
      managerId: meetings.managerId,
      reportDate: meetings.reportDate,
      step: sql<unknown>`${meetings.analysisJson} -> 'next_step'`,
    })
    .from(meetings)
    .where(and(gte(meetings.reportDate, sinceStr), sql`${meetings.analysisJson} -> 'next_step' is not null`))
    .orderBy(desc(meetings.reportDate))
    .limit(20);

  const promises: PromiseItem[] = [];
  for (const m of meetingRows) {
    const step = (m.step ?? null) as { what?: string; who?: string; deadline?: string } | null;
    const what = step && typeof step === 'object' ? String(step.what ?? '').trim() : '';
    if (!what) continue;
    const deadline = step?.deadline ? String(step.deadline) : null;
    promises.push({
      meetingId: m.meetingId,
      dealId: m.dealId,
      dealTitle: (m.dealId != null ? titleByDeal.get(m.dealId) : null) ?? null,
      what,
      who: step?.who ? String(step.who) : null,
      deadline,
      manager: (m.managerId && userMap.get(m.managerId)) || '—',
      reportDate: String(m.reportDate),
      overdue: isPromiseOverdue(deadline, today),
    });
  }

  const count = burning.filter((b) => b.severity === 'critical').length + promises.filter((p) => p.overdue).length;

  return { snapshotDate, burning, promises, count };
}
