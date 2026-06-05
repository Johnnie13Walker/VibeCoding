import 'server-only';

import { eq } from 'drizzle-orm';
import { db } from '@/db';
import { liveChats, liveSnapshot, users } from '@/db/schema';
import { isSalesDept } from './dashboard';

export interface LiveManager {
  managerId: number;
  name: string;
  dials: number;
  answered: number;
  calls60: number;
  chats: number;
  meetings: number;
  mHeld: number;
  mScheduled: number;
  mCancelled: number;
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
  status: 'held' | 'scheduled' | 'cancelled';
  dealId: number | null;
  setToday: boolean;
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
  chatsUpdatedAt: string | null;
  reportDate: string | null;
  totals: { dials: number; answered: number; calls60: number; chats: number; meetings: number; meetingsHeld: number; meetingsScheduled: number; meetingsCancelled: number; briefs: number; kp: number; deals: number; dealsSpam: number; emails: number };
  managers: LiveManager[];
  meetings: LiveMeeting[];
  briefs: LiveBrief[];
  feed: LiveFeedItem[];
}

interface RawManager {
  manager_id: number;
  dials?: number; answered?: number; calls60?: number; meetings?: number;
  m_held?: number; m_scheduled?: number; m_cancelled?: number;
  briefs?: number; kp?: number; deals?: number; emails?: number;
}
interface RawMeeting { id: number | null; title: string; manager_id: number | null; at: string; status: LiveMeeting['status']; deal_id: number | null; set_today?: boolean }
interface RawBrief { id: number | null; title: string; manager_id: number | null; deal_id: number | null; service: string }
interface RawFeed { kind: LiveFeedItem['kind']; manager_id: number | null; title: string; at: string }

const EMPTY: LiveData = {
  updatedAt: null, chatsUpdatedAt: null, reportDate: null,
  totals: { dials: 0, answered: 0, calls60: 0, chats: 0, meetings: 0, meetingsHeld: 0, meetingsScheduled: 0, meetingsCancelled: 0, briefs: 0, kp: 0, deals: 0, dealsSpam: 0, emails: 0 },
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
    totals?: { deals_spam?: number };
  };
  const userRows = await db.select({ id: users.bitrixId, name: users.name, dept: users.dept }).from(users);
  const dir = new Map(userRows.map((u) => [u.id, { name: u.name, dept: u.dept ?? '' }]));
  const nameOf = (id: number | null) => (id ? (dir.get(id)?.name ?? `id ${id}`) : '—');

  const all = (payload.managers ?? []).map((m) => ({
    managerId: m.manager_id,
    name: nameOf(m.manager_id),
    dept: dir.get(m.manager_id)?.dept ?? '',
    dials: m.dials ?? 0, answered: m.answered ?? 0, calls60: m.calls60 ?? 0,
    meetings: m.meetings ?? 0, mHeld: m.m_held ?? 0, mScheduled: m.m_scheduled ?? 0, mCancelled: m.m_cancelled ?? 0,
    briefs: m.briefs ?? 0, kp: m.kp ?? 0, deals: m.deals ?? 0, emails: m.emails ?? 0,
  }));
  const sales = all.filter((m) => isSalesDept(m.dept));
  const shown = sales.length ? sales : all;
  const salesIds = new Set(shown.map((m) => m.managerId));
  const keep = (mid: number | null) => sales.length === 0 || (mid != null && salesIds.has(mid));

  // Wazzup-чаты — отдельный часовой снимок live_chats (мягко, если таблицы нет).
  let chatsMap = new Map<number, number>();
  let chatsUpdatedAt: string | null = null;
  try {
    const cr = await db
      .select({ updatedAt: liveChats.updatedAt, payload: liveChats.payload })
      .from(liveChats)
      .where(eq(liveChats.id, 1))
      .limit(1);
    if (cr[0]?.payload) {
      const cp = cr[0].payload as { managers?: Record<string, number> };
      chatsMap = new Map(Object.entries(cp.managers ?? {}).map(([k, v]) => [Number(k), Number(v)]));
      chatsUpdatedAt = cr[0].updatedAt ? new Date(cr[0].updatedAt).toISOString() : null;
    }
  } catch {
    /* live_chats ещё не создана */
  }

  const managers: LiveManager[] = shown.map((m) => ({
    managerId: m.managerId, name: m.name, dials: m.dials, answered: m.answered,
    calls60: m.calls60, chats: chatsMap.get(m.managerId) ?? 0, meetings: m.meetings,
    mHeld: m.mHeld, mScheduled: m.mScheduled, mCancelled: m.mCancelled,
    briefs: m.briefs, kp: m.kp, emails: m.emails,
  }));

  const meetings: LiveMeeting[] = (payload.meetings_list ?? [])
    .filter((m) => keep(m.manager_id))
    .map((m) => ({ id: m.id, title: m.title, manager: nameOf(m.manager_id), at: m.at, status: m.status ?? 'scheduled', dealId: m.deal_id, setToday: m.set_today ?? false }));

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
    briefs: briefs.length,
    chats: shown.reduce((s, m) => s + (chatsMap.get(m.managerId) ?? 0), 0),
    meetingsHeld: shown.reduce((s, m) => s + m.mHeld, 0),
    meetingsScheduled: shown.reduce((s, m) => s + m.mScheduled, 0),
    meetingsCancelled: shown.reduce((s, m) => s + m.mCancelled, 0),
    kp: shown.reduce((s, m) => s + m.kp, 0),
    deals: shown.reduce((s, m) => s + m.deals, 0),
    dealsSpam: payload.totals?.deals_spam ?? 0,
    emails: shown.reduce((s, m) => s + m.emails, 0),
  };

  return {
    updatedAt: rows[0].updatedAt ? new Date(rows[0].updatedAt).toISOString() : null,
    chatsUpdatedAt,
    reportDate: rows[0].reportDate ? String(rows[0].reportDate) : null,
    totals, managers, meetings, briefs, feed,
  };
}
