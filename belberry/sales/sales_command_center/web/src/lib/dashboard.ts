import 'server-only';

import { and, desc, eq, gte, inArray, lte, sql } from 'drizzle-orm';
import { db } from '@/db';
import { dealRejections, dealsSnapshot, managerAbsences, managerActivity, meetings, payments, plans, reports, users } from '@/db/schema';
import { MEETING_HELD_STAGE } from './telemarketing';
import { buildOperationalMatrix, type OperationalMatrix, type OperDayInput, type OperMemberInput } from './operational';
import { getSalesRejections } from './sales-rejections';
import { emptyBundle, SALES_LOSE_STAGE, SPAM_REASON_10, type SalesRejectionsBundle } from './sales-rejections-shared';

// «Проведено» — событийный слой meetings (status=SUCCESS), а НЕ хранимый агрегат
// manager_activity.meetings_held: до фикса «фильтра отменённых» в collect.py агрегат
// за прошлые дни включал отменённые/перенесённые встречи. Событийный слой
// фильтруется запросом и историчен — единый источник правды с ТМ-дашбордом.
// Возвращает [(managerId, date, n)] — число состоявшихся встреч по ответственному и дню.
async function fetchHeldRows(from: string, to: string, managerIds?: number[]) {
  const conds = [
    eq(meetings.status, MEETING_HELD_STAGE),
    gte(meetings.reportDate, from),
    lte(meetings.reportDate, to),
  ];
  if (managerIds && managerIds.length) conds.push(inArray(meetings.managerId, managerIds));
  const rows = await db
    .select({ managerId: meetings.managerId, date: meetings.reportDate, n: sql<number>`count(*)` })
    .from(meetings)
    .where(and(...conds))
    .groupBy(meetings.managerId, meetings.reportDate);
  return rows.map((r) => ({ managerId: r.managerId, date: String(r.date), n: Number(r.n) }));
}

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
  calls60: number;
  calls120: number;
  kpSent: number;
  briefs: number;
  dealsCreated: number;
  dealsCold: number;
  dealsIncoming: number;
  dealsWon: number;
  dealsWonAmount: number;
  messenger: number;
  emails: number;
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
  /** Сумма оплат за текущий месяц (Приходы 2026, КД без НДС). */
  paymentsTotal: number;
  /** Количество отказов воронки Продажи (C10:LOSE, без СПАМ) за период. */
  rejectionsCount: number;
  /** Количество брифов за период (manager_activity.briefs_created). */
  briefsTotal: number;
  salesFunnel: SalesFunnel;
  forecast: Forecast;
  meetingQuality: MeetingQuality;
  operational: OperationalMatrix;
  managerConversions: { managers: ManagerConversion[]; total: ManagerConversion };
  managerPipeline: ManagerPipeline;
  tmActivity: TmActivity;
  messaging: Messaging;
  velocity: Velocity;
  monthly: MonthRow[];
  day2day: Day2Day;
  planFact: PlanFact;
  salesRejections: SalesRejectionsBundle;
  deltas: {
    meetings: KpiDelta; dials: KpiDelta; kp: KpiDelta; deals: KpiDelta;
    payments: KpiDelta; rejections: KpiDelta; briefs: KpiDelta;
  };
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

/** Менеджер по продажам (МОП) — несёт план оплат. Исключает РОП и телемаркетинг. */
export function isSalesManager(dept: string | null | undefined): boolean {
  return (dept || '').toLowerCase().includes('менеджер по прода');
}

/**
 * План оплат по стажу (политика для новичков): 1-й месяц работы — 0, 2-й — 300 000,
 * 3-й и далее — 500 000. Стаж в КАЛЕНДАРНЫХ месяцах: месяц найма = 1-й месяц.
 * hiredAt — 'YYYY-MM-DD' или null (нет даты → считаем опытным, 500к). period — 'YYYY-MM'.
 */
export function rampRevenuePlan(hiredAt: string | null, period: string): number {
  if (!hiredAt) return 500_000;
  const [hy, hm] = hiredAt.slice(0, 7).split('-').map(Number);
  const [py, pm] = period.split('-').map(Number);
  if (!hy || !hm || !py || !pm) return 500_000;
  const monthsWorked = (py * 12 + pm) - (hy * 12 + hm) + 1;
  if (monthsWorked <= 1) return 0;
  if (monthsWorked === 2) return 300_000;
  return 500_000;
}

/** Норматив брифов на МОП — всегда 20 (если в plans не задано иное). */
export const DEFAULT_BRIEFS_PLAN = 20;

/**
 * Посев ростера: активные сотрудники ОП/ТМ из справочника, у кого ещё НЕТ активности
 * в периоде, добавляются в команду с нулями — чтобы новичок появлялся на дашборде
 * сразу с момента, как его завели в Bitrix с нужной должностью, а не только после
 * первого звонка/встречи. activeIds — id, у кого активность уже есть (их не дублируем).
 */
export function rosterZeroMembers(
  dirUsers: { id: number; name: string; dept: string | null; isActive: boolean }[],
  activeIds: Set<number>,
): TeamMember[] {
  return dirUsers
    .filter((u) => u.isActive && isSalesDept(u.dept) && !activeIds.has(u.id))
    .map((u) => ({
      managerId: u.id,
      name: u.name,
      role: u.dept ?? '',
      meetingsSet: 0, meetingsHeld: 0, dials: 0, calls60: 0, calls120: 0,
      kpSent: 0, briefs: 0, dealsCreated: 0, dealsCold: 0, dealsIncoming: 0,
      dealsWon: 0, dealsWonAmount: 0, messenger: 0, emails: 0, talkHours: 0,
      trend: [], meetings: [],
    }));
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
  order: number;
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
      return { label: s.label, order: s.order, amount: s.amount, prob, weighted: Math.round(s.amount * prob) };
    })
    // Порядок воронки: по стадиям (ранние сверху → договор снизу).
    .sort((a, b) => a.order - b.order);
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

export interface ManagerConversion {
  managerId: number;
  name: string;
  deals: number;
  first: number;
  defense: number;
  won: number;
  dealToMeeting: number | null;
  meetingToDefense: number | null;
  defenseToWon: number | null;
  dealToWon: number | null;
}

export interface ManagerConversionInput {
  managerId: number;
  name: string;
  deals: number;
  first: number;
  defense: number;
  won: number;
}

const convPct = (a: number, b: number): number | null => (b > 0 ? Math.round((a / b) * 100) : null);

/** Конверсии воронки в разрезе менеджера + итоговая строка «Общая ОП». Чистая функция. */
export function buildManagerConversions(
  items: ManagerConversionInput[],
): { managers: ManagerConversion[]; total: ManagerConversion } {
  const enrich = (m: ManagerConversionInput): ManagerConversion => ({
    ...m,
    dealToMeeting: convPct(m.first, m.deals),
    meetingToDefense: convPct(m.defense, m.first),
    defenseToWon: convPct(m.won, m.defense),
    dealToWon: convPct(m.won, m.deals),
  });
  const sum = (key: 'deals' | 'first' | 'defense' | 'won') => items.reduce((a, m) => a + m[key], 0);
  const total = enrich({
    managerId: 0,
    name: 'Общая ОП',
    deals: sum('deals'),
    first: sum('first'),
    defense: sum('defense'),
    won: sum('won'),
  });
  return { managers: items.map(enrich), total };
}

export interface ManagerPipelineRow {
  managerId: number;
  name: string;
  counts: Record<string, number>;
  total: number;
  amount: number;
  /** Δ открытых сделок к началу месяца (рост/падение). */
  delta: number;
}

export interface ManagerPipeline {
  stages: { stage: string; label: string }[];
  rows: ManagerPipelineRow[];
  stageAmount: Record<string, number>;
  stageTotal: Record<string, number>;
  grandTotal: number;
  grandAmount: number;
}

/** Матрица «менеджер × стадия» по текущему снимку + Δ к началу месяца. Чистая функция. */
export function buildManagerPipeline(
  cells: { managerId: number; name: string; stage: string; count: number; amount: number }[],
  startTotalByMgr: Record<number, number>,
): ManagerPipeline {
  const stages = Object.entries(STAGE_META)
    .sort((a, b) => a[1].order - b[1].order)
    .map(([stage, m]) => ({ stage, label: m.label }));
  const byMgr = new Map<number, ManagerPipelineRow>();
  const stageAmount: Record<string, number> = {};
  const stageTotal: Record<string, number> = {};
  for (const c of cells) {
    if (!STAGE_META[c.stage]) continue;
    let row = byMgr.get(c.managerId);
    if (!row) {
      row = { managerId: c.managerId, name: c.name, counts: {}, total: 0, amount: 0, delta: 0 };
      byMgr.set(c.managerId, row);
    }
    row.counts[c.stage] = (row.counts[c.stage] ?? 0) + c.count;
    row.total += c.count;
    row.amount += c.amount;
    stageAmount[c.stage] = (stageAmount[c.stage] ?? 0) + c.amount;
    stageTotal[c.stage] = (stageTotal[c.stage] ?? 0) + c.count;
  }
  const rows = [...byMgr.values()]
    .map((r) => ({ ...r, delta: r.total - (startTotalByMgr[r.managerId] ?? 0) }))
    .sort((a, b) => b.amount - a.amount);
  return {
    stages,
    rows,
    stageAmount,
    stageTotal,
    grandTotal: rows.reduce((a, r) => a + r.total, 0),
    grandAmount: rows.reduce((a, r) => a + r.amount, 0),
  };
}

export interface TmRow {
  managerId: number;
  name: string;
  dials: number;
  calls60: number;
  meetingsSet: number;
  /** Конверсия наборов во встречу, % (с десятыми). */
  convToMeeting: number | null;
}

export interface TmActivity {
  zvonari: number;
  dials: number;
  calls60: number;
  calls120: number;
  talkHours: number;
  meetingsSet: number;
  dialsPerZvonar: number;
  calls60PerZvonar: number;
  dialsPerDay: number;
  calls60PerDay: number;
  rows: TmRow[];
}

export interface TmActivityInput {
  managerId: number;
  name: string;
  dials: number;
  calls60: number;
  calls120: number;
  meetingsSet: number;
  talkHours: number;
}

/** Активность телемаркетинга: дозвоны/наборы, на 1 звонаря, в день; по звонарям. Чистая функция. */
export function buildTmActivity(members: TmActivityInput[], workingDays: number): TmActivity {
  const z = Math.max(1, members.length);
  const wd = Math.max(1, workingDays);
  const sum = (k: 'dials' | 'calls60' | 'calls120' | 'meetingsSet') =>
    members.reduce((a, m) => a + m[k], 0);
  const dials = sum('dials');
  const calls60 = sum('calls60');
  const calls120 = sum('calls120');
  const meetingsSet = sum('meetingsSet');
  const talkHours = Math.round(members.reduce((a, m) => a + m.talkHours, 0) * 10) / 10;
  return {
    zvonari: members.length,
    dials,
    calls60,
    calls120,
    talkHours,
    meetingsSet,
    dialsPerZvonar: Math.round(dials / z),
    calls60PerZvonar: Math.round(calls60 / z),
    dialsPerDay: Math.round(dials / wd),
    calls60PerDay: Math.round(calls60 / wd),
    rows: members
      .map((m) => ({
        managerId: m.managerId,
        name: m.name,
        dials: m.dials,
        calls60: m.calls60,
        meetingsSet: m.meetingsSet,
        convToMeeting: m.dials > 0 ? Math.round((m.meetingsSet / m.dials) * 1000) / 10 : null,
      }))
      .sort((a, b) => b.dials - a.dials),
  };
}

export interface MessagingRow {
  managerId: number;
  name: string;
  messenger: number;
  emails: number;
}

export interface Messaging {
  messengerTotal: number;
  emailTotal: number;
  rows: MessagingRow[];
}

/** Мессенджеры и почта по менеджерам. Чистая функция. */
export function buildMessaging(members: MessagingRow[]): Messaging {
  const rows = members
    .filter((r) => r.messenger > 0 || r.emails > 0)
    .sort((a, b) => b.messenger - a.messenger || b.emails - a.emails);
  return {
    messengerTotal: rows.reduce((a, r) => a + r.messenger, 0),
    emailTotal: rows.reduce((a, r) => a + r.emails, 0),
    rows,
  };
}

export interface VelocityStage {
  stage: string;
  label: string;
  avgDays: number;
  count: number;
}

export interface AgingBucket {
  key: string;
  label: string;
  amount: number;
  count: number;
}

export interface Velocity {
  stages: VelocityStage[];
  aging: AgingBucket[];
  /** Грубая оценка цикла = сумма среднего времени на стадиях, дней. */
  estimatedCycleDays: number;
  /** Сумма ₽ в сделках старше 30 дней (зона риска). */
  agingRiskAmount: number;
}

const AGING_BUCKETS: { key: string; label: string; min: number; max: number }[] = [
  { key: '0-7', label: 'до 7 дней', min: 0, max: 7 },
  { key: '7-14', label: '7–14 дней', min: 7, max: 14 },
  { key: '14-30', label: '14–30 дней', min: 14, max: 30 },
  { key: '30+', label: 'больше 30', min: 30, max: Infinity },
];

/** Скорость воронки (среднее время на стадии) и деньги по возрасту. Чистая функция. */
export function buildVelocity(deals: { stage: string; ageDays: number; amount: number }[]): Velocity {
  const stageAcc = new Map<string, { sum: number; count: number }>();
  const agingAcc = new Map<string, { amount: number; count: number }>();
  for (const d of deals) {
    if (STAGE_META[d.stage]) {
      const a = stageAcc.get(d.stage) ?? { sum: 0, count: 0 };
      a.sum += d.ageDays;
      a.count += 1;
      stageAcc.set(d.stage, a);
    }
    const bucket = AGING_BUCKETS.find((b) => d.ageDays >= b.min && d.ageDays < b.max) ?? AGING_BUCKETS[0];
    const ag = agingAcc.get(bucket.key) ?? { amount: 0, count: 0 };
    ag.amount += d.amount;
    ag.count += 1;
    agingAcc.set(bucket.key, ag);
  }
  const stages = Object.entries(STAGE_META)
    .sort((a, b) => a[1].order - b[1].order)
    .map(([stage, m]) => {
      const a = stageAcc.get(stage);
      return { stage, label: m.label, avgDays: a ? Math.round(a.sum / a.count) : 0, count: a?.count ?? 0 };
    });
  const aging = AGING_BUCKETS.map((b) => {
    const ag = agingAcc.get(b.key);
    return { key: b.key, label: b.label, amount: ag?.amount ?? 0, count: ag?.count ?? 0 };
  });
  return {
    stages,
    aging,
    estimatedCycleDays: stages.reduce((acc, s) => acc + s.avgDays, 0),
    agingRiskAmount: agingAcc.get('30+')?.amount ?? 0,
  };
}

export interface MonthRow {
  ym: string;
  label: string;
  first: number;
  defense: number;
  kp: number;
  deals: number;
  wonCount: number;
  wonAmount: number;
}

/** Помесячная динамика KPI отдела. Чистая функция. */
export function buildMonthlyDynamics(
  months: { ym: string; label: string }[],
  activity: Record<string, { kp: number; deals: number; wonCount: number; wonAmount: number }>,
  meetings: Record<string, { first: number; defense: number }>,
): MonthRow[] {
  return months.map((m) => ({
    ym: m.ym,
    label: m.label,
    first: meetings[m.ym]?.first ?? 0,
    defense: meetings[m.ym]?.defense ?? 0,
    kp: activity[m.ym]?.kp ?? 0,
    deals: activity[m.ym]?.deals ?? 0,
    wonCount: activity[m.ym]?.wonCount ?? 0,
    wonAmount: activity[m.ym]?.wonAmount ?? 0,
  }));
}

export interface Day2DayRow {
  date: string;
  deals: number;
  meetings: number;
  kp: number;
  dials: number;
}

export interface Day2Day {
  rows: Day2DayRow[];
  total: { deals: number; meetings: number; kp: number; dials: number };
}

/** Day2Day — дневные итоги отдела за месяц + строка «Итого». Чистая функция. */
export function buildDay2Day(rows: Day2DayRow[]): Day2Day {
  const total = rows.reduce(
    (a, r) => ({ deals: a.deals + r.deals, meetings: a.meetings + r.meetings, kp: a.kp + r.kp, dials: a.dials + r.dials }),
    { deals: 0, meetings: 0, kp: 0, dials: 0 },
  );
  return { rows, total };
}

export interface PlanFactManager {
  managerId: number;
  name: string;
  revenueFact: number;
  revenuePlan: number;
  briefsFact: number;
  briefsPlan: number;
}

export interface PlanFact {
  /** Оплаты: командный план на отдел + факт команды. */
  revenueTeamFact: number;
  revenueTeamPlan: number;
  /** Индивидуальные планы оплат + брифы по МОП. */
  managers: PlanFactManager[];
  briefsTeamFact: number;
  briefsTeamPlan: number;
}

export interface PlanFactInput {
  revenueTeamFact: number;
  revenueTeamPlan: number;
  /** Норматив брифов на одного МОП. */
  briefsPlanPerMop: number;
  /** Менеджеры с индивидуальным планом оплат (Деговцова, Семенихин). */
  managers: { managerId: number; name: string; revenueFact: number; revenuePlan: number; briefsFact: number }[];
}

/** План/факт месяца: командные оплаты + индивидуальные планы (оплаты/брифы). Чистая. */
export function buildPlanFact(i: PlanFactInput): PlanFact {
  const managers: PlanFactManager[] = i.managers.map((m) => ({
    managerId: m.managerId,
    name: m.name,
    revenueFact: m.revenueFact,
    revenuePlan: m.revenuePlan,
    briefsFact: m.briefsFact,
    briefsPlan: i.briefsPlanPerMop,
  }));
  return {
    revenueTeamFact: i.revenueTeamFact,
    revenueTeamPlan: i.revenueTeamPlan,
    managers,
    briefsTeamFact: managers.reduce((a, m) => a + m.briefsFact, 0),
    briefsTeamPlan: i.briefsPlanPerMop * managers.length,
  };
}

/** Число рабочих дней (пн-пт) в диапазоне [start, end] включительно. */
function countWeekdays(start: string, end: string): number {
  const cur = new Date(`${start}T00:00:00Z`);
  const e = new Date(`${end}T00:00:00Z`);
  let n = 0;
  while (cur <= e) {
    const d = cur.getUTCDay();
    if (d >= 1 && d <= 5) n += 1;
    cur.setUTCDate(cur.getUTCDate() + 1);
  }
  return n;
}

/** Список рабочих дней (пн–пт) окна включительно — колонки матрицы «Опер». */
function weekdayRange(start: string, end: string): string[] {
  const out: string[] = [];
  if (start > end) return out;
  const cur = new Date(`${start}T00:00:00Z`);
  const e = new Date(`${end}T00:00:00Z`);
  while (cur <= e) {
    const d = cur.getUTCDay();
    if (d >= 1 && d <= 5) out.push(cur.toISOString().slice(0, 10));
    cur.setUTCDate(cur.getUTCDate() + 1);
  }
  return out;
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
export function computeWindow(snapshotDate: string, range: Period): Window {
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
  // Δ — к аналогичному периоду прошлого месяца ПО КАЛЕНДАРНЫМ ДНЯМ: текущий месяц
  // неполный (1..N до снимка), поэтому прошлый тоже обрезаем по дню снимка N, а не
  // берём полный месяц (иначе MTD всегда «проваливается» −70% просто из-за неполноты).
  const snapDay = Number(snapshotDate.slice(8, 10));
  const prevMonthLastDay = new Date(Date.UTC(py, pm - 1, 0)).getUTCDate();
  const prevDay = Math.min(snapDay, prevMonthLastDay);
  const prevEnd = `${prevStart.slice(0, 7)}-${String(prevDay).padStart(2, '0')}`;
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
      paymentsTotal: 0,
      rejectionsCount: 0,
      briefsTotal: 0,
      salesFunnel: buildSalesFunnel({
        dealsTotal: 0, dealsCold: 0, dealsIncoming: 0, firstMeetings: 0,
        presentations: 0, kpSent: 0, wonCount: 0, wonAmount: 0,
      }),
      forecast: buildForecast([], 0, 0, 1, 30),
      meetingQuality: buildMeetingQuality([]),
      operational: buildOperationalMatrix([], []),
      managerConversions: buildManagerConversions([]),
      managerPipeline: buildManagerPipeline([], {}),
      tmActivity: buildTmActivity([], 1),
      messaging: buildMessaging([]),
      velocity: buildVelocity([]),
      monthly: [],
      day2day: buildDay2Day([]),
      planFact: buildPlanFact({
        revenueTeamFact: 0, revenueTeamPlan: 0, briefsPlanPerMop: 0, managers: [],
      }),
      salesRejections: emptyBundle('—'),
      deltas: { meetings: zeroDelta, dials: zeroDelta, kp: zeroDelta, deals: zeroDelta, payments: zeroDelta, rejections: zeroDelta, briefs: zeroDelta },
      trend: [],
      health: 0,
      generatedAt: null,
    };
  }

  const { start, end, label, prevStart, prevEnd } = computeWindow(snapshotDate, range);

  // Имена/роли сотрудников.
  const userRows = await db
    .select({ id: users.bitrixId, name: users.name, dept: users.dept, isActive: users.isActive, hiredAt: users.hiredAt })
    .from(users);
  const userMap = new Map(userRows.map((u) => [u.id, { name: u.name, dept: u.dept ?? '', active: u.isActive }]));
  const hiredByMgr = new Map(userRows.map((u) => [u.id, u.hiredAt ?? null]));

  // Воронка — открытые сделки кат.10 на последнем снимке.
  const snapRows = await db
    .select({
      dealId: dealsSnapshot.dealId,
      stage: dealsSnapshot.stage,
      opportunity: dealsSnapshot.opportunity,
      stuckDays: dealsSnapshot.stuckDays,
      stageEntered: dealsSnapshot.stageEntered,
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
      dials: sql<number>`coalesce(sum(${managerActivity.dialsTotal}),0)`,
      calls60: sql<number>`coalesce(sum(${managerActivity.calls60sPlus}),0)`,
      calls120: sql<number>`coalesce(sum(${managerActivity.calls120sPlus}),0)`,
      messenger: sql<number>`coalesce(sum(${managerActivity.messengerDialogs}),0)`,
      emails: sql<number>`coalesce(sum(${managerActivity.emailsSent}),0)`,
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

  // Событийный слой «проведено» за окно: по менеджеру, по (менеджер,день) и по дню.
  // Переопределяет агрегат meetings_held (см. fetchHeldRows) для команды, спарклайнов
  // и итогов — чтобы отменённые встречи не попадали в «проведено» за прошлые дни.
  const heldByMgr = new Map<number, number>();
  const heldByMgrDate = new Map<number, Map<string, number>>();
  const heldByDate = new Map<string, number>();
  for (const r of await fetchHeldRows(start, end)) {
    if (r.managerId == null) continue;
    heldByMgr.set(r.managerId, (heldByMgr.get(r.managerId) ?? 0) + r.n);
    const md = heldByMgrDate.get(r.managerId) ?? new Map<string, number>();
    md.set(r.date, (md.get(r.date) ?? 0) + r.n);
    heldByMgrDate.set(r.managerId, md);
    heldByDate.set(r.date, (heldByDate.get(r.date) ?? 0) + r.n);
  }

  // Дрилл-даун: тренд встреч по дням на менеджера. Скелет дней — из активности
  // (включая нулевые дни), значение «проведено» — из событийного слоя.
  const trendByMgrRows = await db
    .select({
      managerId: managerActivity.managerId,
      date: managerActivity.reportDate,
    })
    .from(managerActivity)
    .where(and(gte(managerActivity.reportDate, start), lte(managerActivity.reportDate, end)))
    .groupBy(managerActivity.managerId, managerActivity.reportDate)
    .orderBy(managerActivity.reportDate);
  const trendByMgr = new Map<number, number[]>();
  for (const r of trendByMgrRows) {
    const arr = trendByMgr.get(r.managerId) ?? [];
    arr.push(heldByMgrDate.get(r.managerId)?.get(String(r.date)) ?? 0);
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

  const activityMembers: TeamMember[] = actRows
    .map((r) => ({
      managerId: r.managerId,
      name: userMap.get(r.managerId)?.name ?? `id ${r.managerId}`,
      role: userMap.get(r.managerId)?.dept ?? '',
      meetingsSet: Number(r.meetingsSet),
      meetingsHeld: heldByMgr.get(r.managerId) ?? 0,
      dials: Number(r.dials),
      calls60: Number(r.calls60),
      calls120: Number(r.calls120),
      kpSent: Number(r.kpSent),
      briefs: Number(r.briefs),
      dealsCreated: Number(r.dealsCreated),
      dealsCold: Number(r.dealsCold),
      dealsIncoming: Number(r.dealsIncoming),
      dealsWon: Number(r.dealsWon),
      dealsWonAmount: Number(r.dealsWonAmount),
      messenger: Number(r.messenger),
      emails: Number(r.emails),
      talkHours: Math.round(Number(r.talkSeconds) / 360) / 10,
      trend: trendByMgr.get(r.managerId) ?? [],
      meetings: meetingsByMgr.get(r.managerId) ?? [],
    }));

  // Посев ростера: активные ОП/ТМ из справочника без активности в периоде —
  // с нулями, чтобы новички были видны сразу (а не только после первого действия).
  const roster = rosterZeroMembers(userRows, new Set(actRows.map((r) => r.managerId)));
  const teamAll: TeamMember[] = [...activityMembers, ...roster].sort(
    (a, b) => b.meetingsHeld - a.meetingsHeld || b.dials - a.dials,
  );

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

  // Встречи по типам в разрезе менеджера — для конверсий по менеджерам.
  const firstByMgr = new Map<number, number>();
  const defenseByMgr = new Map<number, number>();
  if (salesIds.length) {
    const mtMgrRows = await db
      .select({ managerId: meetings.managerId, type: meetings.meetingType, n: sql<number>`count(*)` })
      .from(meetings)
      .where(and(gte(meetings.reportDate, start), lte(meetings.reportDate, end), inArray(meetings.managerId, salesIds)))
      .groupBy(meetings.managerId, meetings.meetingType);
    for (const r of mtMgrRows) {
      if (r.managerId == null) continue;
      if (r.type === 'briefing') firstByMgr.set(r.managerId, Number(r.n));
      else if (r.type === 'defense') defenseByMgr.set(r.managerId, Number(r.n));
    }
  }
  const managerConversions = buildManagerConversions(
    team
      .map((m) => ({
        managerId: m.managerId,
        name: m.name,
        deals: m.dealsCreated,
        first: firstByMgr.get(m.managerId) ?? 0,
        defense: defenseByMgr.get(m.managerId) ?? 0,
        won: m.dealsWon,
      }))
      .filter((m) => m.deals > 0 || m.first > 0 || m.defense > 0 || m.won > 0),
  );

  // Воронка по менеджерам: текущий снимок (cat10 открытые) + Δ к началу месяца.
  const monthStartDay = `${snapshotDate.slice(0, 7)}-01`;
  const startDateRows = await db
    .select({ d: sql<string>`min(${dealsSnapshot.reportDate})` })
    .from(dealsSnapshot)
    .where(gte(dealsSnapshot.reportDate, monthStartDay));
  const monthStartDate = startDateRows[0]?.d ?? snapshotDate;
  const startTotalRows = await db
    .select({ managerId: dealsSnapshot.managerId, n: sql<number>`count(*)` })
    .from(dealsSnapshot)
    .where(and(eq(dealsSnapshot.reportDate, monthStartDate), eq(dealsSnapshot.categoryId, 10)))
    .groupBy(dealsSnapshot.managerId);
  const startTotalByMgr: Record<number, number> = {};
  for (const r of startTotalRows) if (r.managerId != null) startTotalByMgr[r.managerId] = Number(r.n);

  const pipelineCellsAll = snapRows
    .filter((r) => r.managerId != null && STAGE_META[r.stage])
    .map((r) => ({
      managerId: r.managerId as number,
      name: userMap.get(r.managerId as number)?.name ?? `id ${r.managerId}`,
      stage: r.stage,
      count: 1,
      amount: Number(r.opportunity ?? 0),
      dept: userMap.get(r.managerId as number)?.dept ?? '',
    }));
  const pipelineSales = pipelineCellsAll.filter((c) => isSalesDept(c.dept));
  const managerPipeline = buildManagerPipeline(
    pipelineSales.length ? pipelineSales : pipelineCellsAll,
    startTotalByMgr,
  );

  // Активность ТМ (звонки) и мессенджеры/почта.
  const tmActivity = buildTmActivity(
    team
      .filter((m) => isTelemarketing(m.role))
      .map((m) => ({
        managerId: m.managerId,
        name: m.name,
        dials: m.dials,
        calls60: m.calls60,
        calls120: m.calls120,
        meetingsSet: m.meetingsSet,
        talkHours: m.talkHours,
      })),
    countWeekdays(start, end),
  );
  const messaging = buildMessaging(
    team.map((m) => ({ managerId: m.managerId, name: m.name, messenger: m.messenger, emails: m.emails })),
  );

  // Скорость воронки и деньги по возрасту — по текущему снимку открытых сделок.
  const snapMs = Date.parse(`${snapshotDate}T00:00:00Z`);
  const velocity = buildVelocity(
    snapRows
      .filter((r) => STAGE_META[r.stage])
      .map((r) => ({
        stage: r.stage,
        ageDays: r.stageEntered
          ? Math.max(0, Math.round((snapMs - Date.parse(`${r.stageEntered}T00:00:00Z`)) / 86_400_000))
          : 0,
        amount: Number(r.opportunity ?? 0),
      })),
  );

  // Помесячная динамика — последние 6 месяцев (по отделу продаж).
  const dynMonths: { ym: string; label: string }[] = [];
  {
    const [cy, cm] = snapshotDate.split('-').map(Number);
    for (let i = 5; i >= 0; i--) {
      let mm = cm - i;
      let yy = cy;
      while (mm <= 0) {
        mm += 12;
        yy -= 1;
      }
      dynMonths.push({ ym: `${yy}-${String(mm).padStart(2, '0')}`, label: MONTHS_RU[mm - 1] });
    }
  }
  const dynStart = `${dynMonths[0].ym}-01`;
  const ymActExpr = sql<string>`to_char(${managerActivity.reportDate}, 'YYYY-MM')`;
  // Помесячная динамика — историческая: по ВСЕМ сотрудникам (вкл. уволенных, кто
  // работал тогда). НЕ фильтруем по текущему составу salesIds — иначе работа
  // уволенных выпадает из прошлых месяцев и цифры занижаются.
  const dynActRows = await db
    .select({
      ym: ymActExpr,
      kp: sql<number>`coalesce(sum(${managerActivity.kpSent}),0)`,
      deals: sql<number>`coalesce(sum(${managerActivity.dealsCreatedCount}),0)`,
      wonCount: sql<number>`coalesce(sum(${managerActivity.dealsWonCount}),0)`,
      wonAmount: sql<number>`coalesce(sum(${managerActivity.dealsWonAmount}),0)`,
    })
    .from(managerActivity)
    .where(gte(managerActivity.reportDate, dynStart))
    .groupBy(ymActExpr);
  const dynActivity: Record<string, { kp: number; deals: number; wonCount: number; wonAmount: number }> = {};
  for (const r of dynActRows)
    dynActivity[r.ym] = { kp: Number(r.kp), deals: Number(r.deals), wonCount: Number(r.wonCount), wonAmount: Number(r.wonAmount) };

  // «Оплаты» — фактические приходы из финансовой таблицы «Приходы 2026» (вкладка
  // «Продажи», КД без НДС, Отдел=Продажи), а НЕ Bitrix-won. Источник правды по деньгам.
  const payRows = await db
    .select({
      y: payments.payYear,
      m: payments.payMonth,
      n: sql<number>`count(*)`,
      amt: sql<number>`coalesce(sum(${payments.kdNoVat}),0)`,
    })
    .from(payments)
    .where(eq(payments.dept, 'Продажи'))
    .groupBy(payments.payYear, payments.payMonth);
  const payByYm = new Map<string, { n: number; amt: number }>();
  for (const r of payRows) {
    if (r.y == null || r.m == null) continue;
    payByYm.set(`${r.y}-${String(r.m).padStart(2, '0')}`, { n: Number(r.n), amt: Number(r.amt) });
  }
  for (const mo of dynMonths) {
    const e = dynActivity[mo.ym] ?? { kp: 0, deals: 0, wonCount: 0, wonAmount: 0 };
    const p = payByYm.get(mo.ym);
    e.wonCount = p?.n ?? 0;
    e.wonAmount = p?.amt ?? 0;
    dynActivity[mo.ym] = e;
  }

  const ymMeetExpr = sql<string>`to_char(${meetings.reportDate}, 'YYYY-MM')`;
  // Тоже историческая — по всем встречам, без фильтра текущего состава.
  const dynMeetRows = await db
    .select({ ym: ymMeetExpr, type: meetings.meetingType, n: sql<number>`count(*)` })
    .from(meetings)
    .where(gte(meetings.reportDate, dynStart))
    .groupBy(ymMeetExpr, meetings.meetingType);
  const dynMeetings: Record<string, { first: number; defense: number }> = {};
  for (const r of dynMeetRows) {
    const e = dynMeetings[r.ym] ?? { first: 0, defense: 0 };
    if (r.type === 'briefing') e.first = Number(r.n);
    else if (r.type === 'defense') e.defense = Number(r.n);
    dynMeetings[r.ym] = e;
  }
  const monthly = buildMonthlyDynamics(dynMonths, dynActivity, dynMeetings);

  // Day2Day — дневные итоги отдела за текущий месяц.
  const d2dConds = [gte(managerActivity.reportDate, monthStartDay), lte(managerActivity.reportDate, snapshotDate)];
  if (salesIds.length) d2dConds.push(inArray(managerActivity.managerId, salesIds));
  const d2dRows = await db
    .select({
      date: managerActivity.reportDate,
      deals: sql<number>`coalesce(sum(${managerActivity.dealsCreatedCount}),0)`,
      kp: sql<number>`coalesce(sum(${managerActivity.kpSent}),0)`,
      dials: sql<number>`coalesce(sum(${managerActivity.dialsTotal}),0)`,
    })
    .from(managerActivity)
    .where(and(...d2dConds))
    .groupBy(managerActivity.reportDate)
    .orderBy(managerActivity.reportDate);
  // «Проведено» по дням — из событийного слоя (то же окно и sales-фильтр, что d2d).
  const heldByDateD2d = new Map<string, number>();
  for (const r of await fetchHeldRows(monthStartDay, snapshotDate, salesIds.length ? salesIds : undefined)) {
    heldByDateD2d.set(r.date, (heldByDateD2d.get(r.date) ?? 0) + r.n);
  }
  const day2day = buildDay2Day(
    d2dRows.map((r) => ({
      date: String(r.date),
      deals: Number(r.deals),
      meetings: heldByDateD2d.get(String(r.date)) ?? 0,
      kp: Number(r.kp),
      dials: Number(r.dials),
    })),
  );

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

  // Планы месяца: общие (manager_id IS NULL) — revenue (командный на отдел),
  // briefs (норматив на МОП); индивидуальные (manager_id NOT NULL) — revenue по МОП.
  const period = snapshotDate.slice(0, 7);
  const allPlanRows = await db
    .select({ managerId: plans.managerId, metric: plans.metric, target: plans.target })
    .from(plans)
    .where(eq(plans.period, period));
  const planMap: Record<string, number> = {};
  const indivRevenuePlan = new Map<number, number>();
  for (const r of allPlanRows) {
    if (r.managerId == null) planMap[r.metric] = Number(r.target);
    else if (r.metric === 'revenue') indivRevenuePlan.set(r.managerId, Number(r.target));
  }
  const planRevenue = planMap['revenue'] ?? 0;
  const [fy, fm, fd] = snapshotDate.split('-').map(Number);
  const daysInMonth = new Date(Date.UTC(fy, fm, 0)).getUTCDate();
  const forecast = buildForecast(funnel, salesFunnel.wonAmount, planRevenue, fd, daysInMonth);

  // План/факт по МОП: все менеджеры по продажам из команды (вкл. новичков-нулёвок) +
  // любой, у кого есть персональный план. План оплат = явный план из plans, иначе по
  // стажу (новичкам: 1-й мес 0 / 2-й 300к / 3-й+ 500к). Факт оплат/брифов — из team.
  // План/факт — только ДЕЙСТВУЮЩИЕ МОП (уволенным план/брифы не ставим, даже если была
  // активность в начале месяца). Историю периода уволенные видят в других блоках.
  const pfManagers = team
    .filter((m) => (userMap.get(m.managerId)?.active ?? true) && (isSalesManager(m.role) || indivRevenuePlan.has(m.managerId)))
    .map((m) => ({
      managerId: m.managerId,
      name: m.name,
      revenueFact: m.dealsWonAmount,
      revenuePlan: indivRevenuePlan.get(m.managerId) ?? rampRevenuePlan(hiredByMgr.get(m.managerId) ?? null, period),
      briefsFact: m.briefs,
    }))
    .sort((a, b) => b.revenuePlan - a.revenuePlan || a.name.localeCompare(b.name, 'ru'));

  const planFact = buildPlanFact({
    revenueTeamFact: salesFunnel.wonAmount,
    revenueTeamPlan: planRevenue,
    briefsPlanPerMop: planMap['briefs'] || DEFAULT_BRIEFS_PLAN,
    managers: pfManagers,
  });

  // Δ к предыдущему окну (месяц→прошлый месяц, неделя→прошлая неделя). Окна уже
  // выровнены «по календарным дням 1..N» в computeWindow.
  const briefsTotal = team.reduce((s, x) => s + x.briefs, 0);
  const prevRows = await db
    .select({
      dials: sql<number>`coalesce(sum(${managerActivity.dialsTotal}),0)`,
      kp: sql<number>`coalesce(sum(${managerActivity.kpSent}),0)`,
      deals: sql<number>`coalesce(sum(${managerActivity.dealsCreatedCount}),0)`,
      briefs: sql<number>`coalesce(sum(${managerActivity.briefsCreated}),0)`,
    })
    .from(managerActivity)
    .where(and(gte(managerActivity.reportDate, prevStart), lte(managerActivity.reportDate, prevEnd)));
  const prev = prevRows[0] ?? { dials: 0, kp: 0, deals: 0, briefs: 0 };
  // «Проведено» прошлого окна — из событийного слоя (всё окно, без sales-фильтра, как раньше).
  const prevHeld = (await fetchHeldRows(prevStart, prevEnd)).reduce((s, r) => s + r.n, 0);

  // Отказы воронки Продажи (C10:LOSE, без СПАМ) — счётчик за текущее окно vs прошлое,
  // по дате отказа в МСК (deal_rejections, событийный слой).
  const rejAtMsk = sql`(${dealRejections.rejectedAt} AT TIME ZONE 'Europe/Moscow')::date`;
  const notSpam = sql`${dealRejections.reasonId} IS DISTINCT FROM ${SPAM_REASON_10}`;
  const countRejections = async (s: string, e: string): Promise<number> => {
    const r = await db
      .select({ n: sql<number>`count(*)` })
      .from(dealRejections)
      .where(and(eq(dealRejections.stageId, SALES_LOSE_STAGE), notSpam, gte(rejAtMsk, s), lte(rejAtMsk, e)));
    return Number(r[0]?.n ?? 0);
  };
  const [rejectionsCount, rejectionsPrev] = await Promise.all([
    countRejections(start, end),
    countRejections(prevStart, prevEnd),
  ]);

  // Оплаты (Приходы 2026, КД без НДС, отдел Продажи). Сравнение «по календарным дням»:
  // текущее окно [start,end] (для месяца = 1..N до снимка) vs прошлое [prevStart,prevEnd]
  // (прошлый месяц 1..N). «Эффективная дата» оплаты = pay_date, если он валидный
  // дд.мм.гггг; иначе 1-е число месяца из pay_year/pay_month (часть строк заполнена
  // только одной из колонок — ловим обе). Вложенный CASE, чтобы to_date не падал на
  // кривых строках. Так суммы видны независимо от того, какая колонка заполнена.
  const payFullDate = sql`${payments.payDate} ~ '^[0-9]{1,2}[.][0-9]{1,2}[.][0-9]{4}$'`;
  const payEffDate = sql`coalesce(
    case when ${payFullDate} then to_date(${payments.payDate}, 'DD.MM.YYYY') end,
    case when ${payments.payYear} is not null and ${payments.payMonth} is not null
         then make_date(${payments.payYear}, ${payments.payMonth}, 1) end
  )`;
  const sumPayBetween = async (s: string, e: string): Promise<number> => {
    const r = await db
      .select({
        amt: sql<number>`coalesce(sum(case when ${payEffDate} between ${s}::date and ${e}::date then ${payments.kdNoVat} else 0 end),0)`,
      })
      .from(payments)
      .where(eq(payments.dept, 'Продажи'));
    return Number(r[0]?.amt ?? 0);
  };
  const [paymentsTotal, paymentsPrev] = await Promise.all([
    sumPayBetween(start, end),
    sumPayBetween(prevStart, prevEnd),
  ]);

  const deltas = {
    meetings: delta(meetingsHeldTotal, prevHeld),
    dials: delta(dialsTotal, Number(prev.dials)),
    kp: delta(kpTotal, Number(prev.kp)),
    deals: delta(dealsCreatedTotal, Number(prev.deals)),
    payments: delta(paymentsTotal, paymentsPrev),
    rejections: delta(rejectionsCount, rejectionsPrev),
    briefs: delta(briefsTotal, Number(prev.briefs)),
  };

  // Тренд по дням месяца — для спарклайнов. Скелет дней и звонки — из активности,
  // «проведено» — из событийного слоя (heldByDate за то же окно start..end).
  const trendRows = await db
    .select({
      date: managerActivity.reportDate,
      dials: sql<number>`coalesce(sum(${managerActivity.dialsTotal}),0)`,
    })
    .from(managerActivity)
    .where(and(gte(managerActivity.reportDate, start), lte(managerActivity.reportDate, end)))
    .groupBy(managerActivity.reportDate)
    .orderBy(managerActivity.reportDate);
  const trend: TrendPoint[] = trendRows.map((r) => ({
    date: String(r.date),
    meetings: heldByDate.get(String(r.date)) ?? 0,
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

  // ── Операционная эффективность («Опер» по дням) — блок вместо «Качества встреч».
  // Балл считаем по модели живых минут (operational.ts); период и состав следуют за
  // пикером дашборда (окно start..snapshot) и sales-фильтром. Встречи берём из
  // событийного слоя (heldByMgrDate), остальное — из manager_activity по дням.
  const operEnd = snapshotDate ?? end;
  const operDays = weekdayRange(start, operEnd);
  const operConds = [gte(managerActivity.reportDate, start), lte(managerActivity.reportDate, operEnd)];
  if (salesIds.length) operConds.push(inArray(managerActivity.managerId, salesIds));
  const operActRows = operDays.length
    ? await db
        .select({
          managerId: managerActivity.managerId,
          date: managerActivity.reportDate,
          dials: sql<number>`coalesce(sum(${managerActivity.dialsTotal}),0)`,
          calls60: sql<number>`coalesce(sum(${managerActivity.calls60sPlus}),0)`,
          messenger: sql<number>`coalesce(sum(${managerActivity.messengerDialogs}),0)`,
          emails: sql<number>`coalesce(sum(${managerActivity.emailsSent}),0)`,
        })
        .from(managerActivity)
        .where(and(...operConds))
        .groupBy(managerActivity.managerId, managerActivity.reportDate)
    : [];
  const operActByMgr = new Map<number, Map<string, { dials: number; calls60: number; messenger: number; emails: number }>>();
  for (const r of operActRows) {
    const byDate = operActByMgr.get(r.managerId) ?? new Map<string, { dials: number; calls60: number; messenger: number; emails: number }>();
    byDate.set(String(r.date), {
      dials: Number(r.dials),
      calls60: Number(r.calls60),
      messenger: Number(r.messenger),
      emails: Number(r.emails),
    });
    operActByMgr.set(r.managerId, byDate);
  }
  // Дни отсутствия (отпуск/больничный) за окно — «Отпуск», вне среднего балла.
  const absenceRows = operDays.length
    ? await db
        .select({ managerId: managerAbsences.managerId, date: managerAbsences.absenceDate })
        .from(managerAbsences)
        .where(and(gte(managerAbsences.absenceDate, start), lte(managerAbsences.absenceDate, operEnd)))
    : [];
  const leaveByMgr = new Map<number, Set<string>>();
  for (const r of absenceRows) {
    const set = leaveByMgr.get(r.managerId) ?? new Set<string>();
    set.add(String(r.date));
    leaveByMgr.set(r.managerId, set);
  }

  const operMembers: OperMemberInput[] = team.map((tm) => {
    const byDate = new Map<string, OperDayInput>();
    const act = operActByMgr.get(tm.managerId);
    const held = heldByMgrDate.get(tm.managerId);
    for (const d of operDays) {
      const a = act?.get(d);
      const meetings = held?.get(d) ?? 0;
      if (!a && meetings === 0) continue;
      byDate.set(d, {
        date: d,
        dials: a?.dials ?? 0,
        calls60: a?.calls60 ?? 0,
        messenger: a?.messenger ?? 0,
        emails: a?.emails ?? 0,
        meetings,
      });
    }
    return {
      managerId: tm.managerId,
      name: tm.name,
      role: tm.role,
      isTm: isTelemarketing(tm.role),
      isActive: userMap.get(tm.managerId)?.active ?? true,
      byDate,
      leaveDays: leaveByMgr.get(tm.managerId),
    };
  });
  const operational = buildOperationalMatrix(operDays, operMembers);

  // Отказы воронки Продажи — с начала года до опорного дня (независимо от пикера).
  const salesRejections = await getSalesRejections(snapshotDate);

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
    paymentsTotal,
    rejectionsCount,
    briefsTotal,
    salesFunnel,
    forecast,
    meetingQuality,
    operational,
    managerConversions,
    managerPipeline,
    tmActivity,
    messaging,
    velocity,
    monthly,
    day2day,
    planFact,
    salesRejections,
    deltas,
    trend,
    health,
    generatedAt,
  };
}
