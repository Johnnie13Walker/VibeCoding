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
  /** Должность из справочника (для подписи в таблице). */
  dept: string;
  dials: number;
  answered: number;
  calls60: number;
  calls120: number;
  talkSeconds: number;
  meetingsSet: number;
  /** Состоявшиеся встречи, назначенные этим ТМ (held по createdBy). Событийная метрика. */
  meetingsHeldByCreator: number;
  /** Состоявшиеся БРИФования, назначенные этим ТМ (held + type=briefing по createdBy). */
  briefingsHeldByCreator: number;
  /** Личные отвалы (C50:APOLOGY, закрыл сам) за период — для «сжигания базы». */
  rejectionsPeriod: number;
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
  /** Состоялось — встречи от ТМ, прошедшие по бизнес-процессу (held по создателю). */
  meetingsHeld: number;
  /** Явка = состоялось / назначено, %. */
  heldPct: number | null;
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
  const meetingsHeld = sum('meetingsHeldByCreator');
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
    meetingsHeld,
    heldPct: pct1(meetingsHeld, meetingsSet),
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
  dept: string;
  dials: number;
  answered: number;
  answerPct: number | null;
  calls60: number;
  talkHours: number;
  meetingsSet: number;
  /** Состоялось — встречи от ТМ, прошедшие по бизнес-процессу (held по создателю). */
  meetingsHeld: number;
  /** Явка = состоялось / назначено, %. */
  heldPct: number | null;
  /** Конверсия дозвон→встреча, %. */
  convDialToMeeting: number | null;
}

/** Таблица по звонарям, сортировка по наборам. Чистая функция.
 * «Состоялось/явка» — событийная метрика по СОЗДАТЕЛЮ (meetingsHeldByCreator):
 * встречу назначил ТМ и она прошла по бизнес-процессу, даже если проводил продавец. */
export function buildTmManagerTable(members: TmMember[]): TmManagerRow[] {
  return members
    .map((m) => ({
      managerId: m.managerId,
      name: m.name,
      dept: m.dept,
      dials: m.dials,
      answered: m.answered,
      answerPct: pct1(m.answered, m.dials),
      calls60: m.calls60,
      talkHours: Math.round((m.talkSeconds / 3600) * 10) / 10,
      meetingsSet: m.meetingsSet,
      meetingsHeld: m.meetingsHeldByCreator,
      heldPct: pct1(m.meetingsHeldByCreator, m.meetingsSet),
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
  /** Сжигание базы: личных отвалов на 1 назначенную встречу. */
  burn: number | null;
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
    burn: m.meetingsSet > 0 ? Math.round((m.rejectionsPeriod / m.meetingsSet) * 10) / 10 : null,
  };
}

// ───────────────────────── Воронка cat50 ─────────────────────────

export interface TmFunnel50Stage {
  stage: string;
  label: string;
  kind: Cat50Kind;
  count: number;
}

export interface TmFunnelStageMeta {
  stage: string;
  label: string;
  kind: Cat50Kind;
  order: number;
}

/** Воронка [50] по одному владельцу (ТМ или МП) — счётчики по стадиям. */
export interface TmFunnelManager {
  managerId: number;
  name: string;
  isActive: boolean;
  counts: Record<string, number>;
}

/** Бандл ТМ-воронки: стадии + гранулярка по владельцам + список выбора (ТМ и МП). */
export interface TmFunnel50 {
  stages: TmFunnelStageMeta[];
  perManager: TmFunnelManager[];
  selectableManagers: { managerId: number; name: string; isActive: boolean }[];
}

/** Снимок ТМ-воронки [50] по владельцам. cells = открытые сделки cat50 (стадия+владелец). */
export function buildTmFunnel50(
  cells: { managerId: number | null; stage: string }[],
  nameById: Map<number, string>,
  activeById: Map<number, boolean>,
): TmFunnel50 {
  const stages: TmFunnelStageMeta[] = Object.entries(STAGE_META_50)
    .sort((a, b) => a[1].order - b[1].order)
    .map(([stage, m]) => ({ stage, label: m.label, kind: m.kind, order: m.order }));
  const byMgr = new Map<number, TmFunnelManager>();
  for (const c of cells) {
    if (c.managerId == null || !STAGE_META_50[c.stage]) continue;
    let e = byMgr.get(c.managerId);
    if (!e) {
      e = { managerId: c.managerId, name: nameById.get(c.managerId) ?? `id ${c.managerId}`, isActive: activeById.get(c.managerId) ?? true, counts: {} };
      byMgr.set(c.managerId, e);
    }
    e.counts[c.stage] = (e.counts[c.stage] ?? 0) + 1;
  }
  const total = (m: TmFunnelManager) => Object.values(m.counts).reduce((a, b) => a + b, 0);
  const perManager = [...byMgr.values()].sort((a, b) => total(b) - total(a));
  const selectableManagers = perManager
    .map((m) => ({ managerId: m.managerId, name: m.name, isActive: m.isActive }))
    .sort((a, b) => a.name.localeCompare(b.name, 'ru'));
  return { stages, perManager, selectableManagers };
}

/** Свести воронку по выбранным владельцам (для мультиселекта). Чистая. */
export function aggregateTmFunnel(
  perManager: TmFunnelManager[],
  selectedIds: ReadonlySet<number>,
  stages: TmFunnelStageMeta[],
): TmFunnel50Stage[] {
  return stages.map((s) => {
    let count = 0;
    for (const m of perManager) if (selectedIds.has(m.managerId)) count += m.counts[s.stage] ?? 0;
    return { stage: s.stage, label: s.label, kind: s.kind, count };
  });
}

/** @deprecated простой снимок без владельцев — оставлен для тестов/совместимости. */
export function buildTmFunnel50Flat(cells: { stage: string }[]): TmFunnel50Stage[] {
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
  /** Состоялось по создателю-ТМ. */
  meetingsHeldByCreator: number;
  /** Личные отвалы (APOLOGY) за месяц. */
  rejected: number;
  /** Отложено (LOSE) за месяц. */
  postponed: number;
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
  rejected: number;
  postponed: number;
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
    meetingsHeld: r.meetingsHeldByCreator,
    conv: pct1(r.meetingsSet, r.calls60),
    rejected: r.rejected,
    postponed: r.postponed,
  }));
}

// ── Динамика с мультиселектом звонарей + сравнение «на ту же дату» ─────────────

/** Агрегат за период 1..N месяца (для сравнения текущий vs прошлый). */
export interface TmMonthlyPeriod {
  dials: number;
  calls60: number;
  meetingsSet: number;
  held: number;
}

export interface TmMonthlyManager {
  managerId: number;
  name: string;
  isActive: boolean;
  rows: TmMonthlyInput[]; // помесячно (последние 8)
  cur: TmMonthlyPeriod; // текущий месяц 1..N
  prev: TmMonthlyPeriod; // прошлый месяц 1..N
}

export interface TmMonthlyBundle {
  months: { ym: string; label: string }[];
  perManager: TmMonthlyManager[];
  selectableManagers: { managerId: number; name: string; isActive: boolean }[];
  curLabel: string; // «1–7 июн»
  prevLabel: string; // «1–7 мая»
}

const ZERO_PERIOD = (): TmMonthlyPeriod => ({ dials: 0, calls60: 0, meetingsSet: 0, held: 0 });

/** Свести помесячные строки по выбранным звонарям. Чистая. */
export function aggregateTmMonthlyRows(
  perManager: TmMonthlyManager[],
  selectedIds: ReadonlySet<number>,
  months: { ym: string; label: string }[],
): TmMonthlyInput[] {
  return months.map((mo, i) => {
    const acc: TmMonthlyInput = {
      ym: mo.ym, label: mo.label, dials: 0, answered: 0, calls60: 0, talkSeconds: 0,
      meetingsSet: 0, meetingsHeldByCreator: 0, rejected: 0, postponed: 0,
    };
    for (const m of perManager) {
      if (!selectedIds.has(m.managerId)) continue;
      const r = m.rows[i];
      if (!r) continue;
      acc.dials += r.dials;
      acc.answered += r.answered;
      acc.calls60 += r.calls60;
      acc.talkSeconds += r.talkSeconds;
      acc.meetingsSet += r.meetingsSet;
      acc.meetingsHeldByCreator += r.meetingsHeldByCreator;
      acc.rejected += r.rejected;
      acc.postponed += r.postponed;
    }
    return acc;
  });
}

/** Свести период «на ту же дату» (текущий/прошлый) по выбранным звонарям. Чистая. */
export function aggregateTmMonthlyPeriod(
  perManager: TmMonthlyManager[],
  selectedIds: ReadonlySet<number>,
): { cur: TmMonthlyPeriod; prev: TmMonthlyPeriod } {
  const cur = ZERO_PERIOD();
  const prev = ZERO_PERIOD();
  for (const m of perManager) {
    if (!selectedIds.has(m.managerId)) continue;
    cur.dials += m.cur.dials; cur.calls60 += m.cur.calls60; cur.meetingsSet += m.cur.meetingsSet; cur.held += m.cur.held;
    prev.dials += m.prev.dials; prev.calls60 += m.prev.calls60; prev.meetingsSet += m.prev.meetingsSet; prev.held += m.prev.held;
  }
  return { cur, prev };
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
  const held = members.reduce((a, m) => a + m.meetingsHeldByCreator, 0);
  return {
    set,
    held,
    heldPct: pct1(held, set),
    toCold: members.reduce((a, m) => a + m.dealsCold, 0),
  };
}

// ───────────────────────── План / факт ─────────────────────────

/** Строка план/факт по звонарю (для одной метрики). */
export interface TmPlanManager {
  managerId: number;
  name: string;
  fact: number;
  plan: number;
}

/** План/факт ТМ: дозвоны ≥60с и состоявшиеся брифования — командно + по звонарям. */
export interface TmPlanFact {
  dials60: { teamFact: number; teamPlan: number; perTm: number; managers: TmPlanManager[] };
  briefings: { teamFact: number; teamPlan: number; perTm: number; managers: TmPlanManager[] };
}

export interface TmPlanFactInput {
  /** План дозвонов ≥60с на 1 ТМ/мес (дефолт 400). */
  dials60PerTm: number;
  /** План состоявшихся брифований на 1 ТМ/мес (дефолт 20). */
  briefingsPerTm: number;
  members: { managerId: number; name: string; calls60: number; briefingsHeld: number }[];
}

/** План/факт ТМ: дозвоны ≥60с + состоявшиеся брифования, по звонарям и командно. Чистая. */
export function buildTmPlanFact(i: TmPlanFactInput): TmPlanFact {
  const dialsM = i.members
    .map((m) => ({ managerId: m.managerId, name: m.name, fact: m.calls60, plan: i.dials60PerTm }))
    .sort((a, b) => b.fact - a.fact);
  const briefM = i.members
    .map((m) => ({ managerId: m.managerId, name: m.name, fact: m.briefingsHeld, plan: i.briefingsPerTm }))
    .sort((a, b) => b.fact - a.fact);
  const n = i.members.length;
  return {
    dials60: {
      teamFact: dialsM.reduce((a, m) => a + m.fact, 0),
      teamPlan: i.dials60PerTm * n,
      perTm: i.dials60PerTm,
      managers: dialsM,
    },
    briefings: {
      teamFact: briefM.reduce((a, m) => a + m.fact, 0),
      teamPlan: i.briefingsPerTm * n,
      perTm: i.briefingsPerTm,
      managers: briefM,
    },
  };
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
  /** Доп. касаний (мессенджер+почта) на одну назначенную встречу. */
  perMeeting: number | null;
  rows: TmOutreachRow[];
}

/** Мессенджер/почта по звонарям + касаний на встречу. Чистая функция. */
export function buildTmOutreach(members: TmMember[]): TmOutreach {
  const rows = members
    .map((m) => ({ managerId: m.managerId, name: m.name, messenger: m.messenger, emails: m.emails }))
    .filter((r) => r.messenger > 0 || r.emails > 0)
    .sort((a, b) => b.messenger - a.messenger || b.emails - a.emails);
  const messengerTotal = rows.reduce((a, r) => a + r.messenger, 0);
  const emailTotal = rows.reduce((a, r) => a + r.emails, 0);
  const meetingsSet = members.reduce((a, m) => a + m.meetingsSet, 0);
  return {
    messengerTotal,
    emailTotal,
    perMeeting: meetingsSet > 0 ? Math.round(((messengerTotal + emailTotal) / meetingsSet) * 10) / 10 : null,
    rows,
  };
}

// ───────────────────── Причины отвала (cat50) ─────────────────────

/** Лейблы причины отвала ТМ-воронки (UF_CRM_1771324790). */
export const REASON_50: Record<number, string> = {
  8540: 'Все устраивает',
  8550: 'Нет потребности',
  8546: 'Не вышли на ЛПР',
  8838: 'ЛПР не берёт трубку',
  8542: 'Выручка <30 млн',
  8538: 'Бизнес закрылся',
  8544: 'Дубль',
  8548: 'Не прошёл квалификацию',
  8840: 'Некорректные контакты',
  8842: 'Чёрный список',
};

/** Закрыватели-автоматы (админ/автопроцесс гигиены/Лариса) — массовые закрытия,
 * исключаются из «личных» отвалов менеджеров. */
export const REJECTION_ADMIN_CLOSERS = [1, 1710, 2812];

export function reasonLabel(id: number | null): string {
  return id != null ? (REASON_50[id] ?? 'Другое') : '(не указана)';
}

export interface RejectionInput {
  managerId: number;
  name: string;
  reasonId: number | null;
  count: number;
}

export interface ReasonBucket {
  reasonId: number | null;
  label: string;
  count: number;
  pct: number;
}

export interface TmRejections {
  managerId: number;
  name: string;
  total: number;
  reasons: ReasonBucket[];
}

/** Причины отвала по звонарю (накопленно, личные закрытия). Чистая функция. */
export function buildTmRejections(inputs: RejectionInput[]): TmRejections[] {
  const by = new Map<number, { name: string; reasons: Map<number | null, number> }>();
  for (const r of inputs) {
    const e = by.get(r.managerId) ?? { name: r.name, reasons: new Map() };
    e.reasons.set(r.reasonId, (e.reasons.get(r.reasonId) ?? 0) + r.count);
    by.set(r.managerId, e);
  }
  return [...by.entries()]
    .map(([managerId, e]) => {
      const total = [...e.reasons.values()].reduce((a, b) => a + b, 0);
      const reasons: ReasonBucket[] = [...e.reasons.entries()]
        .map(([reasonId, count]) => ({
          reasonId,
          label: reasonLabel(reasonId),
          count,
          pct: total > 0 ? Math.round((count / total) * 100) : 0,
        }))
        .sort((a, b) => b.count - a.count);
      return { managerId, name: e.name, total, reasons };
    })
    .sort((a, b) => b.total - a.total);
}

// ───────────────── Качество встреч ТМ (из разбора /meetings) ─────────────────

export interface TmQualityInput {
  managerId: number;
  name: string;
  score: number; // балл встречи из analysis_json (1..10)
  hasNextStep: boolean;
}

export interface TmQualityRow {
  managerId: number;
  name: string;
  total: number;
  /** Содержательных (балл ≥7), %. */
  richPct: number;
}

export interface TmMeetingQuality {
  total: number;
  rich: number; // ≥7
  weak: number; // 4..6
  empty: number; // <4
  richPct: number;
  weakPct: number;
  emptyPct: number;
  /** % встреч со следующим шагом. */
  nextStepPct: number | null;
  byManager: TmQualityRow[];
}

function qualityBucket(score: number): 'rich' | 'weak' | 'empty' {
  if (score >= 7) return 'rich';
  if (score >= 4) return 'weak';
  return 'empty';
}

/** Качество встреч, назначенных ТМ — по готовому разбору (analysis_json). Только
 * разобранные встречи (есть балл). Чистая функция. */
export function buildTmMeetingQuality(inputs: TmQualityInput[]): TmMeetingQuality {
  const total = inputs.length;
  const rich = inputs.filter((i) => qualityBucket(i.score) === 'rich').length;
  const weak = inputs.filter((i) => qualityBucket(i.score) === 'weak').length;
  const empty = inputs.filter((i) => qualityBucket(i.score) === 'empty').length;
  const pct = (n: number) => (total > 0 ? Math.round((n / total) * 100) : 0);
  const by = new Map<number, { name: string; total: number; rich: number }>();
  for (const i of inputs) {
    const e = by.get(i.managerId) ?? { name: i.name, total: 0, rich: 0 };
    e.total += 1;
    if (qualityBucket(i.score) === 'rich') e.rich += 1;
    by.set(i.managerId, e);
  }
  return {
    total,
    rich,
    weak,
    empty,
    richPct: pct(rich),
    weakPct: pct(weak),
    emptyPct: pct(empty),
    nextStepPct: total > 0 ? Math.round((inputs.filter((i) => i.hasNextStep).length / total) * 100) : null,
    byManager: [...by.entries()]
      .map(([managerId, e]) => ({
        managerId,
        name: e.name,
        total: e.total,
        richPct: e.total > 0 ? Math.round((e.rich / e.total) * 100) : 0,
      }))
      .sort((a, b) => b.total - a.total),
  };
}

// ───────────────────── Heatmap времени дозвона ─────────────────────

export interface HeatInput {
  dow: number; // 0=Вс..6=Сб (Postgres extract(dow))
  hour: number;
  dials: number;
  calls60: number;
}

export interface HeatCell {
  hour: number;
  dials: number;
  calls60: number;
  /** % дозвона ≥60с в этой ячейке. */
  pct: number | null;
}

export interface HeatRow {
  dow: number;
  label: string;
  cells: HeatCell[];
}

export interface TmHeatmap {
  hours: number[];
  rows: HeatRow[];
  /** Максимальный % по сетке (для нормировки цвета). */
  maxPct: number;
}

const DOW_RU: Record<number, string> = { 1: 'Пн', 2: 'Вт', 3: 'Ср', 4: 'Чт', 5: 'Пт' };

/** Heatmap «когда берут трубку»: час × день недели (Пн–Пт), % дозвона ≥60с.
 * Чистая функция. */
export function buildTmHeatmap(inputs: HeatInput[]): TmHeatmap {
  const work = inputs.filter((i) => i.dow >= 1 && i.dow <= 5 && i.hour >= 0 && i.hour <= 23);
  const hours = [...new Set(work.map((i) => i.hour))].sort((a, b) => a - b);
  const byKey = new Map<string, { dials: number; calls60: number }>();
  for (const i of work) {
    const k = `${i.dow}:${i.hour}`;
    const e = byKey.get(k) ?? { dials: 0, calls60: 0 };
    e.dials += i.dials;
    e.calls60 += i.calls60;
    byKey.set(k, e);
  }
  let maxPct = 0;
  const rows: HeatRow[] = [1, 2, 3, 4, 5].map((dow) => ({
    dow,
    label: DOW_RU[dow],
    cells: hours.map((hour) => {
      const e = byKey.get(`${dow}:${hour}`) ?? { dials: 0, calls60: 0 };
      const pct = e.dials > 0 ? Math.round((e.calls60 / e.dials) * 100) : null;
      if (pct != null && pct > maxPct) maxPct = pct;
      return { hour, dials: e.dials, calls60: e.calls60, pct };
    }),
  }));
  return { hours, rows, maxPct: Math.max(1, maxPct) };
}

// ───────────────────────── ТМ-алерты ─────────────────────────

export type AlertLevel = 'red' | 'amber' | 'green';

export interface TmAlert {
  level: AlertLevel;
  icon: string;
  title: string;
  text: string;
}

export interface TmAlertInput {
  name: string;
  /** Конверсия дозвон→встреча, последний полный месяц, %. */
  convNow: number | null;
  /** Конверсия за предыдущий полный месяц, %. */
  convPrev: number | null;
  /** Сжигание базы (отвалов на встречу). */
  burn: number | null;
  /** Явка состоялось/назначено, %. */
  heldPct: number | null;
}

/** Авто-сигналы по ТМ из данных (просадка/рост конверсии, сжигание базы, явка).
 * Чистая функция. */
export function buildTmAlerts(inputs: TmAlertInput[]): TmAlert[] {
  const alerts: TmAlert[] = [];
  for (const i of inputs) {
    if (i.convPrev != null && i.convNow != null && i.convPrev >= 3) {
      if (i.convNow <= i.convPrev * 0.7) {
        alerts.push({
          level: 'red',
          icon: '📉',
          title: `Конверсия ${i.name} просела`,
          text: `дозвон→встреча ${i.convPrev}% → ${i.convNow}% за месяц. Вернуть фокус на назначение встреч.`,
        });
      } else if (i.convNow >= i.convPrev * 1.25) {
        alerts.push({
          level: 'green',
          icon: '📈',
          title: `Конверсия ${i.name} растёт`,
          text: `дозвон→встреча ${i.convPrev}% → ${i.convNow}% за месяц.`,
        });
      }
    }
    if (i.burn != null && i.burn >= 10) {
      alerts.push({
        level: 'amber',
        icon: '🔥',
        title: `${i.name} быстро вырабатывает базу`,
        text: `${i.burn} отвалов на одну встречу за период — проверить темп выдачи базы.`,
      });
    }
    if (i.heldPct != null && i.heldPct < 55 && i.heldPct >= 0) {
      alerts.push({
        level: 'amber',
        icon: '🚪',
        title: `Низкая явка у ${i.name}`,
        text: `состоялось ${i.heldPct}% от назначенных — подтверждать встречи накануне.`,
      });
    }
  }
  return alerts;
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
  kpis: TmKpis;
  table: TmManagerRow[];
  funnel50: TmFunnel50;
  meetingsResult: TmMeetingsResult;
  /** Помесячная динамика по всем ТМ + период «на ту же дату» (мультиселект на клиенте). */
  monthlyBundle: TmMonthlyBundle;
  microFunnels: TmMicroFunnel[];
  planFact: TmPlanFact;
  outreach: TmOutreach;
  /** Причины отвала по звонарям (накопленно, личные закрытия). */
  rejections: TmRejections[];
  /** Heatmap времени дозвона (час × день недели). */
  heatmap: TmHeatmap;
  /** Качество встреч, назначенных ТМ (из разбора /meetings). */
  meetingQuality: TmMeetingQuality;
  /** Авто-сигналы по ТМ. */
  alerts: TmAlert[];
  /** Опции месячного пикера (последние месяцы). */
  monthOptions: { ym: string; label: string }[];
  /** Выбранный месяц (?month), null = текущий период от снимка. */
  selectedMonth: string | null;
  generatedAt: string | null;
}
