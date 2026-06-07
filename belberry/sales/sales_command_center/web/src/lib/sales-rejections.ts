import 'server-only';

import { and, eq, gte, lte, sql } from 'drizzle-orm';
import { db } from '@/db';
import { dealRejections, managerActivity, users } from '@/db/schema';
import {
  REASON_NULL_KEY,
  SALES_LOSE_STAGE,
  SPAM_REASON_10,
  MONTHS_RU_SHORT,
  isSalesManager,
  managersFromPerManager,
  type SalesRejectionPerManager,
  type SalesRejectionsBundle,
} from './sales-rejections-shared';

export {
  SALES_LOSE_STAGE,
  SPAM_REASON_10,
  REASON_10,
  reasonLabel10,
} from './sales-rejections-shared';

/** Отказы воронки Продажи с начала года до опорного дня — гранулярка по
 * действующим продажникам (для мультиселекта карточки 1) + таблица карточки 2.
 * Источник — deal_rejections (sync_rejections.py); оплаты — manager_activity
 * (deals_won_count, тот же владелец). СПАМ исключаем (считаем отдельно). */
export async function getSalesRejections(snapshotDate: string): Promise<SalesRejectionsBundle> {
  const year = Number(snapshotDate.slice(0, 4));
  const yearLabel = String(year);
  const yearStart = `${year}-01-01`;
  const rejAtMsk = sql`(${dealRejections.rejectedAt} AT TIME ZONE 'Europe/Moscow')::date`;
  const inYear = and(
    eq(dealRejections.stageId, SALES_LOSE_STAGE),
    gte(rejAtMsk, yearStart),
    lte(rejAtMsk, snapshotDate),
  );

  // Действующие продажники (отдел Продажи/РОП, без ТМ) — кого можно выбрать.
  const userRows = await db
    .select({ id: users.bitrixId, name: users.name, dept: users.dept, isActive: users.isActive })
    .from(users);
  const nameById = new Map(userRows.map((u) => [u.id, u.name]));
  const eligible = new Set(
    userRows.filter((u) => u.isActive && isSalesManager(u.dept)).map((u) => u.id),
  );

  // Менеджер × причина: количество + сумма потерь.
  const mgrReasonRows = await db
    .select({
      managerId: dealRejections.assignedBy,
      reasonId: dealRejections.reasonId,
      n: sql<number>`count(*)`,
      amount: sql<number>`coalesce(sum(${dealRejections.opportunity}),0)`,
    })
    .from(dealRejections)
    .where(inYear)
    .groupBy(dealRejections.assignedBy, dealRejections.reasonId);

  // Менеджер × месяц (ex-spam).
  const ymExpr = sql<string>`to_char((${dealRejections.rejectedAt} AT TIME ZONE 'Europe/Moscow'), 'YYYY-MM')`;
  const mgrMonthRows = await db
    .select({ managerId: dealRejections.assignedBy, ym: ymExpr, n: sql<number>`count(*)` })
    .from(dealRejections)
    .where(and(inYear, sql`${dealRejections.reasonId} IS DISTINCT FROM ${SPAM_REASON_10}`))
    .groupBy(dealRejections.assignedBy, ymExpr);

  // Оплаты (won) по владельцу — знаменатель «доли отказов».
  const wonRows = await db
    .select({
      managerId: managerActivity.managerId,
      won: sql<number>`coalesce(sum(${managerActivity.dealsWonCount}),0)`,
    })
    .from(managerActivity)
    .where(and(gte(managerActivity.reportDate, yearStart), lte(managerActivity.reportDate, snapshotDate)))
    .groupBy(managerActivity.managerId);
  const wonByMgr = new Map<number, number>();
  for (const r of wonRows) wonByMgr.set(r.managerId, Number(r.won));

  // Сборка гранулярки только по действующим продажникам.
  const pm = new Map<number, SalesRejectionPerManager>();
  const ensure = (id: number): SalesRejectionPerManager => {
    let e = pm.get(id);
    if (!e) {
      e = {
        managerId: id,
        name: nameById.get(id) ?? `id ${id}`,
        rejections: 0,
        lostAmount: 0,
        spam: 0,
        won: wonByMgr.get(id) ?? 0,
        monthCounts: {},
        reasonCounts: {},
      };
      pm.set(id, e);
    }
    return e;
  };

  for (const r of mgrReasonRows) {
    if (r.managerId == null || !eligible.has(r.managerId)) continue;
    const e = ensure(r.managerId);
    const count = Number(r.n);
    if (r.reasonId === SPAM_REASON_10) {
      e.spam += count;
      continue;
    }
    e.rejections += count;
    e.lostAmount += Number(r.amount);
    const key = r.reasonId == null ? REASON_NULL_KEY : String(r.reasonId);
    e.reasonCounts[key] = (e.reasonCounts[key] ?? 0) + count;
  }
  for (const r of mgrMonthRows) {
    if (r.managerId == null || !eligible.has(r.managerId)) continue;
    const e = ensure(r.managerId);
    e.monthCounts[r.ym] = (e.monthCounts[r.ym] ?? 0) + Number(r.n);
  }

  // Только те, у кого есть отказы (для осмысленного списка выбора).
  const perManager = [...pm.values()]
    .filter((m) => m.rejections > 0)
    .sort((a, b) => b.rejections - a.rejections);

  const lastMonth = Number(snapshotDate.slice(5, 7));
  const monthsSkeleton: { ym: string; label: string }[] = [];
  for (let m = 1; m <= lastMonth; m++) {
    monthsSkeleton.push({ ym: `${year}-${String(m).padStart(2, '0')}`, label: MONTHS_RU_SHORT[m - 1] });
  }

  const selectableManagers = [...perManager]
    .map((m) => ({ managerId: m.managerId, name: m.name }))
    .sort((a, b) => a.name.localeCompare(b.name, 'ru'));

  return {
    yearLabel,
    monthsSkeleton,
    perManager,
    selectableManagers,
    managers: managersFromPerManager(perManager),
  };
}
