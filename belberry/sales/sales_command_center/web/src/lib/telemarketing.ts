import 'server-only';

import { and, eq, gte, lte, sql } from 'drizzle-orm';
import { db } from '@/db';
import { dealsSnapshot, managerActivity, plans, reports, users } from '@/db/schema';
import {
  buildTmFunnel50,
  buildTmKpis,
  buildTmManagerTable,
  buildTmMeetingsResult,
  buildTmMicroFunnel,
  buildTmMonthly,
  buildTmOutreach,
  buildTmPlanFact,
  isTelemarketing,
  type TmDashboardData,
  type TmMember,
  type TmMonthlyInput,
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
    selectedManagerId: null,
    selectedManagerName: null,
    kpis: buildTmKpis([], 1),
    table: [],
    funnel50: buildTmFunnel50([]),
    meetingsResult: buildTmMeetingsResult([]),
    monthly: [],
    microFunnels: [],
    planFact: [],
    outreach: buildTmOutreach([]),
    generatedAt: null,
  };
}

export async function getTmDashboardData(
  range: TmPeriod = 'month',
  managerParam?: number | null,
): Promise<TmDashboardData> {
  const latest = await db.select({ d: sql<string>`max(${dealsSnapshot.reportDate})` }).from(dealsSnapshot);
  const snapshotDate = latest[0]?.d ?? null;
  if (!snapshotDate) return emptyData();

  const { start, end, label } = computeWindow(snapshotDate, range);
  const workingDays = countWeekdays(start, end);
  const periodLabel = range === 'week' ? label : `${label} · ${workingDays} раб. дн.`;

  // Справочник сотрудников.
  const userRows = await db
    .select({ id: users.bitrixId, name: users.name, dept: users.dept })
    .from(users);
  const userMap = new Map(userRows.map((u) => [u.id, { name: u.name, dept: u.dept ?? '' }]));

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
      meetingsHeld: sql<number>`coalesce(sum(${managerActivity.meetingsHeld}),0)`,
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
      dials: Number(r.dials),
      answered: Number(r.answered),
      calls60: Number(r.calls60),
      calls120: Number(r.calls120),
      talkSeconds: Number(r.talkSeconds),
      meetingsSet: Number(r.meetingsSet),
      meetingsHeld: Number(r.meetingsHeld),
      dealsCold: Number(r.dealsCold),
      messenger: Number(r.messenger),
      emails: Number(r.emails),
    }))
    .sort((a, b) => b.dials - a.dials);

  if (members.length === 0) {
    return { ...emptyData(), monthLabel: label, periodLabel, snapshotDate, workingDays };
  }

  // Выбранный звонарь для динамики/конверсии (по умолчанию — топ по наборам).
  const memberIds = new Set(members.map((m) => m.managerId));
  const selectedManagerId =
    managerParam != null && memberIds.has(managerParam) ? managerParam : members[0].managerId;
  const selectedMember = members.find((m) => m.managerId === selectedManagerId) ?? members[0];

  // Снимок воронки [50] на последнем снимке.
  const funnelCells = await db
    .select({ stage: dealsSnapshot.stage })
    .from(dealsSnapshot)
    .where(and(eq(dealsSnapshot.reportDate, snapshotDate), eq(dealsSnapshot.categoryId, 50)));

  // Помесячная динамика по выбранному звонарю — последние 8 месяцев.
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
  const ymExpr = sql<string>`to_char(${managerActivity.reportDate}, 'YYYY-MM')`;
  const monRows = await db
    .select({
      ym: ymExpr,
      dials: sql<number>`coalesce(sum(${managerActivity.dialsTotal}),0)`,
      answered: sql<number>`coalesce(sum(${managerActivity.callsAnswered}),0)`,
      calls60: sql<number>`coalesce(sum(${managerActivity.calls60sPlus}),0)`,
      talkSeconds: sql<number>`coalesce(sum(${managerActivity.talkSeconds}),0)`,
      meetingsSet: sql<number>`coalesce(sum(${managerActivity.meetingsSet}),0)`,
      meetingsHeld: sql<number>`coalesce(sum(${managerActivity.meetingsHeld}),0)`,
    })
    .from(managerActivity)
    .where(and(gte(managerActivity.reportDate, dynStart), eq(managerActivity.managerId, selectedManagerId)))
    .groupBy(ymExpr);
  const monByYm = new Map(monRows.map((r) => [r.ym, r]));
  const monthlyInputs: TmMonthlyInput[] = dynMonths.map((mo) => {
    const r = monByYm.get(mo.ym);
    return {
      ym: mo.ym,
      label: mo.label,
      dials: r ? Number(r.dials) : 0,
      answered: r ? Number(r.answered) : 0,
      calls60: r ? Number(r.calls60) : 0,
      talkSeconds: r ? Number(r.talkSeconds) : 0,
      meetingsSet: r ? Number(r.meetingsSet) : 0,
      meetingsHeld: r ? Number(r.meetingsHeld) : 0,
    };
  });

  // План встреч ТМ (plans, metric='meetings', период месяца снимка; дефолт 20/ТМ).
  const planRows = await db
    .select({ target: plans.target })
    .from(plans)
    .where(and(eq(plans.period, snapshotDate.slice(0, 7)), eq(plans.metric, 'meetings')))
    .limit(1);
  const monthlyPlanPerTm = planRows[0] ? Number(planRows[0].target) : 20;
  const meetingsPlanPerTm = range === 'week' ? Math.max(1, Math.round(monthlyPlanPerTm / 4)) : monthlyPlanPerTm;

  const kpis = buildTmKpis(members, workingDays);

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
    selectedManagerId,
    selectedManagerName: selectedMember.name,
    kpis,
    table: buildTmManagerTable(members),
    funnel50: buildTmFunnel50(funnelCells),
    meetingsResult: buildTmMeetingsResult(members),
    monthly: buildTmMonthly(monthlyInputs),
    microFunnels: members.map((m) => buildTmMicroFunnel(m)),
    planFact: buildTmPlanFact({
      meetingsSetFact: kpis.meetingsSet,
      meetingsPlanPerTm,
      tmCount: members.length,
    }),
    outreach: buildTmOutreach(members),
    generatedAt,
  };
}
