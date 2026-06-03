import 'server-only';

import { and, desc, eq, gte, lte, sql } from 'drizzle-orm';
import { db } from '@/db';
import { dealsSnapshot, managerActivity, meetings, plans, reports, users } from '@/db/schema';

// Зеркало STAGE_RULES/STAGE_ORDER из runner/src/transform.py — воронка «Продажи» (CATEGORY_ID=10).
// Порядок = реальная последовательность стадий в Bitrix.
export const STAGE_META: Record<string, { label: string; order: number }> = {
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

export interface ManagerMeeting {
  date: string;
  score: number | null;
  note: string;
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
  /** Тренд встреч по дням месяца — для спарклайна в дрилл-дауне. */
  trend: number[];
  /** Последние разобранные встречи (балл + заметка) — для дрилл-дауна. */
  meetings: ManagerMeeting[];
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
  dialsTotal: number;
  kpTotal: number;
  dealsCreatedTotal: number;
  deltas: { meetings: KpiDelta; dials: KpiDelta; kp: KpiDelta; deals: KpiDelta };
  trend: TrendPoint[];
  health: number;
  generatedAt: string | null;
}

export interface KpiDelta {
  pct: number | null;
  dir: 'up' | 'down' | 'flat';
  /** Готовая подпись: «+34%», «×11», «новое» — или null (нечего показывать). */
  label: string | null;
}

export interface TrendPoint {
  date: string;
  meetings: number;
  dials: number;
}

function delta(current: number, prev: number): KpiDelta {
  if (!prev) {
    return { pct: null, dir: current > 0 ? 'up' : 'flat', label: current > 0 ? 'новое' : null };
  }
  const pct = Math.round(((current - prev) / prev) * 100);
  const dir = pct > 0 ? 'up' : pct < 0 ? 'down' : 'flat';
  // Дикие проценты (крошечный прошлый месяц) показываем кратностью: «×11».
  let label: string;
  if (Math.abs(pct) >= 1000) {
    const x = current / prev;
    label = `×${x >= 10 ? Math.round(x) : x.toFixed(1)}`;
  } else {
    label = `${pct > 0 ? '+' : ''}${pct}%`;
  }
  return { pct, dir, label };
}

/** Здоровье месяца 0-100: выполнение плана встреч − штраф за затор. Детерминировано. */
export function monthHealth(
  meetingsHeld: number,
  meetingsPlan: number,
  activeManagers: number,
  stuckCount: number,
): number {
  const target = Math.max(1, meetingsPlan * Math.max(1, activeManagers));
  const attainment = Math.min(1, meetingsHeld / target) * 100;
  const penalty = Math.min(25, stuckCount * 4);
  return Math.max(0, Math.min(100, Math.round(attainment - penalty)));
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
    const zeroDelta: KpiDelta = { pct: null, dir: 'flat', label: null };
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
      dialsTotal: 0,
      kpTotal: 0,
      dealsCreatedTotal: 0,
      deltas: { meetings: zeroDelta, dials: zeroDelta, kp: zeroDelta, deals: zeroDelta },
      trend: [],
      health: 0,
      generatedAt: null,
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

  // Дрилл-даун: тренд встреч по дням на менеджера.
  const trendByMgrRows = await db
    .select({
      managerId: managerActivity.managerId,
      date: managerActivity.reportDate,
      meetings: sql<number>`coalesce(sum(${managerActivity.meetingsHeld}),0)`,
    })
    .from(managerActivity)
    .where(and(gte(managerActivity.reportDate, start), lte(managerActivity.reportDate, end)))
    .groupBy(managerActivity.managerId, managerActivity.reportDate)
    .orderBy(managerActivity.reportDate);
  const trendByMgr = new Map<number, number[]>();
  for (const r of trendByMgrRows) {
    const arr = trendByMgr.get(r.managerId) ?? [];
    arr.push(Number(r.meetings));
    trendByMgr.set(r.managerId, arr);
  }

  // Дрилл-даун: последние разобранные встречи на менеджера (балл + заметка).
  const anRows = await db
    .select({
      managerId: meetings.managerId,
      date: meetings.reportDate,
      analysis: meetings.analysisJson,
    })
    .from(meetings)
    .where(and(gte(meetings.reportDate, start), lte(meetings.reportDate, end), sql`${meetings.analysisJson} is not null`))
    .orderBy(desc(meetings.reportDate));
  const meetingsByMgr = new Map<number, ManagerMeeting[]>();
  for (const r of anRows) {
    if (r.managerId == null) continue;
    const a = (r.analysis ?? {}) as {
      score?: number;
      observations?: { kind?: string; text?: string }[];
      verdict?: string;
      systemic_conclusion?: string;
    };
    const risk = (a.observations ?? []).find((o) => o.kind === 'risk' && o.text);
    const note = (risk?.text || a.verdict || a.systemic_conclusion || '').toString().trim();
    const list = meetingsByMgr.get(r.managerId) ?? [];
    if (list.length < 5) {
      list.push({ date: String(r.date), score: a.score ?? null, note });
      meetingsByMgr.set(r.managerId, list);
    }
  }

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
      trend: trendByMgr.get(r.managerId) ?? [],
      meetings: meetingsByMgr.get(r.managerId) ?? [],
    }))
    .sort((a, b) => b.meetingsHeld - a.meetingsHeld || b.dials - a.dials);

  const meetingsHeldTotal = team.reduce((s, x) => s + x.meetingsHeld, 0);
  const dialsTotal = team.reduce((s, x) => s + x.dials, 0);
  const kpTotal = team.reduce((s, x) => s + x.kpSent, 0);
  const dealsCreatedTotal = team.reduce((s, x) => s + x.dealsCreated, 0);

  // Δ к прошлому месяцу — суммы активности за предыдущий календарный месяц.
  const [py, pm] = start.split('-').map(Number);
  const prevStart = `${pm === 1 ? py - 1 : py}-${String(pm === 1 ? 12 : pm - 1).padStart(2, '0')}-01`;
  const prevEndDay = new Date(Date.UTC(py, pm - 1, 0)).getUTCDate();
  const prevEnd = `${prevStart.slice(0, 7)}-${String(prevEndDay).padStart(2, '0')}`;
  const prevRows = await db
    .select({
      meetings: sql<number>`coalesce(sum(${managerActivity.meetingsHeld}),0)`,
      dials: sql<number>`coalesce(sum(${managerActivity.dialsTotal}),0)`,
      kp: sql<number>`coalesce(sum(${managerActivity.kpSent}),0)`,
      deals: sql<number>`coalesce(sum(${managerActivity.dealsCreatedCount}),0)`,
    })
    .from(managerActivity)
    .where(and(gte(managerActivity.reportDate, prevStart), lte(managerActivity.reportDate, prevEnd)));
  const prev = prevRows[0] ?? { meetings: 0, dials: 0, kp: 0, deals: 0 };
  const deltas = {
    meetings: delta(meetingsHeldTotal, Number(prev.meetings)),
    dials: delta(dialsTotal, Number(prev.dials)),
    kp: delta(kpTotal, Number(prev.kp)),
    deals: delta(dealsCreatedTotal, Number(prev.deals)),
  };

  // Тренд по дням месяца — для спарклайнов.
  const trendRows = await db
    .select({
      date: managerActivity.reportDate,
      meetings: sql<number>`coalesce(sum(${managerActivity.meetingsHeld}),0)`,
      dials: sql<number>`coalesce(sum(${managerActivity.dialsTotal}),0)`,
    })
    .from(managerActivity)
    .where(and(gte(managerActivity.reportDate, start), lte(managerActivity.reportDate, end)))
    .groupBy(managerActivity.reportDate)
    .orderBy(managerActivity.reportDate);
  const trend: TrendPoint[] = trendRows.map((r) => ({
    date: String(r.date),
    meetings: Number(r.meetings),
    dials: Number(r.dials),
  }));

  // План ТМ по встречам из таблицы plans (period 'YYYY-MM', metric 'meetings', глобальный).
  const period = start.slice(0, 7);
  const planRows = await db
    .select({ target: plans.target })
    .from(plans)
    .where(and(eq(plans.period, period), eq(plans.metric, 'meetings')))
    .limit(1);
  const meetingsPlan = planRows[0] ? Number(planRows[0].target) : 20;

  const health = monthHealth(meetingsHeldTotal, meetingsPlan, team.length, stuck.length);

  // Свежесть: когда сформирован отчёт за опорный день.
  const repRows = await db
    .select({ g: reports.generatedAt })
    .from(reports)
    .where(eq(reports.reportDate, snapshotDate))
    .limit(1);
  const generatedAt = repRows[0]?.g ? new Date(repRows[0].g).toISOString() : null;

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
    dialsTotal,
    kpTotal,
    dealsCreatedTotal,
    deltas,
    trend,
    health,
    generatedAt,
  };
}
