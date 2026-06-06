// Метрика «Опер» — операционная вовлечённость по модели реальных рабочих минут.
// Зеркало runner/src/oper.py: каждое действие переводим в живое время, нормируем
// к дню (≈300 мин «в руках»). Роль (ОП/ТМ) на балл не влияет — встреча весит как
// встреча, пустой набор как набор. Держать веса в синхроне с oper.py.

export const OPER = {
  DIAL_MINUTES: 0.25, // набор/короткий обрыв <60с
  DIAL_CAP: 90, // потолок «механического» обзвона за день
  CALL_60S: 5, // разговор 60с+
  CHAT: 10, // диалог Wazzup
  EMAIL: 5, // письмо
  MEETING: 60, // встреча
  DAY_TARGET: 300, // целевые рабочие минуты «в руках» за день
} as const;

export interface OperActions {
  dials: number;
  calls60: number;
  messenger?: number;
  meetings?: number;
  emails?: number;
}

/** «Живые» рабочие минуты за день по действиям менеджера. */
export function operationalMinutes(a: OperActions): number {
  const dials = a.dials || 0;
  const calls60 = a.calls60 || 0;
  const shortDials = Math.max(0, dials - calls60);
  const dialMin = Math.min(shortDials * OPER.DIAL_MINUTES, OPER.DIAL_CAP);
  return (
    dialMin +
    calls60 * OPER.CALL_60S +
    (a.messenger || 0) * OPER.CHAT +
    (a.emails || 0) * OPER.EMAIL +
    (a.meetings || 0) * OPER.MEETING
  );
}

/** Балл «Опер» 0–10: нормировка минут к дневной цели, потолок 10, округление до 0.1. */
export function operationalScore(a: OperActions): number {
  const total = operationalMinutes(a);
  return Math.round(Math.min(10, (total / OPER.DAY_TARGET) * 10) * 10) / 10;
}

// ───────────────── Данные блока «Операционная эффективность» ─────────────────

export interface OperationalRow {
  managerId: number;
  name: string;
  role: string; // должность (dept)
  isTm: boolean; // телемаркетинг → отдельная секция
  scores: (number | null)[]; // балл по дням (null = нет данных за день)
  minutes: (number | null)[]; // живые минуты по дням — для загрузки
  avg: number | null; // средний балл сотрудника за окно
}

export interface OperationalMatrix {
  days: string[]; // ISO-даты колонок (рабочие дни окна)
  rows: OperationalRow[]; // ОП, затем ТМ; внутри секции — по среднему баллу ↓
  deptAvgByDay: (number | null)[]; // средний балл отдела по дням
  avgScore: number | null; // средний балл отдела за окно
  loadPct: number | null; // загрузка дня: средние минуты / целевые, %
  best: { name: string; score: number } | null; // лучший по среднему баллу
  countOp: number;
  countTm: number;
}

export interface OperDayInput {
  date: string;
  dials: number;
  calls60: number;
  messenger: number;
  emails: number;
  meetings: number;
}

export interface OperMemberInput {
  managerId: number;
  name: string;
  role: string;
  isTm: boolean;
  isActive: boolean; // действующий сотрудник (is_active в Bitrix)
  byDate: Map<string, OperDayInput>; // активность сотрудника по дням окна
}

// Сотрудник попадает в блок, только если он действующий (is_active) И реально
// работал в периоде — хотя бы один день с заметной операционной загрузкой
// (Опер ≥ этого порога ≈ 30 живых минут). Так уходят уволенные, отпускники и
// простаивающие — и не занижают среднее по отделу нулями.
const ACTIVE_MIN_SCORE = 1.0;

/** Чистая сборка матрицы из подготовленных по-дневных входов (без БД — тестируемо). */
export function buildOperationalMatrix(days: string[], members: OperMemberInput[]): OperationalMatrix {
  const mk = (m: OperMemberInput): OperationalRow => {
    const scores: (number | null)[] = [];
    const minutes: (number | null)[] = [];
    for (const d of days) {
      const a = m.byDate.get(d);
      if (!a) {
        scores.push(null);
        minutes.push(null);
        continue;
      }
      scores.push(operationalScore(a));
      minutes.push(operationalMinutes(a));
    }
    const present = scores.filter((s): s is number => s != null);
    const avg = present.length ? Math.round((present.reduce((x, y) => x + y, 0) / present.length) * 10) / 10 : null;
    return { managerId: m.managerId, name: m.name, role: m.role, isTm: m.isTm, scores, minutes, avg };
  };

  const byAvg = (a: OperationalRow, b: OperationalRow) => (b.avg ?? -1) - (a.avg ?? -1) || a.name.localeCompare(b.name, 'ru');
  // Только действующие и реально работавшие в периоде (см. ACTIVE_MIN_SCORE).
  const worked = (m: OperMemberInput, row: OperationalRow) =>
    m.isActive && row.scores.some((s) => s != null && s >= ACTIVE_MIN_SCORE);
  const prep = (m: OperMemberInput) => ({ m, row: mk(m) });
  const op = members.filter((m) => !m.isTm).map(prep).filter(({ m, row }) => worked(m, row)).map(({ row }) => row).sort(byAvg);
  const tm = members.filter((m) => m.isTm).map(prep).filter(({ m, row }) => worked(m, row)).map(({ row }) => row).sort(byAvg);
  const rows = [...op, ...tm];

  const deptAvgByDay = days.map((_, i) => {
    const col = rows.map((r) => r.scores[i]).filter((s): s is number => s != null);
    return col.length ? Math.round((col.reduce((x, y) => x + y, 0) / col.length) * 10) / 10 : null;
  });

  const allScores = rows.flatMap((r) => r.scores).filter((s): s is number => s != null);
  const avgScore = allScores.length
    ? Math.round((allScores.reduce((x, y) => x + y, 0) / allScores.length) * 10) / 10
    : null;

  const allMinutes = rows.flatMap((r) => r.minutes).filter((s): s is number => s != null);
  const loadPct = allMinutes.length
    ? Math.round(((allMinutes.reduce((x, y) => x + y, 0) / allMinutes.length) / OPER.DAY_TARGET) * 100)
    : null;

  let best: { name: string; score: number } | null = null;
  for (const r of rows) {
    if (r.avg != null && (best == null || r.avg > best.score)) best = { name: r.name, score: r.avg };
  }

  return {
    days,
    rows,
    deptAvgByDay,
    avgScore,
    loadPct,
    best,
    countOp: op.length,
    countTm: tm.length,
  };
}
