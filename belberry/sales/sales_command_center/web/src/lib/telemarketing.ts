import 'server-only';

import { and, eq, gte, inArray, lte, sql } from 'drizzle-orm';
import { db } from '@/db';
import { callHourly, dealRejections, dealsSnapshot, managerActivity, meetings, plans, reports, users } from '@/db/schema';
import {
  buildTmAlerts,
  buildTmHeatmap,
  buildTmMeetingQuality,
  buildTmRejections,
  type HeatInput,
  type RejectionInput,
  type TmAlertInput,
  type TmQualityInput,
} from './telemarketing-shared';

/** Стадия состоявшейся встречи (SP 1048). Единый источник для событийного слоя
 *  встреч (telemarketing.ts + dashboard.ts), зеркало MEETING_HELD_STAGE в collect.py. */
export const MEETING_HELD_STAGE = 'DT1048_24:SUCCESS';
const STAGE_REJECTED = 'C50:APOLOGY';
const STAGE_POSTPONED = 'C50:LOSE';
// «Выручка <30 млн» — автодисквал по правилу ТМ (не вина менеджера), исключаем.
const REASON_REVENUE_AUTO = 8542;
import {
  buildTmFunnel50,
  buildTmKpis,
  buildTmManagerTable,
  buildTmMeetingsResult,
  buildTmMicroFunnel,
  buildTmOutreach,
  buildTmPlanFact,
  isTelemarketing,
  type TmDashboardData,
  type TmMember,
  type TmMonthlyBundle,
  type TmMonthlyInput,
  type TmMonthlyManager,
} from './telemarketing-shared';

export type TmPeriod = 'month' | 'week';

const MONTHS_RU = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

/** Рабочих дней (Пн–Пт) в [start, end] включительно. */
function countWeekdays(start: string, end: string): number {
  const s = new Date(`${start}T00:00:00Z`);
  const e = new Date(`${end}T00:00:00Z`);
  let n = 0;
  for (let d = new Date(s); d <= e; d.setUTCDate(d.getUTCDate() + 1)) {
    const wd = d.getUTCDay();
    if (wd !== 0 && wd !== 6) n += 1;
  }
  return n;
}

interface Window {
  start: string;
  end: string;
  label: string;
}

/** Окно периода. Месяц — календарный до снимка; неделя — 7 дней до снимка. */
function computeWindow(snapshotDate: string, range: TmPeriod): Window {
  const [y, m, d] = snapshotDate.split('-').map(Number);
  if (range === 'week') {
    const endD = new Date(Date.UTC(y, m - 1, d));
    const startD = new Date(endD);
    startD.setUTCDate(endD.getUTCDate() - 6);
    const ddmm = (x: Date) =>
      `${String(x.getUTCDate()).padStart(2, '0')}.${String(x.getUTCMonth() + 1).padStart(2, '0')}`;
    return { start: startD.toISOString().slice(0, 10), end: snapshotDate, label: `7 дней · ${ddmm(startD)}–${ddmm(endD)}` };
  }
  const start = `${snapshotDate.slice(0, 7)}-01`;
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const end = `${snapshotDate.slice(0, 7)}-${String(last).padStart(2, '0')}`;
  return { start, end, label: `${MONTHS_RU[m - 1]} ${y}` };
}

function emptyData(): TmDashboardData {
  return {
    monthLabel: '—',
    periodLabel: '—',
    snapshotDate: null,
    workingDays: 1,
    managers: [],
    kpis: buildTmKpis([], 1),
    kpisPrev: null,
    kpisCmpLabel: '',
    table: [],
    funnel50: buildTmFunnel50([], new Map(), new Map()),
    meetingsResult: buildTmMeetingsResult([]),
    monthlyBundle: { months: [], perManager: [], selectableManagers: [], curLabel: '', prevLabel: '' },
    microFunnels: [],
    planFact: buildTmPlanFact({ dials60PerTm: 400, briefingsPerTm: 20, members: [] }),
    outreach: buildTmOutreach([]),
    rejections: [],
    heatmap: buildTmHeatmap([]),
    meetingQuality: buildTmMeetingQuality([]),
    alerts: [],
    monthOptions: [],
    selectedMonth: null,
    generatedAt: null,
  };
}

export async function getTmDashboardData(
  range: TmPeriod = 'month',
  monthParam?: string | null,
): Promise<TmDashboardData> {
  const latest = await db.select({ d: sql<string>`max(${dealsSnapshot.reportDate})` }).from(dealsSnapshot);
  const snapshotDate = latest[0]?.d ?? null;
  if (!snapshotDate) return emptyData();

  // Окно периода: явный месяц (?month=YYYY-MM) переопределяет Месяц/Неделя.
  let start: string;
  let end: string;
  let label: string;
  const monthOk = !!monthParam && /^\d{4}-\d{2}$/.test(monthParam);
  if (monthOk) {
    const [my, mm] = (monthParam as string).split('-').map(Number);
    start = `${monthParam}-01`;
    const lastDay = new Date(Date.UTC(my, mm, 0)).getUTCDate();
    const monthEnd = `${monthParam}-${String(lastDay).padStart(2, '0')}`;
    // Текущий месяц снимка — обрезаем по дате снимка (MTD).
    end = monthParam === snapshotDate.slice(0, 7) ? snapshotDate : monthEnd;
    label = `${MONTHS_RU[mm - 1]} ${my}`;
  } else {
    const w = computeWindow(snapshotDate, range);
    start = w.start;
    end = w.end;
    label = w.label;
  }
  const planPeriod = monthOk ? (monthParam as string) : snapshotDate.slice(0, 7);
  const workingDays = countWeekdays(start, end);
  const periodLabel = range === 'week' && !monthOk ? label : `${label} · ${workingDays} раб. дн.`;

  // Справочник сотрудников.
  const userRows = await db
    .select({ id: users.bitrixId, name: users.name, dept: users.dept, isActive: users.isActive })
    .from(users);
  const userMap = new Map(userRows.map((u) => [u.id, { name: u.name, dept: u.dept ?? '', isActive: u.isActive }]));

  // Активность за период по всем менеджерам, затем фильтр scope ТМ по должности.
  const actRows = await db
    .select({
      managerId: managerActivity.managerId,
      dials: sql<number>`coalesce(sum(${managerActivity.dialsTotal}),0)`,
      answered: sql<number>`coalesce(sum(${managerActivity.callsAnswered}),0)`,
      calls60: sql<number>`coalesce(sum(${managerActivity.calls60sPlus}),0)`,
      calls120: sql<number>`coalesce(sum(${managerActivity.calls120sPlus}),0)`,
      talkSeconds: sql<number>`coalesce(sum(${managerActivity.talkSeconds}),0)`,
      meetingsSet: sql<number>`coalesce(sum(${managerActivity.meetingsSet}),0)`,
      dealsCold: sql<number>`coalesce(sum(${managerActivity.dealsColdCount}),0)`,
      messenger: sql<number>`coalesce(sum(${managerActivity.messengerDialogs}),0)`,
      emails: sql<number>`coalesce(sum(${managerActivity.emailsSent}),0)`,
    })
    .from(managerActivity)
    .where(and(gte(managerActivity.reportDate, start), lte(managerActivity.reportDate, end)))
    .groupBy(managerActivity.managerId);

  const members: TmMember[] = actRows
    .filter((r) => isTelemarketing(userMap.get(r.managerId)?.dept))
    .map((r) => ({
      managerId: r.managerId,
      name: userMap.get(r.managerId)?.name ?? `id ${r.managerId}`,
      dept: userMap.get(r.managerId)?.dept ?? '',
      dials: Number(r.dials),
      answered: Number(r.answered),
      calls60: Number(r.calls60),
      calls120: Number(r.calls120),
      talkSeconds: Number(r.talkSeconds),
      meetingsSet: Number(r.meetingsSet),
      meetingsHeldByCreator: 0, // наполняется ниже из событий таблицы meetings
      briefingsHeldByCreator: 0, // наполняется ниже (held + type=briefing)
      rejectionsPeriod: 0, // наполняется ниже из deal_rejections
      dealsCold: Number(r.dealsCold),
      messenger: Number(r.messenger),
      emails: Number(r.emails),
    }))
    .sort((a, b) => b.dials - a.dials);

  if (members.length === 0) {
    return { ...emptyData(), monthLabel: label, periodLabel, snapshotDate, workingDays };
  }

  // Событийная метрика «состоялось»: встречи (SP1048 SUCCESS), назначенные ТМ
  // (created_by), за период — запросом по таблице meetings, не из агрегата.
  const tmIds = members.map((m) => m.managerId);
  const heldRows = await db
    .select({ creator: meetings.createdBy, n: sql<number>`count(*)` })
    .from(meetings)
    .where(
      and(
        eq(meetings.status, MEETING_HELD_STAGE),
        inArray(meetings.createdBy, tmIds),
        gte(meetings.reportDate, start),
        lte(meetings.reportDate, end),
      ),
    )
    .groupBy(meetings.createdBy);
  const heldByCreator = new Map<number, number>();
  for (const r of heldRows) if (r.creator != null) heldByCreator.set(r.creator, Number(r.n));
  for (const m of members) m.meetingsHeldByCreator = heldByCreator.get(m.managerId) ?? 0;

  // Состоявшиеся БРИФования по ТМ-создателю (held + type=briefing) — для план/факта.
  const briefHeldRows = tmIds.length
    ? await db
        .select({ creator: meetings.createdBy, n: sql<number>`count(*)` })
        .from(meetings)
        .where(
          and(
            eq(meetings.status, MEETING_HELD_STAGE),
            eq(meetings.meetingType, 'briefing'),
            inArray(meetings.createdBy, tmIds),
            gte(meetings.reportDate, start),
            lte(meetings.reportDate, end),
          ),
        )
        .groupBy(meetings.createdBy)
    : [];
  const briefByCreator = new Map<number, number>();
  for (const r of briefHeldRows) if (r.creator != null) briefByCreator.set(r.creator, Number(r.n));
  for (const m of members) m.briefingsHeldByCreator = briefByCreator.get(m.managerId) ?? 0;

  // Причины отвала (deal_rejections) — по ВЛАДЕЛЬЦУ сделки (assigned_by, чья база),
  // как в отчёте; «Выручка <30» (автодисквал) исключаем. rejected_at — в МСК.
  const nameById = new Map(members.map((m) => [m.managerId, m.name]));
  const rejAtMsk = sql`(${dealRejections.rejectedAt} AT TIME ZONE 'Europe/Moscow')::date`;
  const notRevenueAuto = sql`${dealRejections.reasonId} IS DISTINCT FROM ${REASON_REVENUE_AUTO}`;
  const rejReasonRows = await db
    .select({ mgr: dealRejections.assignedBy, reason: dealRejections.reasonId, n: sql<number>`count(*)` })
    .from(dealRejections)
    .where(and(eq(dealRejections.stageId, STAGE_REJECTED), inArray(dealRejections.assignedBy, tmIds), notRevenueAuto))
    .groupBy(dealRejections.assignedBy, dealRejections.reasonId);
  const rejectionInputs: RejectionInput[] = rejReasonRows
    .filter((r) => r.mgr != null)
    .map((r) => ({
      managerId: r.mgr as number,
      name: nameById.get(r.mgr as number) ?? `id ${r.mgr}`,
      reasonId: r.reason,
      count: Number(r.n),
    }));
  const rejections = buildTmRejections(rejectionInputs);

  // Отвалы за период (для сжигания базы) — по владельцу, без автодисквала.
  const rejPeriodRows = await db
    .select({ mgr: dealRejections.assignedBy, n: sql<number>`count(*)` })
    .from(dealRejections)
    .where(
      and(
        eq(dealRejections.stageId, STAGE_REJECTED),
        inArray(dealRejections.assignedBy, tmIds),
        notRevenueAuto,
        gte(rejAtMsk, start),
        lte(rejAtMsk, end),
      ),
    )
    .groupBy(dealRejections.assignedBy);
  const rejByMgr = new Map<number, number>();
  for (const r of rejPeriodRows) if (r.mgr != null) rejByMgr.set(r.mgr, Number(r.n));
  for (const m of members) m.rejectionsPeriod = rejByMgr.get(m.managerId) ?? 0;

  // Снимок воронки [50] на последнем снимке — по владельцам (ТМ и МП).
  const funnelCells = await db
    .select({ stage: dealsSnapshot.stage, managerId: dealsSnapshot.managerId })
    .from(dealsSnapshot)
    .where(and(eq(dealsSnapshot.reportDate, snapshotDate), eq(dealsSnapshot.categoryId, 50)));

  // Имена + статус «уволен» владельцев — из справочника users (is_active держим
  // актуальным из Bitrix ACTIVE через sync_users_active).
  const fNameById = new Map<number, string>();
  const fActiveById = new Map<number, boolean>();
  for (const [id, u] of userMap) {
    fNameById.set(id, u.name);
    fActiveById.set(id, u.isActive);
  }

  // Помесячная динамика по всем ТМ — последние 8 месяцев (мультиселект на клиенте).
  const dynMonths: { ym: string; label: string }[] = [];
  {
    const [cy, cm] = snapshotDate.split('-').map(Number);
    for (let i = 7; i >= 0; i--) {
      let mm = cm - i;
      let yy = cy;
      while (mm <= 0) {
        mm += 12;
        yy -= 1;
      }
      dynMonths.push({ ym: `${yy}-${String(mm).padStart(2, '0')}`, label: `${MONTHS_RU[mm - 1]} ${String(yy).slice(2)}` });
    }
  }
  const dynStart = `${dynMonths[0].ym}-01`;

  // Помесячно по КАЖДОМУ ТМ (мультиселект собирается на клиенте). Группировка по
  // (ym, владелец); для «состоялось» — по создателю, для отвалов — по владельцу.
  const ymExpr = sql<string>`to_char(${managerActivity.reportDate}, 'YYYY-MM')`;
  const monRows = await db
    .select({
      ym: ymExpr,
      mgr: managerActivity.managerId,
      dials: sql<number>`coalesce(sum(${managerActivity.dialsTotal}),0)`,
      answered: sql<number>`coalesce(sum(${managerActivity.callsAnswered}),0)`,
      calls60: sql<number>`coalesce(sum(${managerActivity.calls60sPlus}),0)`,
      talkSeconds: sql<number>`coalesce(sum(${managerActivity.talkSeconds}),0)`,
      meetingsSet: sql<number>`coalesce(sum(${managerActivity.meetingsSet}),0)`,
    })
    .from(managerActivity)
    .where(and(gte(managerActivity.reportDate, dynStart), inArray(managerActivity.managerId, tmIds)))
    .groupBy(ymExpr, managerActivity.managerId);
  const monByMgrYm = new Map(monRows.map((r) => [`${r.mgr}:${r.ym}`, r]));

  const ymMeetExpr = sql<string>`to_char(${meetings.reportDate}, 'YYYY-MM')`;
  const heldMonRows = await db
    .select({ ym: ymMeetExpr, creator: meetings.createdBy, n: sql<number>`count(*)` })
    .from(meetings)
    .where(
      and(
        eq(meetings.status, MEETING_HELD_STAGE),
        inArray(meetings.createdBy, tmIds),
        gte(meetings.reportDate, dynStart),
      ),
    )
    .groupBy(ymMeetExpr, meetings.createdBy);
  const heldByMgrYm = new Map<string, number>();
  for (const r of heldMonRows) if (r.creator != null) heldByMgrYm.set(`${r.creator}:${r.ym}`, Number(r.n));

  const ymRejExpr = sql<string>`to_char((${dealRejections.rejectedAt} AT TIME ZONE 'Europe/Moscow'), 'YYYY-MM')`;
  const monRejRows = await db
    .select({ ym: ymRejExpr, mgr: dealRejections.assignedBy, stage: dealRejections.stageId, n: sql<number>`count(*)` })
    .from(dealRejections)
    .where(
      and(
        inArray(dealRejections.assignedBy, tmIds),
        inArray(dealRejections.stageId, [STAGE_REJECTED, STAGE_POSTPONED]),
        notRevenueAuto,
        gte(rejAtMsk, dynStart),
      ),
    )
    .groupBy(ymRejExpr, dealRejections.assignedBy, dealRejections.stageId);
  const rejByMgrYm = new Map<string, { rejected: number; postponed: number }>();
  for (const r of monRejRows) {
    if (r.mgr == null) continue;
    const k = `${r.mgr}:${r.ym}`;
    const e = rejByMgrYm.get(k) ?? { rejected: 0, postponed: 0 };
    if (r.stage === STAGE_REJECTED) e.rejected = Number(r.n);
    else if (r.stage === STAGE_POSTPONED) e.postponed = Number(r.n);
    rejByMgrYm.set(k, e);
  }

  // Период «на ту же дату» 1..N: текущий (неполный) месяц снимка vs прошлый месяц.
  const snapYm = snapshotDate.slice(0, 7);
  const [sy, sm] = snapYm.split('-').map(Number);
  const snapDay = Number(snapshotDate.slice(8, 10));
  let pm = sm - 1;
  let py = sy;
  if (pm <= 0) {
    pm += 12;
    py -= 1;
  }
  const prevYm = `${py}-${String(pm).padStart(2, '0')}`;
  const prevLastDay = new Date(Date.UTC(py, pm, 0)).getUTCDate();
  const prevDay = Math.min(snapDay, prevLastDay);
  const curPStart = `${snapYm}-01`;
  const curPEnd = snapshotDate;
  const prevPStart = `${prevYm}-01`;
  const prevPEnd = `${prevYm}-${String(prevDay).padStart(2, '0')}`;
  const curLabel = `1–${snapDay} ${MONTHS_RU[sm - 1]}`;
  const prevLabel = `1–${prevDay} ${MONTHS_RU[pm - 1]}`;

  // Активность 1..N окна (dials/calls60/meetingsSet) — по дням managerActivity.
  const periodActivity = async (s: string, e: string) => {
    const rows = await db
      .select({
        mgr: managerActivity.managerId,
        dials: sql<number>`coalesce(sum(${managerActivity.dialsTotal}),0)`,
        calls60: sql<number>`coalesce(sum(${managerActivity.calls60sPlus}),0)`,
        meetingsSet: sql<number>`coalesce(sum(${managerActivity.meetingsSet}),0)`,
      })
      .from(managerActivity)
      .where(and(gte(managerActivity.reportDate, s), lte(managerActivity.reportDate, e), inArray(managerActivity.managerId, tmIds)))
      .groupBy(managerActivity.managerId);
    return new Map(rows.map((r) => [r.mgr, r]));
  };
  // Состоялось 1..N окна (по создателю-ТМ) — событийным запросом по meetings.
  const periodHeld = async (s: string, e: string) => {
    const rows = await db
      .select({ creator: meetings.createdBy, n: sql<number>`count(*)` })
      .from(meetings)
      .where(
        and(
          eq(meetings.status, MEETING_HELD_STAGE),
          inArray(meetings.createdBy, tmIds),
          gte(meetings.reportDate, s),
          lte(meetings.reportDate, e),
        ),
      )
      .groupBy(meetings.createdBy);
    const m = new Map<number, number>();
    for (const r of rows) if (r.creator != null) m.set(r.creator, Number(r.n));
    return m;
  };
  const [curAct, prevAct, curHeld, prevHeld] = await Promise.all([
    periodActivity(curPStart, curPEnd),
    periodActivity(prevPStart, prevPEnd),
    periodHeld(curPStart, curPEnd),
    periodHeld(prevPStart, prevPEnd),
  ]);

  const perMonthlyManager: TmMonthlyManager[] = members.map((m) => {
    const rows: TmMonthlyInput[] = dynMonths.map((mo) => {
      const r = monByMgrYm.get(`${m.managerId}:${mo.ym}`);
      const rej = rejByMgrYm.get(`${m.managerId}:${mo.ym}`);
      return {
        ym: mo.ym,
        label: mo.label,
        dials: r ? Number(r.dials) : 0,
        answered: r ? Number(r.answered) : 0,
        calls60: r ? Number(r.calls60) : 0,
        talkSeconds: r ? Number(r.talkSeconds) : 0,
        meetingsSet: r ? Number(r.meetingsSet) : 0,
        meetingsHeldByCreator: heldByMgrYm.get(`${m.managerId}:${mo.ym}`) ?? 0,
        rejected: rej?.rejected ?? 0,
        postponed: rej?.postponed ?? 0,
      };
    });
    const ca = curAct.get(m.managerId);
    const pa = prevAct.get(m.managerId);
    return {
      managerId: m.managerId,
      name: m.name,
      isActive: userMap.get(m.managerId)?.isActive ?? true,
      rows,
      cur: {
        dials: ca ? Number(ca.dials) : 0,
        calls60: ca ? Number(ca.calls60) : 0,
        meetingsSet: ca ? Number(ca.meetingsSet) : 0,
        held: curHeld.get(m.managerId) ?? 0,
      },
      prev: {
        dials: pa ? Number(pa.dials) : 0,
        calls60: pa ? Number(pa.calls60) : 0,
        meetingsSet: pa ? Number(pa.meetingsSet) : 0,
        held: prevHeld.get(m.managerId) ?? 0,
      },
    };
  });
  const monthlyBundle: TmMonthlyBundle = {
    months: dynMonths,
    perManager: perMonthlyManager,
    selectableManagers: perMonthlyManager
      .map((m) => ({ managerId: m.managerId, name: m.name, isActive: m.isActive }))
      .sort((a, b) => a.name.localeCompare(b.name, 'ru')),
    curLabel,
    prevLabel,
  };


  // План ТМ на месяц: дозвоны ≥60с (metric='tm_dials60', дефолт 400) и состоявшиеся
  // брифования (metric='tm_briefings', дефолт 20) — на 1 звонаря.
  const tmPlanRows = await db
    .select({ metric: plans.metric, target: plans.target })
    .from(plans)
    .where(and(eq(plans.period, planPeriod), inArray(plans.metric, ['tm_dials60', 'tm_briefings'])));
  const tmPlanMap: Record<string, number> = {};
  for (const r of tmPlanRows) tmPlanMap[r.metric] = Number(r.target);
  const dials60PerTm = tmPlanMap['tm_dials60'] ?? 400;
  const briefingsPerTm = tmPlanMap['tm_briefings'] ?? 20;

  // Heatmap «когда берут трубку»: час × день недели по ТМ за последние 3 месяца —
  // более репрезентативная выборка, одиночные дни не создают шум.
  // dow = extract(dow): 0=Вс..6=Сб.
  const heatStart = (() => {
    const [hy, hm] = snapshotDate.split('-').map(Number);
    let mm = hm - 2;
    let yy = hy;
    while (mm <= 0) {
      mm += 12;
      yy -= 1;
    }
    return `${yy}-${String(mm).padStart(2, '0')}-01`;
  })();
  const dowExpr = sql<number>`extract(dow from ${callHourly.reportDate})::int`;
  const heatRows = await db
    .select({
      dow: dowExpr,
      hour: callHourly.hour,
      dials: sql<number>`coalesce(sum(${callHourly.dials}),0)`,
      calls60: sql<number>`coalesce(sum(${callHourly.calls60}),0)`,
    })
    .from(callHourly)
    .where(and(inArray(callHourly.managerId, tmIds), gte(callHourly.reportDate, heatStart)))
    .groupBy(dowExpr, callHourly.hour);
  const heatmap = buildTmHeatmap(
    heatRows.map<HeatInput>((r) => ({ dow: Number(r.dow), hour: Number(r.hour), dials: Number(r.dials), calls60: Number(r.calls60) })),
  );

  // Качество встреч, назначенных ТМ — из готового разбора (analysis_json), только
  // состоявшиеся встречи создателя-ТМ с баллом.
  const mqRows = await db
    .select({ creator: meetings.createdBy, analysis: meetings.analysisJson })
    .from(meetings)
    .where(
      and(
        eq(meetings.status, MEETING_HELD_STAGE),
        inArray(meetings.createdBy, tmIds),
        sql`${meetings.analysisJson} is not null`,
        gte(meetings.reportDate, dynStart),
      ),
    );
  const qualityInputs: TmQualityInput[] = [];
  for (const r of mqRows) {
    if (r.creator == null) continue;
    const a = (r.analysis ?? {}) as { score?: number; next_step?: unknown; next_steps?: unknown[] };
    if (typeof a.score !== 'number') continue;
    qualityInputs.push({
      managerId: r.creator,
      name: nameById.get(r.creator) ?? `id ${r.creator}`,
      score: a.score,
      hasNextStep: a.next_step != null || (Array.isArray(a.next_steps) && a.next_steps.length > 0),
    });
  }
  const meetingQuality = buildTmMeetingQuality(qualityInputs);

  // ТМ-алерты: конверсия дозвон→встреча за 2 последних ПОЛНЫХ месяца (месяц снимка —
  // частичный, исключаем) + сжигание/явка за период. snapYm/sy/sm объявлены выше.
  let am = sm - 2;
  let ay = sy;
  while (am <= 0) {
    am += 12;
    ay -= 1;
  }
  const alertStart = `${ay}-${String(am).padStart(2, '0')}-01`;
  const ymActExpr = sql<string>`to_char(${managerActivity.reportDate}, 'YYYY-MM')`;
  const alertRows = await db
    .select({
      mgr: managerActivity.managerId,
      ym: ymActExpr,
      mset: sql<number>`coalesce(sum(${managerActivity.meetingsSet}),0)`,
      c60: sql<number>`coalesce(sum(${managerActivity.calls60sPlus}),0)`,
    })
    .from(managerActivity)
    .where(and(inArray(managerActivity.managerId, tmIds), gte(managerActivity.reportDate, alertStart)))
    .groupBy(managerActivity.managerId, ymActExpr);
  const convByMgr = new Map<number, { ym: string; conv: number | null }[]>();
  for (const r of alertRows) {
    if (r.ym === snapYm) continue; // текущий месяц частичный — пропускаем
    const c60 = Number(r.c60);
    const conv = c60 > 0 ? Math.round((Number(r.mset) / c60) * 1000) / 10 : null;
    const arr = convByMgr.get(r.mgr) ?? [];
    arr.push({ ym: r.ym, conv });
    convByMgr.set(r.mgr, arr);
  }
  const alertInputs: TmAlertInput[] = members.map((m) => {
    const months = (convByMgr.get(m.managerId) ?? []).sort((a, b) => (a.ym < b.ym ? 1 : -1));
    return {
      name: m.name,
      convNow: months[0]?.conv ?? null,
      convPrev: months[1]?.conv ?? null,
      burn: m.meetingsSet > 0 ? Math.round((m.rejectionsPeriod / m.meetingsSet) * 10) / 10 : null,
      heldPct: m.meetingsSet > 0 ? Math.round((m.meetingsHeldByCreator / m.meetingsSet) * 1000) / 10 : null,
    };
  });
  const alerts = buildTmAlerts(alertInputs);

  const kpis = buildTmKpis(members, workingDays);

  // Сравнение «итога отдела» с аналогичным периодом прошлого месяца ПО КАЛЕНДАРНЫМ
  // ДНЯМ (1..N). Показываем только для живого текущего месяца — для недели и
  // выбранных прошлых месяцев сравнение не имеет смысла (период полный/иной).
  const isLiveMonth = !monthOk && range === 'month';
  let kpisPrev: ReturnType<typeof buildTmKpis> | null = null;
  let kpisCmpLabel = '';
  if (isLiveMonth) {
    const prevActRows = await db
      .select({
        managerId: managerActivity.managerId,
        dials: sql<number>`coalesce(sum(${managerActivity.dialsTotal}),0)`,
        answered: sql<number>`coalesce(sum(${managerActivity.callsAnswered}),0)`,
        calls60: sql<number>`coalesce(sum(${managerActivity.calls60sPlus}),0)`,
        calls120: sql<number>`coalesce(sum(${managerActivity.calls120sPlus}),0)`,
        talkSeconds: sql<number>`coalesce(sum(${managerActivity.talkSeconds}),0)`,
        meetingsSet: sql<number>`coalesce(sum(${managerActivity.meetingsSet}),0)`,
        dealsCold: sql<number>`coalesce(sum(${managerActivity.dealsColdCount}),0)`,
        messenger: sql<number>`coalesce(sum(${managerActivity.messengerDialogs}),0)`,
        emails: sql<number>`coalesce(sum(${managerActivity.emailsSent}),0)`,
      })
      .from(managerActivity)
      .where(and(gte(managerActivity.reportDate, prevPStart), lte(managerActivity.reportDate, prevPEnd)))
      .groupBy(managerActivity.managerId);
    const prevMembers: TmMember[] = prevActRows
      .filter((r) => isTelemarketing(userMap.get(r.managerId)?.dept))
      .map((r) => ({
        managerId: r.managerId,
        name: userMap.get(r.managerId)?.name ?? `id ${r.managerId}`,
        dept: userMap.get(r.managerId)?.dept ?? '',
        dials: Number(r.dials),
        answered: Number(r.answered),
        calls60: Number(r.calls60),
        calls120: Number(r.calls120),
        talkSeconds: Number(r.talkSeconds),
        meetingsSet: Number(r.meetingsSet),
        meetingsHeldByCreator: prevHeld.get(r.managerId) ?? 0,
        briefingsHeldByCreator: 0,
        rejectionsPeriod: 0,
        dealsCold: Number(r.dealsCold),
        messenger: Number(r.messenger),
        emails: Number(r.emails),
      }));
    kpisPrev = buildTmKpis(prevMembers, countWeekdays(prevPStart, prevPEnd));
    kpisCmpLabel = prevLabel;
  }

  // Свежесть отчёта.
  const repRows = await db
    .select({ g: reports.generatedAt })
    .from(reports)
    .where(eq(reports.reportDate, snapshotDate))
    .limit(1);
  const generatedAt = repRows[0]?.g ? new Date(repRows[0].g).toISOString() : null;

  return {
    monthLabel: label,
    periodLabel,
    snapshotDate,
    workingDays,
    managers: members.map((m) => ({ managerId: m.managerId, name: m.name })),
    kpis,
    kpisPrev,
    kpisCmpLabel,
    table: buildTmManagerTable(members),
    funnel50: buildTmFunnel50(funnelCells, fNameById, fActiveById),
    meetingsResult: buildTmMeetingsResult(members),
    monthlyBundle,
    microFunnels: members.map((m) => buildTmMicroFunnel(m)),
    planFact: buildTmPlanFact({
      dials60PerTm,
      briefingsPerTm,
      members: members.map((m) => ({
        managerId: m.managerId,
        name: m.name,
        calls60: m.calls60,
        briefingsHeld: m.briefingsHeldByCreator,
      })),
    }),
    outreach: buildTmOutreach(members),
    rejections,
    heatmap,
    meetingQuality,
    alerts,
    monthOptions: dynMonths.slice(-6).map((mo) => {
      const [oy, om] = mo.ym.split('-').map(Number);
      return { ym: mo.ym, label: `${MONTHS_RU[om - 1]} ${oy}` };
    }),
    selectedMonth: monthOk ? (monthParam as string) : null,
    generatedAt,
  };
}
