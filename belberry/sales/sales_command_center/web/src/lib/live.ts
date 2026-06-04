import 'server-only';

import { eq } from 'drizzle-orm';
import { db } from '@/db';
import { liveSnapshot, users } from '@/db/schema';
import { isSalesDept } from './dashboard';

export interface LiveManager {
  managerId: number;
  name: string;
  dials: number;
  answered: number;
  calls120: number;
  meetings: number;
  deals: number;
  kp: number;
}

export interface LiveFeedItem {
  kind: 'meeting' | 'kp' | 'deal';
  manager: string;
  title: string;
  at: string;
}

export interface LiveData {
  updatedAt: string | null;
  reportDate: string | null;
  totals: { dials: number; answered: number; calls120: number; meetings: number; kp: number; deals: number };
  managers: LiveManager[];
  feed: LiveFeedItem[];
}

interface RawManager {
  manager_id: number;
  dials?: number;
  answered?: number;
  calls120?: number;
  meetings?: number;
  deals?: number;
  kp?: number;
}
interface RawFeed {
  kind: 'meeting' | 'kp' | 'deal';
  manager_id: number | null;
  title: string;
  at: string;
}

const EMPTY: LiveData = {
  updatedAt: null,
  reportDate: null,
  totals: { dials: 0, answered: 0, calls120: 0, meetings: 0, kp: 0, deals: 0 },
  managers: [],
  feed: [],
};

export async function getLive(): Promise<LiveData> {
  let rows: { updatedAt: Date | null; reportDate: string | null; payload: unknown }[] = [];
  try {
    rows = await db
      .select({ updatedAt: liveSnapshot.updatedAt, reportDate: liveSnapshot.reportDate, payload: liveSnapshot.payload })
      .from(liveSnapshot)
      .where(eq(liveSnapshot.id, 1))
      .limit(1);
  } catch {
    // Таблица live_snapshot ещё не создана (миграция не применена) — мягко пусто.
    return EMPTY;
  }
  if (!rows[0]?.payload) return EMPTY;

  const payload = rows[0].payload as { managers?: RawManager[]; feed?: RawFeed[] };
  const userRows = await db.select({ id: users.bitrixId, name: users.name, dept: users.dept }).from(users);
  const dir = new Map(userRows.map((u) => [u.id, { name: u.name, dept: u.dept ?? '' }]));

  // Только ОП+ТМ (по должности). Если справочник пуст — показываем всех.
  const all = (payload.managers ?? []).map((m) => ({
    managerId: m.manager_id,
    name: dir.get(m.manager_id)?.name ?? `id ${m.manager_id}`,
    dept: dir.get(m.manager_id)?.dept ?? '',
    dials: m.dials ?? 0,
    answered: m.answered ?? 0,
    calls120: m.calls120 ?? 0,
    meetings: m.meetings ?? 0,
    deals: m.deals ?? 0,
    kp: m.kp ?? 0,
  }));
  const sales = all.filter((m) => isSalesDept(m.dept));
  const shown = sales.length ? sales : all;
  const managers: LiveManager[] = shown.map((m) => ({
    managerId: m.managerId,
    name: m.name,
    dials: m.dials,
    answered: m.answered,
    calls120: m.calls120,
    meetings: m.meetings,
    deals: m.deals,
    kp: m.kp,
  }));

  const totals = managers.reduce(
    (a, m) => ({
      dials: a.dials + m.dials,
      answered: a.answered + m.answered,
      calls120: a.calls120 + m.calls120,
      meetings: a.meetings + m.meetings,
      kp: a.kp + m.kp,
      deals: a.deals + m.deals,
    }),
    { dials: 0, answered: 0, calls120: 0, meetings: 0, kp: 0, deals: 0 },
  );

  const feed: LiveFeedItem[] = (payload.feed ?? []).map((e) => ({
    kind: e.kind,
    manager: e.manager_id ? (dir.get(e.manager_id)?.name ?? `id ${e.manager_id}`) : '—',
    title: e.title,
    at: e.at,
  }));

  return {
    updatedAt: rows[0].updatedAt ? new Date(rows[0].updatedAt).toISOString() : null,
    reportDate: rows[0].reportDate ? String(rows[0].reportDate) : null,
    totals,
    managers,
    feed,
  };
}
