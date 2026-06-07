// Типы и чистые функции анализа встреч — БЕЗ server-only, чтобы импортировать
// и в серверной загрузке (meetings.ts), и в клиентском компоненте (MeetingsView).

export type TranscriptStatus = 'ok' | 'no_transcript';

export interface MeetingObs {
  text: string;
  metric?: string;
}

export interface MeetingItem {
  id: number;
  date: string;
  time: string;
  managerId: number;
  manager: string;
  type: 'briefing' | 'defense' | 'other' | null;
  domain: string;
  dealId: number | null;
  score: number | null;
  good: MeetingObs[];
  risk: MeetingObs[];
  verdict: string;
  conclusion: string;
  nextStep: { what?: string; who?: string; deadline?: string } | null;
  transcript: TranscriptStatus;
  /** Итоги клиенту отправлены (по пост-встречной переписке). null = не вычислено. */
  summarySent: boolean | null;
  /** Бюджет назван. null = не вычислено. */
  budgetNamed: boolean | null;
  /** Продукты/услуги, обсуждённые на встрече. */
  products: string[];
  /** Оценка обоснованности КП: обоснованно | преждевременно | не_применимо. */
  kpAssessment: 'обоснованно' | 'преждевременно' | 'не_применимо' | null;
  kpAssessmentNote: string;
  // Глубокий разбор:
  clientNeeds: { need: string; pain: string; evidence: string }[];
  decisionMakers: string;
  currentSituation: string;
  budgetSignals: string;
  dialogQuality: string;
  coaching: string;
  keyQuotes: string[];
}

export interface ManagerScore {
  managerId: number;
  name: string;
  count: number;
  avg: number | null;
  briefingAvg: number | null;
  defenseAvg: number | null;
  summaryPct: number | null;
  budgetPct: number | null;
  nextStepPct: number;
  gaps: number;
}

const avg = (arr: number[]): number | null =>
  arr.length ? Math.round((arr.reduce((a, b) => a + b, 0) / arr.length) * 10) / 10 : null;
const pct = (arr: (boolean | null)[]): number | null => {
  const known = arr.filter((x): x is boolean => x !== null);
  return known.length ? Math.round((known.filter(Boolean).length / known.length) * 100) : null;
};

/** Рейтинг менеджеров по среднему баллу встреч. Чистая функция — тестируема. */
export function buildManagerScores(items: MeetingItem[]): ManagerScore[] {
  const by = new Map<number, MeetingItem[]>();
  for (const m of items) {
    const arr = by.get(m.managerId) ?? [];
    arr.push(m);
    by.set(m.managerId, arr);
  }
  return [...by.entries()]
    .map(([managerId, ms]) => {
      const scored = ms.filter((m) => m.score != null).map((m) => m.score as number);
      return {
        managerId,
        name: ms[0].manager,
        count: ms.length,
        avg: avg(scored),
        briefingAvg: avg(ms.filter((m) => m.type === 'briefing' && m.score != null).map((m) => m.score as number)),
        defenseAvg: avg(ms.filter((m) => m.type === 'defense' && m.score != null).map((m) => m.score as number)),
        summaryPct: pct(ms.map((m) => m.summarySent)),
        budgetPct: pct(ms.map((m) => m.budgetNamed)),
        nextStepPct: ms.length ? Math.round((ms.filter((m) => m.nextStep).length / ms.length) * 100) : 0,
        gaps: ms.filter((m) => m.transcript !== 'ok').length,
      };
    })
    .sort((a, b) => (b.avg ?? -1) - (a.avg ?? -1));
}
