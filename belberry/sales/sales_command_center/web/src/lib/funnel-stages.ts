// Порядок и названия стадий воронки Продажи [10] — зеркало runner/src/funnel_stages.py.
// Сверено с живым Bitrix 2026-06-18. Шаги воронки «Путь сделки» строятся отсюда.

export const FUNNEL_STEPS_10: { order: number; stage: string; label: string; sub?: string }[] = [
  { order: 1, stage: 'C10:NEW', label: 'Вошли в воронку', sub: 'квалификация' },
  { order: 2, stage: 'C10:PREPAYMENT_INVOIC', label: 'Подготовка БРИФа' },
  { order: 3, stage: 'C10:EXECUTING', label: 'Подготовка КП' },
  { order: 4, stage: 'C10:UC_4SJOE4', label: 'Защита КП', sub: 'презентация' },
  { order: 5, stage: 'C10:FINAL_INVOICE', label: 'Получить решение' },
  { order: 6, stage: 'C10:UC_RJK0KE', label: 'Получить реквизиты' },
  { order: 7, stage: 'C10:UC_KC7195', label: 'Согласование договора' },
  { order: 8, stage: 'C10:UC_755Z64', label: 'Ожидаем оплату' },
  { order: 9, stage: 'C10:WON', label: 'Оплата' },
];

export const FUNNEL_MAX_ORDER = 9;
export const SPAM_REASON_10 = 8588;

// Каноническое название стадии Bitrix (для снимка/прогноза/алертов) — зеркало
// runner/src/funnel_stages.py STAGE_LABEL_10. Отличается от FUNNEL_STEPS_10 только
// первой стадией: тут «Квалификация» (имя стадии), там «Вошли в воронку» (путь сделки).
export const STAGE_LABEL_10: Record<string, string> = {
  'C10:NEW': 'Квалификация',
  'C10:PREPAYMENT_INVOIC': 'Подготовка БРИФа',
  'C10:EXECUTING': 'Подготовка КП',
  'C10:UC_4SJOE4': 'Защита КП',
  'C10:FINAL_INVOICE': 'Получить решение',
  'C10:UC_RJK0KE': 'Получить реквизиты',
  'C10:UC_KC7195': 'Согласование договора',
  'C10:UC_755Z64': 'Ожидаем оплату',
  'C10:WON': 'Оплата',
};

// Порядок стадии 1..9 — выводится из FUNNEL_STEPS_10 (единый источник пути).
export const STAGE_ORDER_10: Record<string, number> = Object.fromEntries(
  FUNNEL_STEPS_10.map((s) => [s.stage, s.order]),
);

export const WON_STAGE_10 = 'C10:WON';

// Стадии, добавленные при перестройке процесса Продаж (18.06). Пока в них нет
// сделок — помечаются бейджем «нов.»; бейдж исчезает, как только стадия наполнится.
export const NEW_STAGES_10 = new Set(['C10:UC_4SJOE4', 'C10:UC_RJK0KE', 'C10:UC_755Z64']);
