import 'server-only';

import { and, eq, gte, inArray, lte, sql } from 'drizzle-orm';
import { db } from '@/db';
import { dealRejections, managerActivity, users } from '@/db/schema';

// Воронка Продажи [10] — отказ = стадия C10:LOSE, причина в UF_CRM_1771495464.
export const SALES_LOSE_STAGE = 'C10:LOSE';
export const SPAM_REASON_10 = 8588;

/** Справочник причин отказа воронки Продажи (UF_CRM_1771495464, enum Bitrix). */
export const REASON_10: Record<number, string> = {
  8574: 'Нет связи',
  8576: 'Нет такой услуги / не реализуем',
  8578: 'Выручка <30 млн/год',
  8580: 'Ушли к конкурентам',
  8582: 'Свой исполнитель / инхаус',
  8584: 'Нехватка бюджета / нет финмодели',
  8586: 'Передумали / неактуально',
  8624: 'Действующий клиент',
  8588: 'СПАМ',
};

export function reasonLabel10(id: number | null): string {
  return id != null ? (REASON_10[id] ?? 'Другое') : '(не указана)';
}

const MONTHS_RU_SHORT = [
  'янв', 'фев', 'мар', 'апр', 'май', 'июнь',
  'июль', 'авг', 'сен', 'окт', 'ноя', 'дек',
];

export interface SalesReasonBucket {
  reasonId: number | null;
  label: string;
  count: number;
  pct: number;
}

export interface SalesRejectionMonth {
  ym: string;
  label: string;
  count: number;
}

export interface SalesRejectionManager {
  managerId: number;
  name: string;
  rejections: number;
  lostAmount: number;
  won: number;
  /** Доля отказов = отказы / (отказы + оплаты), %. null если нет закрытых. */
  lossRate: number | null;
  topReason: string | null;
}

export interface SalesRejections {
  yearLabel: string;
  totalRejections: number;
  lostAmount: number;
  /** Доля отказов по отделу = отказы / (отказы + оплаты), %. */
  lossRate: number | null;
  /** Средняя потеря на одну проигранную сделку, ₽. */
  avgLoss: number;
  /** Сколько СПАМ-лидов отсеяно (в отказы/долю не входят). */
  spamExcluded: number;
  wonTotal: number;
  months: SalesRejectionMonth[];
  reasons: SalesReasonBucket[];
  managers: SalesRejectionManager[];
}

// ── Чистые билдеры (тестируемы) ──────────────────────────────────────────────

export interface MgrReasonRow {
  managerId: number | null;
  reasonId: number | null;
  count: number;
  amount: number;
}

const lossRate = (rej: number, won: number): number | null =>
  rej + won > 0 ? Math.round((rej / (rej + won)) * 100) : null;

/** Агрегаты отказов из строк (менеджер × причина). СПАМ исключаем из всего, но
 * считаем отдельно. Чистая функция. */
export function buildSalesRejections(
  rows: MgrReasonRow[],
  wonByMgr: Map<number, number>,
  nameById: Map<number, string>,
  months: SalesRejectionMonth[],
  yearLabel: string,
): SalesRejections {
  const spamExcluded = rows
    .filter((r) => r.reasonId === SPAM_REASON_10)
    .reduce((a, r) => a + r.count, 0);
  const real = rows.filter((r) => r.reasonId !== SPAM_REASON_10);

  // По причинам (отдел).
  const reasonAcc = new Map<number | null, number>();
  for (const r of real) reasonAcc.set(r.reasonId, (reasonAcc.get(r.reasonId) ?? 0) + r.count);
  const totalRejections = [...reasonAcc.values()].reduce((a, b) => a + b, 0);
  const reasons: SalesReasonBucket[] = [...reasonAcc.entries()]
    .map(([reasonId, count]) => ({
      reasonId,
      label: reasonLabel10(reasonId),
      count,
      pct: totalRejections > 0 ? Math.round((count / totalRejections) * 100) : 0,
    }))
    .sort((a, b) => b.count - a.count);

  const lostAmount = real.reduce((a, r) => a + r.amount, 0);

  // По менеджерам.
  const byMgr = new Map<number, { rejections: number; lostAmount: number; reasons: Map<number | null, number> }>();
  for (const r of real) {
    if (r.managerId == null) continue;
    const e = byMgr.get(r.managerId) ?? { rejections: 0, lostAmount: 0, reasons: new Map() };
    e.rejections += r.count;
    e.lostAmount += r.amount;
    e.reasons.set(r.reasonId, (e.reasons.get(r.reasonId) ?? 0) + r.count);
    byMgr.set(r.managerId, e);
  }
  const managers: SalesRejectionManager[] = [...byMgr.entries()]
    .map(([managerId, e]) => {
      const won = wonByMgr.get(managerId) ?? 0;
      const topReasonId = [...e.reasons.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
      return {
        managerId,
        name: nameById.get(managerId) ?? `id ${managerId}`,
        rejections: e.rejections,
        lostAmount: e.lostAmount,
        won,
        lossRate: lossRate(e.rejections, won),
        topReason: e.reasons.size ? reasonLabel10(topReasonId) : null,
      };
    })
    .sort((a, b) => b.rejections - a.rejections);

  const wonTotal = managers.reduce((a, m) => a + m.won, 0);

  return {
    yearLabel,
    totalRejections,
    lostAmount,
    lossRate: lossRate(totalRejections, wonTotal),
    avgLoss: totalRejections > 0 ? Math.round(lostAmount / totalRejections) : 0,
    spamExcluded,
    wonTotal,
    months,
    reasons,
    managers,
  };
}

// ── Запрос ───────────────────────────────────────────────────────────────────

/** Отказы воронки Продажи с начала года до опорного дня. Источник —
 * deal_rejections (наполняет sync_rejections.py), оплаты — manager_activity
 * (deals_won_count, по тому же владельцу). */
export async function getSalesRejections(snapshotDate: string): Promise<SalesRejections> {
  const year = Number(snapshotDate.slice(0, 4));
  const yearStart = `${year}-01-01`;
  const rejAtMsk = sql`(${dealRejections.rejectedAt} AT TIME ZONE 'Europe/Moscow')::date`;
  const inYear = and(
    eq(dealRejections.stageId, SALES_LOSE_STAGE),
    gte(rejAtMsk, yearStart),
    lte(rejAtMsk, snapshotDate),
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
  const rows: MgrReasonRow[] = mgrReasonRows.map((r) => ({
    managerId: r.managerId,
    reasonId: r.reasonId,
    count: Number(r.n),
    amount: Number(r.amount),
  }));

  // Помесячно (с начала года), СПАМ исключён в SQL.
  const ymExpr = sql<string>`to_char((${dealRejections.rejectedAt} AT TIME ZONE 'Europe/Moscow'), 'YYYY-MM')`;
  const monthRows = await db
    .select({ ym: ymExpr, n: sql<number>`count(*)` })
    .from(dealRejections)
    .where(and(inYear, sql`${dealRejections.reasonId} IS DISTINCT FROM ${SPAM_REASON_10}`))
    .groupBy(ymExpr);
  const monthCount = new Map(monthRows.map((r) => [r.ym, Number(r.n)]));
  const lastMonth = Number(snapshotDate.slice(5, 7));
  const months: SalesRejectionMonth[] = [];
  for (let m = 1; m <= lastMonth; m++) {
    const ym = `${year}-${String(m).padStart(2, '0')}`;
    months.push({ ym, label: MONTHS_RU_SHORT[m - 1], count: monthCount.get(ym) ?? 0 });
  }

  // Оплаты (won) по владельцу с начала года — знаменатель «доли отказов».
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

  // Имена.
  const userRows = await db.select({ id: users.bitrixId, name: users.name }).from(users);
  const nameById = new Map(userRows.map((u) => [u.id, u.name]));

  return buildSalesRejections(rows, wonByMgr, nameById, months, String(year));
}
