import 'server-only';

import { gte, inArray, sql } from 'drizzle-orm';
import { db } from '@/db';
import { dealsSnapshot, meetings, users } from '@/db/schema';
import { isSalesDept, isTelemarketing } from './dashboard';
import type { MeetingItem, TranscriptStatus } from './meetings-shared';

export type { MeetingItem, ManagerScore, MeetingObs, TranscriptStatus } from './meetings-shared';
export { buildManagerScores } from './meetings-shared';

function timeMsk(iso: string | Date | null): string {
  if (!iso) return '';
  try {
    return new Intl.DateTimeFormat('ru-RU', {
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'Europe/Moscow',
    }).format(new Date(iso));
  } catch {
    return '';
  }
}

interface RawAnalysis {
  score?: number;
  observations?: { kind?: string; text?: string; metric?: string | null }[];
  verdict?: string;
  systemic_conclusion?: string;
  next_step?: { what?: string; who?: string; deadline?: string } | null;
  next_steps?: unknown[];
  summary_sent?: boolean;
  budget_named?: boolean;
}

/** Загрузка разобранных встреч ОП+РОП за окно (по умолчанию 120 дней). */
export async function getMeetingsForAnalysis(days = 120): Promise<MeetingItem[]> {
  const cutoff = new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10);

  const userRows = await db.select({ id: users.bitrixId, name: users.name, dept: users.dept }).from(users);
  const userMap = new Map(userRows.map((u) => [u.id, { name: u.name, dept: u.dept ?? '' }]));
  // ОП + РОП = отдел продаж, но НЕ телемаркетинг (ТМ встреч не проводит).
  const isOpRop = (dept: string) => isSalesDept(dept) && !isTelemarketing(dept);

  const rows = await db
    .select({
      id: meetings.meetingId,
      reportDate: meetings.reportDate,
      dealId: meetings.dealId,
      type: meetings.meetingType,
      managerId: meetings.managerId,
      scheduledAt: meetings.scheduledAt,
      analysis: meetings.analysisJson,
      transcriptOk: meetings.transcriptOk,
      transcriptUrl: meetings.transcriptUrl,
    })
    .from(meetings)
    .where(gte(meetings.reportDate, cutoff))
    .orderBy(sql`${meetings.reportDate} desc`);

  const dealIds = [...new Set(rows.map((r) => r.dealId).filter((x): x is number => x != null))];
  const titleMap = new Map<number, string>();
  if (dealIds.length) {
    const titleRows = await db
      .select({ dealId: dealsSnapshot.dealId, title: dealsSnapshot.title, d: dealsSnapshot.reportDate })
      .from(dealsSnapshot)
      .where(inArray(dealsSnapshot.dealId, dealIds))
      .orderBy(sql`${dealsSnapshot.reportDate} desc`);
    for (const t of titleRows) {
      if (t.title && !titleMap.has(t.dealId)) titleMap.set(t.dealId, t.title);
    }
  }

  const out: MeetingItem[] = [];
  for (const r of rows) {
    if (r.managerId == null) continue;
    const u = userMap.get(r.managerId);
    if (!u || !isOpRop(u.dept)) continue;

    const a = (r.analysis ?? null) as RawAnalysis | null;
    const analyzed = a != null && typeof a.score === 'number';
    const obs = a?.observations ?? [];
    const good = obs.filter((o) => o.kind === 'good' && o.text).map((o) => ({ text: o.text as string, metric: o.metric ?? undefined }));
    const risk = obs.filter((o) => o.kind === 'risk' && o.text).map((o) => ({ text: o.text as string, metric: o.metric ?? undefined }));
    const transcript: TranscriptStatus = analyzed || r.transcriptOk === true ? 'ok' : 'no_transcript';

    out.push({
      id: r.id,
      date: String(r.reportDate),
      time: timeMsk(r.scheduledAt),
      managerId: r.managerId,
      manager: u.name,
      type: (r.type as MeetingItem['type']) ?? null,
      domain: (r.dealId && titleMap.get(r.dealId)) || (r.dealId ? `Сделка #${r.dealId}` : 'Без сделки'),
      dealId: r.dealId,
      score: analyzed ? (a!.score as number) : null,
      good,
      risk,
      verdict: (a?.verdict ?? '').toString().trim(),
      conclusion: (a?.systemic_conclusion ?? '').toString().trim(),
      nextStep: a?.next_step ?? null,
      transcript,
      summarySent: typeof a?.summary_sent === 'boolean' ? a.summary_sent : null,
      budgetNamed: typeof a?.budget_named === 'boolean' ? a.budget_named : null,
    });
  }
  return out;
}
