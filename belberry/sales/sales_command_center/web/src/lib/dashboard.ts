import 'server-only';

import { and, eq, gte, lte, sql } from 'drizzle-orm';
import { db } from '@/db';
import { dealsSnapshot, managerActivity, plans, users } from '@/db/schema';

// Зеркало STAGE_RULES/STAGE_ORDER из runner/src/transform.py — воронка «Продажи» (CATEGORY_ID=10).
// Порядок = реальная последовательность стадий в Bitrix.
const STAGE_META: Record<string, { label: string; order: number }> = {
  'C10:NEW': { label: 'Квалификация', order: 1 },
  'C10:PREPAYMENT_INVOIC': { label: 'Подготовка БРИФа', order: 2 },
  'C10:EXECUTING': { label: 'Подготовка КП', order: 3 },
  'C10:FINAL_INVOICE': { label: 'Догрев и переговоры', order: 4 },
  'C10:UC_KC7195': { label: 'Подготовка договора', order: 5 },
};

export interface FunnelStage {
  stage: string;
  label: string;
  order: number;
  count: number;
  amount: number;
}

export interface StuckDeal {
  dealId: number;
  title: string;
  stageLabel: string;
  amount: number;
  stuckDays: number;
  manager: string;
}

export interface TeamMember {
  managerId: number;
  name: string;
  role: string;
  meetingsSet: number;
  meetingsHeld: number;
  dials: number;
  calls120: number;
  kpSent: number;
  briefs: number;
  dealsCreated: number;
  talkHours: number;
}

export interface DashboardData {
  monthLabel: string;
  snapshotDate: string | null;
  funnel: FunnelStage[];
  funnelCount: number;
  funnelAmount: number;
  stuck: StuckDeal[];
  team: TeamMember[];
  meetingsPlan: number;
  meetingsHeldTotal: number;
}

interface FunnelRow {
  stage: string;
  opportunity: number;
  stuckDays: number | null;
}

/** Группировка открытых сделок кат.10 по стадиям воронки. Чистая функция — тестируема. */
export function buildFunnel(rows: FunnelRow[]): FunnelStage[] {
  const acc = new Map<string, FunnelStage>();

  for (const row of rows) {
    const meta = STAGE_META[row.stage];
    if (!meta) continue; // незнакомые/закрытые стадии в воронку не считаем

    const current =
      acc.get(row.stage) ??
      ({ stage: row.stage, label: meta.label, order: meta.order, count: 0, amount: 0 } as FunnelStage);
    current.count += 1;
    current.amount += row.opportunity;
    acc.set(row.stage, current);
  }

  return Array.from(acc.values()).sort((a, b) => a.order - b.order);
}

const MONTHS_RU = [
  'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
  'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
];

function monthBounds(day: string): { start: string; end: string; label: string } {
  const [y, m] = day.split('-').map(Number);
  const start = `${y}-${String(m).padStart(2, '0')}-01`;
  const lastDay = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const end = `${y}-${String(m).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`;
  return { start, end, label: `${MONTHS_RU[m - 1]} ${y}` };
}

export async function getDashboardData(): Promise<DashboardData> {
  // Опорная дата = самый свежий снимок сделок; от него берём текущий месяц.
  const latest = await db
    .select({ d: sql<string>`max(${dealsSnapshot.reportDate})` })
    .from(dealsSnapshot);
  const snapshotDate = latest[0]?.d ?? null;

  if (!snapshotDate) {
    return {
      monthLabel: '—',
      snapshotDate: null,
      funnel: [],
      funnelCount: 0,
      funnelAmount: 0,
      stuck: [],
      team: [],
      meetingsPlan: 20,
      meetingsHeldTotal: 0,
    };
  }

  const { start, end, label } = monthBounds(snapshotDate);

  // Имена/роли сотрудников.
  const userRows = await db
    .select({ id: users.bitrixId, name: users.name, role: users.role })
    .from(users);
  const userMap = new Map(userRows.map((u) => [u.id, { name: u.name, role: u.role }]));

  // Воронка — открытые сделки кат.10 на последнем снимке.
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

  const funnelRows: FunnelRow[] = snapRows.map((r) => ({
    stage: r.stage,
    opportunity: Number(r.opportunity ?? 0),
    stuckDays: r.stuckDays,
  }));
  const funnel = buildFunnel(funnelRows);
  const funnelCount = funnel.reduce((s, x) => s + x.count, 0);
  const funnelAmount = funnel.reduce((s, x) => s + x.amount, 0);

  const stuck: StuckDeal[] = snapRows
    .filter((r) => STAGE_META[r.stage] && (r.stuckDays ?? 0) > 0)
    .sort((a, b) => (b.stuckDays ?? 0) - (a.stuckDays ?? 0) || Number(b.opportunity ?? 0) - Number(a.opportunity ?? 0))
    .slice(0, 6)
    .map((r) => ({
      dealId: r.dealId,
      title: r.title ?? `Сделка #${r.dealId}`,
      stageLabel: STAGE_META[r.stage]?.label ?? r.stage,
      amount: Number(r.opportunity ?? 0),
      stuckDays: r.stuckDays ?? 0,
      manager: (r.managerId && userMap.get(r.managerId)?.name) || '—',
    }));

  // Команда — сумма активности за месяц.
  const actRows = await db
    .select({
      managerId: managerActivity.managerId,
      meetingsSet: sql<number>`coalesce(sum(${managerActivity.meetingsSet}),0)`,
      meetingsHeld: sql<number>`coalesce(sum(${managerActivity.meetingsHeld}),0)`,
      dials: sql<number>`coalesce(sum(${managerActivity.dialsTotal}),0)`,
      calls120: sql<number>`coalesce(sum(${managerActivity.calls120sPlus}),0)`,
      kpSent: sql<number>`coalesce(sum(${managerActivity.kpSent}),0)`,
      briefs: sql<number>`coalesce(sum(${managerActivity.briefsCreated}),0)`,
      dealsCreated: sql<number>`coalesce(sum(${managerActivity.dealsCreatedCount}),0)`,
      talkSeconds: sql<number>`coalesce(sum(${managerActivity.talkSeconds}),0)`,
    })
    .from(managerActivity)
    .where(and(gte(managerActivity.reportDate, start), lte(managerActivity.reportDate, end)))
    .groupBy(managerActivity.managerId);

  const team: TeamMember[] = actRows
    .map((r) => ({
      managerId: r.managerId,
      name: userMap.get(r.managerId)?.name ?? `id ${r.managerId}`,
      role: userMap.get(r.managerId)?.role ?? '',
      meetingsSet: Number(r.meetingsSet),
      meetingsHeld: Number(r.meetingsHeld),
      dials: Number(r.dials),
      calls120: Number(r.calls120),
      kpSent: Number(r.kpSent),
      briefs: Number(r.briefs),
      dealsCreated: Number(r.dealsCreated),
      talkHours: Math.round(Number(r.talkSeconds) / 360) / 10,
    }))
    .sort((a, b) => b.meetingsHeld - a.meetingsHeld || b.dials - a.dials);

  const meetingsHeldTotal = team.reduce((s, x) => s + x.meetingsHeld, 0);

  // План ТМ по встречам из таблицы plans (period 'YYYY-MM', metric 'meetings', глобальный).
  const period = start.slice(0, 7);
  const planRows = await db
    .select({ target: plans.target })
    .from(plans)
    .where(and(eq(plans.period, period), eq(plans.metric, 'meetings')))
    .limit(1);
  const meetingsPlan = planRows[0] ? Number(planRows[0].target) : 20;

  return {
    monthLabel: label,
    snapshotDate,
    funnel,
    funnelCount,
    funnelAmount,
    stuck,
    team,
    meetingsPlan,
    meetingsHeldTotal,
  };
}
