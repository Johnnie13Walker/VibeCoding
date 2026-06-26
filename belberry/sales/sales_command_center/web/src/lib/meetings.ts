import 'server-only';

import { and, eq, gte, inArray, sql } from 'drizzle-orm';
import { db } from '@/db';
import { dealsSnapshot, dealTitles, meetings, users } from '@/db/schema';
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
  products_discussed?: string[];
  kp_assessment?: string | null;
  kp_assessment_note?: string | null;
  client_needs?: { need?: string; pain?: string; evidence?: string }[];
  decision_makers?: string | null;
  current_situation?: string | null;
  budget_signals?: string | null;
  dialog_quality?: string | null;
  cases_mentioned?: { client?: string; service?: string | null; result?: string | null; quote?: string | null }[];
  niches_claimed?: string[];
  coaching?: string | null;
  key_quotes?: string[];
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
      status: meetings.status,
      analysisStatus: meetings.analysisStatus,
    })
    .from(meetings)
    // Только ПРОВЕДЁННЫЕ встречи, ОДНА строка на встречу. В meetings теперь две
    // строки на встречу (назначение под датой создания + проведение под датой
    // встречи) ради архива «Встречи назначены». Берём строку-ПРОВЕДЕНИЕ: статус
    // SUCCESS И дата встречи = дата отчёта (date(scheduled)=report_date) — это
    // убирает дубль (у строки-назначения дата встречи ≠ report_date).
    .where(and(
      gte(meetings.reportDate, cutoff),
      eq(meetings.status, 'DT1048_24:SUCCESS'),
      sql`date(${meetings.scheduledAt} at time zone 'Europe/Moscow') = ${meetings.reportDate}`,
    ))
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
    // deals_snapshot хранит только открытые сделки → у закрытых название добираем
    // из справочника deal_titles (наполняется sync_deal_titles.py из Bitrix).
    const missing = dealIds.filter((id) => !titleMap.has(id));
    if (missing.length) {
      const dtRows = await db
        .select({ dealId: dealTitles.dealId, title: dealTitles.title })
        .from(dealTitles)
        .where(inArray(dealTitles.dealId, missing));
      for (const t of dtRows) if (t.title) titleMap.set(t.dealId, t.title);
    }
  }

  const out: MeetingItem[] = [];
  for (const r of rows) {
    if (r.managerId == null) continue;
    const u = userMap.get(r.managerId);
    if (!u || !isOpRop(u.dept)) continue;
    // Только продажные встречи: брифинг и защита КП. «Другое» / «Передача проекта»
    // (meeting_type='other') не про продажи — не анализируем и не показываем здесь.
    if (r.type !== 'briefing' && r.type !== 'defense') continue;
    // Исключённые вручную (встреча про другое) не показываем и не анализируем.
    if (r.analysisStatus === 'skipped_manual') continue;

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
      note: r.analysisStatus === 'no_record' ? 'Не было записи и транскрипции' : null,
      summarySent: typeof a?.summary_sent === 'boolean' ? a.summary_sent : null,
      budgetNamed: typeof a?.budget_named === 'boolean' ? a.budget_named : null,
      products: Array.isArray(a?.products_discussed) ? a!.products_discussed!.map(String) : [],
      kpAssessment: (a?.kp_assessment as MeetingItem['kpAssessment']) ?? null,
      kpAssessmentNote: (a?.kp_assessment_note ?? '').toString().trim(),
      clientNeeds: Array.isArray(a?.client_needs)
        ? a!.client_needs!.filter((n) => n?.need).map((n) => ({ need: String(n.need), pain: String(n.pain ?? ''), evidence: String(n.evidence ?? '') }))
        : [],
      decisionMakers: (a?.decision_makers ?? '').toString().trim(),
      currentSituation: (a?.current_situation ?? '').toString().trim(),
      budgetSignals: (a?.budget_signals ?? '').toString().trim(),
      dialogQuality: (a?.dialog_quality ?? '').toString().trim(),
      // Кейсы известны только у разборов с новым полем: array → знаем (даже []), undefined → старый разбор (блок не показываем).
      cases: Array.isArray(a?.cases_mentioned)
        ? a!.cases_mentioned!.filter((c) => c?.client).map((c) => ({ client: String(c.client), service: c.service ? String(c.service) : '', result: c.result ? String(c.result) : '', quote: c.quote ? String(c.quote) : '' }))
        : null,
      niches: Array.isArray(a?.niches_claimed) ? a!.niches_claimed!.map(String).filter(Boolean) : [],
      coaching: (a?.coaching ?? '').toString().trim(),
      keyQuotes: Array.isArray(a?.key_quotes) ? a!.key_quotes!.map(String) : [],
    });
  }
  return out;
}
