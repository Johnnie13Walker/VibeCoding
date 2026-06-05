import 'server-only';

import { and, desc, eq, gte, inArray, lte, sql } from 'drizzle-orm';
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
  dealsCold: number;
  dealsIncoming: number;
  dealsWon: number;
  dealsWonAmount: number;
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
  salesFunnel: SalesFunnel;
  forecast: Forecast;
  meetingQuality: MeetingQuality;
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

const SALES_DEPT_KEYS = ['продаж', 'телемарк', 'роп'];
/** Менеджер из отдела продаж/ТМ по должности (dept = WORK_POSITION). */
export function isSalesDept(dept: string | null | undefined): boolean {
  const d = (dept || '').toLowerCase();
  return SALES_DEPT_KEYS.some((k) => d.includes(k));
}

/** Сотрудник телемаркетинга по должности. */
export function isTelemarketing(dept: string | null | undefined): boolean {
  return (dept || '').toLowerCase().includes('телемаркет');
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

export interface SalesFunnelStep {
  key: string;
  label: string;
  count: number;
  /** Конверсия из предыдущего шага, % (целое). null — для первого шага. */
  convFromPrev: number | null;
  /** Сумма ₽ — только для шага «Оплаты». */
  amount?: number;
}

export interface SalesFunnel {
  /** Шаги потока: сделки → первых встреч → презентаций → КП → оплаты. */
  steps: SalesFunnelStep[];
  dealsCold: number;
  dealsIncoming: number;
  wonAmount: number;
  /** Средний чек оплаченной сделки, ₽ (0 если оплат нет). */
  avgCheck: number;
}

export interface SalesFunnelInput {
  /** Всего создано сделок (deals_created_count) — база воронки и шага «Сделки».
   *  Есть историческая глубина; холод/вход — разрез поверх (новые колонки). */
  dealsTotal: number;
  dealsCold: number;
  dealsIncoming: number;
  firstMeetings: number;
  presentations: number;
  kpSent: number;
  wonCount: number;
  wonAmount: number;
}

/** Воронка-поток вход→оплата за период. Чистая функция — тестируема.
 *  Конверсии не ограничиваем 100%: встречи/КП периода могут опережать сделки
 *  по таймингу (так же как в старом дашборде «Новый даш»: 113%, 156%). */
export function buildSalesFunnel(input: SalesFunnelInput): SalesFunnel {
  const deals = input.dealsTotal;
  const conv = (cur: number, prev: number): number | null =>
    prev > 0 ? Math.round((cur / prev) * 100) : null;

  // Порядок = реальный путь сделки: брифинг → готовят и отправляют КП →
  // защита КП (презентация) → оплата.
  const steps: SalesFunnelStep[] = [
    { key: 'deals', label: 'Сделки', count: deals, convFromPrev: null },
    { key: 'first', label: 'Первых встреч', count: input.firstMeetings, convFromPrev: conv(input.firstMeetings, deals) },
    { key: 'kp', label: 'КП отправлено', count: input.kpSent, convFromPrev: conv(input.kpSent, input.firstMeetings) },
    { key: 'present', label: 'Презентаций', count: input.presentations, convFromPrev: conv(input.presentations, input.kpSent) },
    { key: 'won', label: 'Оплаты', count: input.wonCount, convFromPrev: conv(input.wonCount, input.presentations), amount: input.wonAmount },
  ];

  return {
    steps,
    dealsCold: input.dealsCold,
    dealsIncoming: input.dealsIncoming,
    wonAmount: input.wonAmount,
    avgCheck: input.wonCount > 0 ? Math.round(input.wonAmount / input.wonCount) : 0,
  };
}

// Вероятность закрытия по стадии воронки Продажи — для взвешенного прогноза.
// Эвристика (калибруется по историческому win rate): чем ближе к договору, тем выше.
const STAGE_PROB: Record<string, number> = {
  'C10:NEW': 0.05,
  'C10:PREPAYMENT_INVOIC': 0.08,
  'C10:EXECUTING': 0.15,
  'C10:FINAL_INVOICE': 0.25,
  'C10:UC_KC7195': 0.8,
};

export interface ForecastStage {
  label: string;
  amount: number;
  prob: number;
  weighted: number;
}

export interface Forecast {
  paid: number;
  weighted: number;
  forecastClose: number;
  planRevenue: number;
  pct: number | null;
  byStage: ForecastStage[];
  paceExpected: number;
  pacePct: number | null;
}

/** Прогноз закрытия месяца: оплачено + взвешенная открытая воронка. Чистая функция. */
export function buildForecast(
  funnel: FunnelStage[],
  paid: number,
  planRevenue: number,
  dayOfMonth: number,
  daysInMonth: number,
): Forecast {
  const byStage = funnel
    .map((s) => {
      const prob = STAGE_PROB[s.stage] ?? 0;
      return { label: s.label, amount: s.amount, prob, weighted: Math.round(s.amount * prob) };
    })
    .sort((a, b) => b.weighted - a.weighted);
  const weighted = byStage.reduce((acc, x) => acc + x.weighted, 0);
  const forecastClose = paid + weighted;
  const pct = planRevenue > 0 ? Math.round((forecastClose / planRevenue) * 100) : null;
  const paceExpected = planRevenue > 0 ? Math.round((planRevenue * dayOfMonth) / Math.max(1, daysInMonth)) : 0;
  const pacePct = paceExpected > 0 ? Math.round((paid / paceExpected) * 100) : null;
  return { paid, weighted, forecastClose, planRevenue, pct, byStage, paceExpected, pacePct };
}

export interface ProblemMeeting {
  date: string;
  manager: string;
  score: number | null;
  note: string;
}

export interface MeetingQuality {
  count: number;
  avgScore: number | null;
  pctNextStep: number | null;
  briefingAvg: number | null;
  defenseAvg: number | null;
  problematic: ProblemMeeting[];
}

export interface MeetingQualityInput {
  score: number | null;
  hasNextStep: boolean;
  type: string | null;
  note: string;
  date: string;
  manager: string;
}

/** Качество встреч из LLM-разбора: средний балл, % со след.шагом, балл по типам,
 *  топ проблемных. Чистая функция — тестируема. */
export function buildMeetingQuality(items: MeetingQualityInput[]): MeetingQuality {
  const avg = (arr: number[]): number | null =>
    arr.length ? Math.round((arr.reduce((a, b) => a + b, 0) / arr.length) * 10) / 10 : null;
  const scored = items.filter((i) => typeof i.score === 'number') as (MeetingQualityInput & { score: number })[];
  const pctNextStep = items.length
    ? Math.round((items.filter((i) => i.hasNextStep).length / items.length) * 100)
    : null;
  const problematic = [...scored]
    .sort((a, b) => a.score - b.score)
    .slice(0, 5)
    .map((i) => ({ date: i.date, manager: i.manager, score: i.score, note: i.note }));
  return {
    count: items.length,
    avgScore: avg(scored.map((i) => i.score)),
    pctNextStep,
    briefingAvg: avg(scored.filter((i) => i.type === 'briefing').map((i) => i.score)),
    defenseAvg: avg(scored.filter((i) => i.type === 'defense').map((i) => i.score)),
    problematic,
  };
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

export type Period = 'month' | 'week';

interface Window {
  start: string;
  end: string;
  label: string;
  prevStart: string;
  prevEnd: string;
}

function ddmm(d: Date): string {
  return `${String(d.getUTCDate()).padStart(2, '0')}.${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
}

/** Окно периода + предыдущее окно для Δ. Месяц — календарный; неделя — 7 дней до снимка. */
function computeWindow(snapshotDate: string, range: Period): Window {
  if (range === 'week') {
    const [y, m, d] = snapshotDate.split('-').map(Number);
    const endD = new Date(Date.UTC(y, m - 1, d));
    const startD = new Date(endD);
    startD.setUTCDate(endD.getUTCDate() - 6);
    const pEndD = new Date(startD);
    pEndD.setUTCDate(startD.getUTCDate() - 1);
    const pStartD = new Date(pEndD);
    pStartD.setUTCDate(pEndD.getUTCDate() - 6);
    const iso = (x: Date) => x.toISOString().slice(0, 10);
    return {
      start: iso(startD),
      end: snapshotDate,
      label: `7 дней · ${ddmm(startD)}–${ddmm(endD)}`,
      prevStart: iso(pStartD),
      prevEnd: iso(pEndD),
    };
  }
  const mb = monthBounds(snapshotDate);
  const [py, pm] = mb.start.split('-').map(Number);
  const prevStart = `${pm === 1 ? py - 1 : py}-${String(pm === 1 ? 12 : pm - 1).padStart(2, '0')}-01`;
  const prevEndDay = new Date(Date.UTC(py, pm - 1, 0)).getUTCDate();
  const prevEnd = `${prevStart.slice(0, 7)}-${String(prevEndDay).padStart(2, '0')}`;
  return { ...mb, prevStart, prevEnd };
}

export async function getDashboardData(range: Period = 'month'): Promise<DashboardData> {
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
      salesFunnel: buildSalesFunnel({
        dealsTotal: 0, dealsCold: 0, dealsIncoming: 0, firstMeetings: 0,
        presentations: 0, kpSent: 0, wonCount: 0, wonAmount: 0,
      }),
      forecast: buildForecast([], 0, 0, 1, 30),
      meetingQuality: buildMeetingQuality([]),
      deltas: { meetings: zeroDelta, dials: zeroDelta, kp: zeroDelta, deals: zeroDelta },
      trend: [],
      health: 0,
      generatedAt: null,
    };
  }

  const { start, end, label, prevStart, prevEnd } = computeWindow(snapshotDate, range);

  // Имена/роли сотрудников.
  const userRows = await db
    .select({ id: users.bitrixId, name: users.name, dept: users.dept })
    .from(users);
  const userMap = new Map(userRows.map((u) => [u.id, { name: u.name, dept: u.dept ?? '' }]));

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
      dealsCold: sql<number>`coalesce(sum(${managerActivity.dealsColdCount}),0)`,
      dealsIncoming: sql<number>`coalesce(sum(${managerActivity.dealsIncomingCount}),0)`,
      dealsWon: sql<number>`coalesce(sum(${managerActivity.dealsWonCount}),0)`,
      dealsWonAmount: sql<number>`coalesce(sum(${managerActivity.dealsWonAmount}),0)`,
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
      type: meetings.meetingType,
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

  const teamAll: TeamMember[] = actRows
    .map((r) => ({
      managerId: r.managerId,
      name: userMap.get(r.managerId)?.name ?? `id ${r.managerId}`,
      role: userMap.get(r.managerId)?.dept ?? '',
      meetingsSet: Number(r.meetingsSet),
      meetingsHeld: Number(r.meetingsHeld),
      dials: Number(r.dials),
      calls120: Number(r.calls120),
      kpSent: Number(r.kpSent),
      briefs: Number(r.briefs),
      dealsCreated: Number(r.dealsCreated),
      dealsCold: Number(r.dealsCold),
      dealsIncoming: Number(r.dealsIncoming),
      dealsWon: Number(r.dealsWon),
      dealsWonAmount: Number(r.dealsWonAmount),
      talkHours: Math.round(Number(r.talkSeconds) / 360) / 10,
      trend: trendByMgr.get(r.managerId) ?? [],
      meetings: meetingsByMgr.get(r.managerId) ?? [],
    }))
    .sort((a, b) => b.meetingsHeld - a.meetingsHeld || b.dials - a.dials);

  // Только отдел продаж + телемаркетинг (по должности из dept). Если справочник
  // ещё не наполнен (dept пуст у всех) — показываем всех, чтобы не опустеть.
  const sales = teamAll.filter((m) => isSalesDept(m.role));
  const team: TeamMember[] = sales.length ? sales : teamAll;

  const meetingsHeldTotal = team.reduce((s, x) => s + x.meetingsHeld, 0);
  const dialsTotal = team.reduce((s, x) => s + x.dials, 0);
  const kpTotal = team.reduce((s, x) => s + x.kpSent, 0);
  const dealsCreatedTotal = team.reduce((s, x) => s + x.dealsCreated, 0);

  // Воронка-поток вход→оплата за период (только отдел продаж + ТМ).
  // Первых встреч/презентаций берём по типу из таблицы meetings (брифинг/защита).
  const salesIds = team.map((m) => m.managerId);
  let firstMeetings = 0;
  let presentations = 0;
  if (salesIds.length) {
    const mtRows = await db
      .select({ type: meetings.meetingType, n: sql<number>`count(*)` })
      .from(meetings)
      .where(
        and(
          gte(meetings.reportDate, start),
          lte(meetings.reportDate, end),
          inArray(meetings.managerId, salesIds),
        ),
      )
      .groupBy(meetings.meetingType);
    for (const r of mtRows) {
      if (r.type === 'briefing') firstMeetings = Number(r.n);
      else if (r.type === 'defense') presentations = Number(r.n);
    }
  }
  const salesFunnel = buildSalesFunnel({
    dealsTotal: dealsCreatedTotal,
    dealsCold: team.reduce((s, x) => s + x.dealsCold, 0),
    dealsIncoming: team.reduce((s, x) => s + x.dealsIncoming, 0),
    firstMeetings,
    presentations,
    kpSent: kpTotal,
    wonCount: team.reduce((s, x) => s + x.dealsWon, 0),
    wonAmount: team.reduce((s, x) => s + x.dealsWonAmount, 0),
  });

  // Качество встреч (LLM-разбор) — по разобранным встречам отдела за период.
  const salesIdSet = new Set(salesIds);
  const mqInputs: MeetingQualityInput[] = anRows
    .filter((r) => r.managerId != null && salesIdSet.has(r.managerId))
    .map((r) => {
      const a = (r.analysis ?? {}) as {
        score?: number;
        observations?: { kind?: string; text?: string }[];
        verdict?: string;
        systemic_conclusion?: string;
        next_step?: unknown;
        next_steps?: unknown[];
      };
      const risk = (a.observations ?? []).find((o) => o.kind === 'risk' && o.text);
      const note = (risk?.text || a.verdict || a.systemic_conclusion || '').toString().trim();
      const hasNextStep = a.next_step != null || (Array.isArray(a.next_steps) && a.next_steps.length > 0);
      return {
        score: typeof a.score === 'number' ? a.score : null,
        hasNextStep,
        type: r.type,
        note,
        date: String(r.date),
        manager: userMap.get(r.managerId as number)?.name ?? `id ${r.managerId}`,
      };
    });
  const meetingQuality = buildMeetingQuality(mqInputs);

  // Прогноз закрытия месяца: оплачено + взвешенная воронка; pacing к плану выручки.
  const revPlanRows = await db
    .select({ target: plans.target })
    .from(plans)
    .where(and(eq(plans.period, snapshotDate.slice(0, 7)), eq(plans.metric, 'revenue'), sql`${plans.managerId} is null`))
    .limit(1);
  const planRevenue = revPlanRows[0] ? Number(revPlanRows[0].target) : 0;
  const [fy, fm, fd] = snapshotDate.split('-').map(Number);
  const daysInMonth = new Date(Date.UTC(fy, fm, 0)).getUTCDate();
  const forecast = buildForecast(funnel, salesFunnel.wonAmount, planRevenue, fd, daysInMonth);

  // Δ к предыдущему окну (месяц→прошлый месяц, неделя→прошлая неделя).
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

  // План ТМ по встречам из таблицы plans (period 'YYYY-MM' месяца снимка, не
  // окна — у недели start может быть в прошлом месяце). Для недели — ~1/4 месяца.
  const planPeriod = snapshotDate.slice(0, 7);
  const planRows = await db
    .select({ target: plans.target })
    .from(plans)
    .where(and(eq(plans.period, planPeriod), eq(plans.metric, 'meetings')))
    .limit(1);
  const monthlyPlan = planRows[0] ? Number(planRows[0].target) : 20;
  const meetingsPlan = range === 'week' ? Math.max(1, Math.round(monthlyPlan / 4)) : monthlyPlan;

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
    salesFunnel,
    forecast,
    meetingQuality,
    deltas,
    trend,
    health,
    generatedAt,
  };
}
