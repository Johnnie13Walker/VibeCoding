// Типы и чистые функции дашборда телемаркетинга — БЕЗ server-only, чтобы
// переиспользовать и в серверной загрузке (telemarketing.ts), и в компонентах.
//
// Канон проекта: дозвон = разговор ≥60 секунд; встреча «назначено» атрибутируется
// создателю (телемаркетологу); scope ТМ = должность содержит «телемаркет» —
// имена НЕ хардкодим, новый звонарь подхватывается автоматически.

export type Cat50Kind = 'open' | 'win' | 'lose';

export interface Stage50Meta {
  label: string;
  order: number;
  kind: Cat50Kind;
}

/** Стадии воронки [50] «Телемаркетинг» (crm.dealcategory.stage.list id=50). */
export const STAGE_META_50: Record<string, Stage50Meta> = {
  'C50:UC_1S1KIU': { label: 'База', order: 1, kind: 'open' },
  'C50:NEW': { label: 'К обзвону', order: 2, kind: 'open' },
  'C50:PREPARATION': { label: 'Взято в работу', order: 3, kind: 'open' },
  'C50:UC_WZ4KQE': { label: 'Встреча назначена', order: 4, kind: 'open' },
  'C50:WON': { label: 'Успех', order: 5, kind: 'win' },
  'C50:LOSE': { label: 'Отложено', order: 6, kind: 'lose' },
  'C50:APOLOGY': { label: 'Отвал', order: 7, kind: 'lose' },
};

/** ТМ-сотрудник = должность содержит «телемаркет». Дубль из dashboard.ts,
 * чтобы не тянуть server-only в client-safe модуль. */
export function isTelemarketing(dept: string | null | undefined): boolean {
  return !!dept && /телемаркет/i.test(dept);
}

/** Агрегаты активности одного ТМ-сотрудника за период (из manager_activity). */
export interface TmMember {
  managerId: number;
  name: string;
  dials: number;
  answered: number;
  calls60: number;
  calls120: number;
  talkSeconds: number;
  meetingsSet: number;
  meetingsHeld: number;
  dealsCold: number;
  messenger: number;
  emails: number;
}

const pct1 = (a: number, b: number): number | null =>
  b > 0 ? Math.round((a / b) * 1000) / 10 : null;

// ───────────────────────── KPI отдела ─────────────────────────

export interface TmKpis {
  zvonari: number;
  dials: number;
  answered: number;
  /** % взятых трубок = снято / набрано. */
  answerPct: number | null;
  calls60: number;
  calls120: number;
  talkHours: number;
  meetingsSet: number;
  meetingsHeld: number;
  /** Конверсия дозвон→встреча = назначено / дозвоны ≥60с, %. */
  convDialToMeeting: number | null;
  toCold: number;
  dialsPerZvonar: number;
  dialsPerDay: number;
  calls60PerZvonar: number;
  calls60PerDay: number;
}

/** Сводные KPI обзвона по всем ТМ за период. Чистая функция. */
export function buildTmKpis(members: TmMember[], workingDays: number): TmKpis {
  const z = Math.max(1, members.length);
  const wd = Math.max(1, workingDays);
  const sum = (k: keyof TmMember) => members.reduce((a, m) => a + (m[k] as number), 0);
  const dials = sum('dials');
  const answered = sum('answered');
  const calls60 = sum('calls60');
  const calls120 = sum('calls120');
  const meetingsSet = sum('meetingsSet');
  const talkHours = Math.round((sum('talkSeconds') / 3600) * 10) / 10;
  return {
    zvonari: members.length,
    dials,
    answered,
    answerPct: pct1(answered, dials),
    calls60,
    calls120,
    talkHours,
    meetingsSet,
    meetingsHeld: sum('meetingsHeld'),
    convDialToMeeting: pct1(meetingsSet, calls60),
    toCold: sum('dealsCold'),
    dialsPerZvonar: Math.round(dials / z),
    dialsPerDay: Math.round(dials / wd),
    calls60PerZvonar: Math.round(calls60 / z),
    calls60PerDay: Math.round(calls60 / wd),
  };
}

// ───────────────────────── По звонарям ─────────────────────────

export interface TmManagerRow {
  managerId: number;
  name: string;
  dials: number;
  answered: number;
  answerPct: number | null;
  calls60: number;
  talkHours: number;
  meetingsSet: number;
  meetingsHeld: number;
  /** Конверсия дозвон→встреча, %. */
  convDialToMeeting: number | null;
}

/** Таблица по звонарям, сортировка по наборам. Чистая функция. */
export function buildTmManagerTable(members: TmMember[]): TmManagerRow[] {
  return members
    .map((m) => ({
      managerId: m.managerId,
      name: m.name,
      dials: m.dials,
      answered: m.answered,
      answerPct: pct1(m.answered, m.dials),
      calls60: m.calls60,
      talkHours: Math.round((m.talkSeconds / 3600) * 10) / 10,
      meetingsSet: m.meetingsSet,
      meetingsHeld: m.meetingsHeld,
      convDialToMeeting: pct1(m.meetingsSet, m.calls60),
    }))
    .sort((a, b) => b.dials - a.dials);
}

// ───────────────────── Микро-воронка звонка ─────────────────────

export interface MicroStep {
  label: string;
  value: number;
  /** Конверсия из предыдущего шага, % (null для первого). */
  pctFromPrev: number | null;
}

export interface TmMicroFunnel {
  managerId: number;
  name: string;
  steps: MicroStep[];
}

/** Набрал → снял трубку → дозвон ≥60с → встреча, с % потерь. Чистая функция. */
export function buildTmMicroFunnel(m: TmMember): TmMicroFunnel {
  const raw: [string, number][] = [
    ['Набрал', m.dials],
    ['Снял трубку', m.answered],
    ['Дозвон ≥60с', m.calls60],
    ['Встреча', m.meetingsSet],
  ];
  return {
    managerId: m.managerId,
    name: m.name,
    steps: raw.map(([label, value], i) => ({
      label,
      value,
      pctFromPrev: i === 0 ? null : pct1(value, raw[i - 1][1]),
    })),
  };
}

// ───────────────────────── Воронка cat50 ─────────────────────────

export interface TmFunnel50Stage {
  stage: string;
  label: string;
  kind: Cat50Kind;
  count: number;
}

/** Снимок ТМ-воронки [50] по стадиям. Чистая функция. */
export function buildTmFunnel50(cells: { stage: string }[]): TmFunnel50Stage[] {
  const counts = new Map<string, number>();
  for (const c of cells) {
    if (!STAGE_META_50[c.stage]) continue;
    counts.set(c.stage, (counts.get(c.stage) ?? 0) + 1);
  }
  return Object.entries(STAGE_META_50)
    .sort((a, b) => a[1].order - b[1].order)
    .map(([stage, meta]) => ({
      stage,
      label: meta.label,
      kind: meta.kind,
      count: counts.get(stage) ?? 0,
    }));
}

// ───────────────────── Помесячная динамика ─────────────────────

export interface TmMonthlyInput {
  ym: string;
  label: string;
  dials: number;
  answered: number;
  calls60: number;
  talkSeconds: number;
  meetingsSet: number;
  meetingsHeld: number;
}

export interface TmMonthlyRow {
  ym: string;
  label: string;
  dials: number;
  answered: number;
  answerPct: number | null;
  calls60: number;
  talkMin: number;
  meetingsSet: number;
  meetingsHeld: number;
  conv: number | null;
}

/** Помесячные строки по выбранному звонарю + производные. Чистая функция. */
export function buildTmMonthly(rows: TmMonthlyInput[]): TmMonthlyRow[] {
  return rows.map((r) => ({
    ym: r.ym,
    label: r.label,
    dials: r.dials,
    answered: r.answered,
    answerPct: pct1(r.answered, r.dials),
    calls60: r.calls60,
    talkMin: Math.round(r.talkSeconds / 60),
    meetingsSet: r.meetingsSet,
    meetingsHeld: r.meetingsHeld,
    conv: pct1(r.meetingsSet, r.calls60),
  }));
}

// ───────────────────── Встречи → результат ─────────────────────

export interface TmMeetingsResult {
  set: number;
  held: number;
  /** % проведённых от назначенных. */
  heldPct: number | null;
  toCold: number;
}

export function buildTmMeetingsResult(members: TmMember[]): TmMeetingsResult {
  const set = members.reduce((a, m) => a + m.meetingsSet, 0);
  const held = members.reduce((a, m) => a + m.meetingsHeld, 0);
  return {
    set,
    held,
    heldPct: pct1(held, set),
    toCold: members.reduce((a, m) => a + m.dealsCold, 0),
  };
}

// ───────────────────────── План / факт ─────────────────────────

export interface TmPlanFactRow {
  label: string;
  fact: number;
  plan: number;
  /** Выполнение, %. */
  pct: number;
  /** Единица для подписи (например, «встреч/ТМ»). */
  unit?: string;
}

export interface TmPlanFactInput {
  meetingsSetFact: number;
  meetingsPlanPerTm: number;
  tmCount: number;
}

/** План/факт ТМ. Сейчас — встречи (план из «Плана оплат»). Чистая функция. */
export function buildTmPlanFact(i: TmPlanFactInput): TmPlanFactRow[] {
  const planMeetings = i.meetingsPlanPerTm * Math.max(1, i.tmCount);
  const rows: TmPlanFactRow[] = [];
  if (i.meetingsPlanPerTm > 0) {
    rows.push({
      label: 'Встречи назначено',
      fact: i.meetingsSetFact,
      plan: planMeetings,
      pct: planMeetings > 0 ? Math.round((i.meetingsSetFact / planMeetings) * 100) : 0,
      unit: `план ${i.meetingsPlanPerTm}/ТМ × ${Math.max(1, i.tmCount)}`,
    });
  }
  return rows;
}

// ───────────────────────── Outreach ─────────────────────────

export interface TmOutreachRow {
  managerId: number;
  name: string;
  messenger: number;
  emails: number;
}

export interface TmOutreach {
  messengerTotal: number;
  emailTotal: number;
  rows: TmOutreachRow[];
}

/** Мессенджер/почта по звонарям. Чистая функция. */
export function buildTmOutreach(members: TmMember[]): TmOutreach {
  const rows = members
    .map((m) => ({ managerId: m.managerId, name: m.name, messenger: m.messenger, emails: m.emails }))
    .filter((r) => r.messenger > 0 || r.emails > 0)
    .sort((a, b) => b.messenger - a.messenger || b.emails - a.emails);
  return {
    messengerTotal: rows.reduce((a, r) => a + r.messenger, 0),
    emailTotal: rows.reduce((a, r) => a + r.emails, 0),
    rows,
  };
}

// ───────────────────── Композит для страницы ─────────────────────

export interface TmManagerOption {
  managerId: number;
  name: string;
}

export interface TmDashboardData {
  monthLabel: string;
  periodLabel: string;
  snapshotDate: string | null;
  workingDays: number;
  managers: TmManagerOption[];
  selectedManagerId: number | null;
  selectedManagerName: string | null;
  kpis: TmKpis;
  table: TmManagerRow[];
  funnel50: TmFunnel50Stage[];
  meetingsResult: TmMeetingsResult;
  monthly: TmMonthlyRow[];
  microFunnels: TmMicroFunnel[];
  planFact: TmPlanFactRow[];
  outreach: TmOutreach;
  generatedAt: string | null;
}
