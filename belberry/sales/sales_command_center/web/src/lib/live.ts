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
  calls60: number;
  meetings: number;
  briefs: number;
  kp: number;
  emails: number;
}

export interface LiveFeedItem {
  kind: 'meeting' | 'brief' | 'kp' | 'deal';
  manager: string;
  title: string;
  at: string;
}

export interface LiveMeeting {
  id: number | null;
  title: string;
  manager: string;
  at: string;
  done: boolean;
  dealId: number | null;
}

export interface LiveBrief {
  id: number | null;
  title: string;
  manager: string;
  dealId: number | null;
  service: string;
}

export interface LiveData {
  updatedAt: string | null;
  reportDate: string | null;
  totals: { dials: number; answered: number; calls60: number; meetings: number; meetingsDone: number; briefs: number; kp: number; deals: number; emails: number };
  managers: LiveManager[];
  meetings: LiveMeeting[];
  briefs: LiveBrief[];
  feed: LiveFeedItem[];
}

interface RawManager {
  manager_id: number;
  dials?: number; answered?: number; calls60?: number; meetings?: number; briefs?: number; kp?: number; deals?: number; emails?: number;
}
interface RawMeeting { id: number | null; title: string; manager_id: number | null; at: string; done: boolean; deal_id: number | null }
interface RawBrief { id: number | null; title: string; manager_id: number | null; deal_id: number | null; service: string }
interface RawFeed { kind: LiveFeedItem['kind']; manager_id: number | null; title: string; at: string }

const EMPTY: LiveData = {
  updatedAt: null, reportDate: null,
  totals: { dials: 0, answered: 0, calls60: 0, meetings: 0, meetingsDone: 0, briefs: 0, kp: 0, deals: 0, emails: 0 },
  managers: [], meetings: [], briefs: [], feed: [],
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
    return EMPTY;
  }
  if (!rows[0]?.payload) return EMPTY;

  const payload = rows[0].payload as {
    managers?: RawManager[]; meetings_list?: RawMeeting[]; briefs_list?: RawBrief[]; feed?: RawFeed[];
  };
  const userRows = await db.select({ id: users.bitrixId, name: users.name, dept: users.dept }).from(users);
  const dir = new Map(userRows.map((u) => [u.id, { name: u.name, dept: u.dept ?? '' }]));
  const nameOf = (id: number | null) => (id ? (dir.get(id)?.name ?? `id ${id}`) : '—');

  const all = (payload.managers ?? []).map((m) => ({
    managerId: m.manager_id,
    name: nameOf(m.manager_id),
    dept: dir.get(m.manager_id)?.dept ?? '',
    dials: m.dials ?? 0, answered: m.answered ?? 0, calls60: m.calls60 ?? 0,
    meetings: m.meetings ?? 0, briefs: m.briefs ?? 0, kp: m.kp ?? 0, deals: m.deals ?? 0, emails: m.emails ?? 0,
  }));
  const sales = all.filter((m) => isSalesDept(m.dept));
  const shown = sales.length ? sales : all;
  const salesIds = new Set(shown.map((m) => m.managerId));
  const keep = (mid: number | null) => sales.length === 0 || (mid != null && salesIds.has(mid));

  const managers: LiveManager[] = shown.map((m) => ({
    managerId: m.managerId, name: m.name, dials: m.dials, answered: m.answered,
    calls60: m.calls60, meetings: m.meetings, briefs: m.briefs, kp: m.kp, emails: m.emails,
  }));

  const meetings: LiveMeeting[] = (payload.meetings_list ?? [])
    .filter((m) => keep(m.manager_id))
    .map((m) => ({ id: m.id, title: m.title, manager: nameOf(m.manager_id), at: m.at, done: m.done, dealId: m.deal_id }));

  const briefs: LiveBrief[] = (payload.briefs_list ?? [])
    .filter((b) => keep(b.manager_id))
    .map((b) => ({ id: b.id, title: b.title, manager: nameOf(b.manager_id), dealId: b.deal_id, service: b.service }));

  const feed: LiveFeedItem[] = (payload.feed ?? [])
    .filter((e) => keep(e.manager_id))
    .map((e) => ({ kind: e.kind, manager: nameOf(e.manager_id), title: e.title, at: e.at }));

  const totals = {
    dials: shown.reduce((s, m) => s + m.dials, 0),
    answered: shown.reduce((s, m) => s + m.answered, 0),
    calls60: shown.reduce((s, m) => s + m.calls60, 0),
    meetings: meetings.length,
    meetingsDone: meetings.filter((m) => m.done).length,
    briefs: briefs.length,
    kp: shown.reduce((s, m) => s + m.kp, 0),
    deals: shown.reduce((s, m) => s + m.deals, 0),
    emails: shown.reduce((s, m) => s + m.emails, 0),
  };

  return {
    updatedAt: rows[0].updatedAt ? new Date(rows[0].updatedAt).toISOString() : null,
    reportDate: rows[0].reportDate ? String(rows[0].reportDate) : null,
    totals, managers, meetings, briefs, feed,
  };
}
