// Чистая логика блока «Отказы» (воронка Продажи [10]) — без server-only,
// чтобы импортировать и в клиентский компонент (мультиселект менеджеров).

export const SALES_LOSE_STAGE = 'C10:LOSE';
export const SPAM_REASON_10 = 8588;

/** Справочник причин отказа воронки Продажи (UF_CRM_1771495464, enum Bitrix). */
export const REASON_10: Record<number, string> = {
  8574: 'Нет связи',
  8576: 'Нет такой услуги / не реализуем',
  8578: 'Выручка <30 млн/год',
  8580: 'Ушли к конкурентам',
  8582: 'Свой исполнитель / инхаус',
  8584: 'Нехватка бюджета / нет финмодели',
  8586: 'Передумали / неактуально',
  8624: 'Действующий клиент',
  8588: 'СПАМ',
};

export function reasonLabel10(id: number | null): string {
  return id != null ? (REASON_10[id] ?? 'Другое') : '(не указана)';
}

// Отдел продаж по должности. Отказ ставит ТОЛЬКО продажник/РОП, НЕ телемаркетолог.
export const isTelemarketing = (dept: string | null | undefined): boolean =>
  (dept || '').toLowerCase().includes('телемаркет');
export const isSalesManager = (dept: string | null | undefined): boolean => {
  const d = (dept || '').toLowerCase();
  return (d.includes('продаж') || d.includes('роп')) && !isTelemarketing(d);
};

export const MONTHS_RU_SHORT = [
  'янв', 'фев', 'мар', 'апр', 'май', 'июнь',
  'июль', 'авг', 'сен', 'окт', 'ноя', 'дек',
];

export const REASON_NULL_KEY = 'null';

export interface SalesReasonBucket {
  reasonId: number | null;
  label: string;
  count: number;
  pct: number;
}

export interface SalesRejectionMonth {
  ym: string;
  label: string;
  count: number;
}

export interface SalesRejectionManager {
  managerId: number;
  name: string;
  rejections: number;
  lostAmount: number;
  won: number;
  /** Доля отказов = отказы / (отказы + оплаты), %. null если нет закрытых. */
  lossRate: number | null;
  topReason: string | null;
}

/** Гранулярные данные по одному действующему продажнику (для агрегации на клиенте). */
export interface SalesRejectionPerManager {
  managerId: number;
  name: string;
  rejections: number; // ex-spam
  lostAmount: number; // ex-spam
  spam: number;
  won: number;
  monthCounts: Record<string, number>; // ym -> count (ex-spam)
  reasonCounts: Record<string, number>; // reasonId|'null' -> count (ex-spam)
}

/** Бандл для страницы: гранулярка для карточки 1 (мультиселект) + таблица карточки 2. */
export interface SalesRejectionsBundle {
  yearLabel: string;
  monthsSkeleton: { ym: string; label: string }[];
  perManager: SalesRejectionPerManager[];
  selectableManagers: { managerId: number; name: string }[];
  /** Карточка 2 «по менеджерам» (все действующие продажники). */
  managers: SalesRejectionManager[];
}

/** Агрегированный срез карточки 1 под выбранных менеджеров. */
export interface SalesRejectionsView {
  yearLabel: string;
  totalRejections: number;
  lostAmount: number;
  lossRate: number | null;
  avgLoss: number;
  spamExcluded: number;
  wonTotal: number;
  months: SalesRejectionMonth[];
  reasons: SalesReasonBucket[];
}

export const lossRate = (rej: number, won: number): number | null =>
  rej + won > 0 ? Math.round((rej / (rej + won)) * 100) : null;

const parseReasonKey = (key: string): number | null =>
  key === REASON_NULL_KEY ? null : Number(key);

/** Срез карточки 1 под выбранных менеджеров (КPI + помесячно + причины). Чистая. */
export function aggregateSelected(
  perManager: SalesRejectionPerManager[],
  selectedIds: ReadonlySet<number>,
  monthsSkeleton: { ym: string; label: string }[],
  yearLabel: string,
): SalesRejectionsView {
  const monthCount = new Map<string, number>();
  const reasonCount = new Map<string, number>();
  let lostAmount = 0;
  let spamExcluded = 0;
  let wonTotal = 0;

  for (const m of perManager) {
    if (!selectedIds.has(m.managerId)) continue;
    lostAmount += m.lostAmount;
    spamExcluded += m.spam;
    wonTotal += m.won;
    for (const [ym, c] of Object.entries(m.monthCounts)) {
      monthCount.set(ym, (monthCount.get(ym) ?? 0) + c);
    }
    for (const [rid, c] of Object.entries(m.reasonCounts)) {
      reasonCount.set(rid, (reasonCount.get(rid) ?? 0) + c);
    }
  }

  const totalRejections = [...reasonCount.values()].reduce((a, b) => a + b, 0);
  const reasons: SalesReasonBucket[] = [...reasonCount.entries()]
    .map(([key, count]) => {
      const reasonId = parseReasonKey(key);
      return {
        reasonId,
        label: reasonLabel10(reasonId),
        count,
        pct: totalRejections > 0 ? Math.round((count / totalRejections) * 100) : 0,
      };
    })
    .sort((a, b) => b.count - a.count);
  const months: SalesRejectionMonth[] = monthsSkeleton.map((mo) => ({
    ...mo,
    count: monthCount.get(mo.ym) ?? 0,
  }));

  return {
    yearLabel,
    totalRejections,
    lostAmount,
    lossRate: lossRate(totalRejections, wonTotal),
    avgLoss: totalRejections > 0 ? Math.round(lostAmount / totalRejections) : 0,
    spamExcluded,
    wonTotal,
    months,
    reasons,
  };
}

/** Карточка 2 «по менеджерам» из гранулярки. Топ-причина = макс по reasonCounts. */
export function managersFromPerManager(perManager: SalesRejectionPerManager[]): SalesRejectionManager[] {
  return perManager
    .map((m) => {
      const top = Object.entries(m.reasonCounts).sort((a, b) => b[1] - a[1])[0]?.[0];
      return {
        managerId: m.managerId,
        name: m.name,
        rejections: m.rejections,
        lostAmount: m.lostAmount,
        won: m.won,
        lossRate: lossRate(m.rejections, m.won),
        topReason: top != null ? reasonLabel10(parseReasonKey(top)) : null,
      };
    })
    .sort((a, b) => b.rejections - a.rejections);
}

export const emptyBundle = (yearLabel = '—'): SalesRejectionsBundle => ({
  yearLabel,
  monthsSkeleton: [],
  perManager: [],
  selectableManagers: [],
  managers: [],
});
