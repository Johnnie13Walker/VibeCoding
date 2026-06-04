import 'server-only';

import { and, gte, isNotNull, lte, sql } from 'drizzle-orm';
import { db } from '@/db';
import { reports } from '@/db/schema';

const TIGER_RE = /class="tiger-name">([^<]+?)\s*(?:<|$)/;

const MONTHS_RU = [
  'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
  'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
];

export interface TigerLeader {
  name: string;
  count: number;
}

export interface TigerStats {
  monthLabel: string;
  days: number; // отчётных дней в месяце с распознанным тигром
  leaders: TigerLeader[];
}

const EMPTY: TigerStats = { monthLabel: '', days: 0, leaders: [] };

/** Лидерборд «Тигров дня» за месяц последнего отчёта (парсим из HTML — без новых данных). */
export async function getTigerStats(): Promise<TigerStats> {
  let latest: { d: string | null }[] = [];
  try {
    latest = await db.select({ d: sql<string>`max(${reports.reportDate})` }).from(reports);
  } catch {
    return EMPTY;
  }
  const snapshot = latest[0]?.d;
  if (!snapshot) return EMPTY;

  const [y, m] = snapshot.split('-').map(Number);
  const start = `${y}-${String(m).padStart(2, '0')}-01`;
  const lastDay = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const end = `${y}-${String(m).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`;

  const rows = await db
    .select({ html: reports.html })
    .from(reports)
    .where(and(gte(reports.reportDate, start), lte(reports.reportDate, end), isNotNull(reports.html)));

  const counts = new Map<string, number>();
  let days = 0;
  for (const r of rows) {
    const match = r.html ? TIGER_RE.exec(r.html) : null;
    const name = match?.[1]?.trim();
    if (!name) continue;
    days += 1;
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }

  const leaders = Array.from(counts.entries())
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));

  return { monthLabel: `${MONTHS_RU[m - 1]} ${y}`, days, leaders };
}
