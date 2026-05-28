import { getMeetings } from '../../provider.gcal.js';
import { getTodoConfig } from '../../provider.todo.js';
import { getWhoopDailySummary } from '../../provider.whoop.js';

function parseDayArgs(rawArg = '') {
  const tokens = String(rawArg || '').trim().split(/\s+/).filter(Boolean);
  const weeklyAliases = new Set(['steps_week', 'week_steps', 'шаги_неделя', 'шаги-неделя']);
  let includeWeeklySteps = true;
  const dateTokens = [];

  for (const token of tokens) {
    const normalized = token.toLowerCase();
    if (weeklyAliases.has(normalized)) {
      includeWeeklySteps = true;
      continue;
    }
    dateTokens.push(token);
  }

  const dateQuery = dateTokens.join(' ').trim() || 'сегодня';
  return { dateQuery, includeWeeklySteps };
}

function fmtNumber(value) {
  return new Intl.NumberFormat('ru-RU').format(Number(value || 0));
}

function formatWeeklyStepsBlock(weeklySteps) {
  if (!weeklySteps) return 'Шаги за прошлую неделю: н/д';
  if (!weeklySteps.available) {
    const reason = String(weeklySteps.message || 'данные недоступны').trim();
    return `Шаги за прошлую неделю: н/д (${reason})`;
  }

  const minLabel = weeklySteps.minDay
    ? `${weeklySteps.minDay.day}: ${fmtNumber(weeklySteps.minDay.steps)}`
    : 'н/д';
  const maxLabel = weeklySteps.maxDay
    ? `${weeklySteps.maxDay.day}: ${fmtNumber(weeklySteps.maxDay.steps)}`
    : 'н/д';

  return [
    `Шаги за прошлую неделю (${weeklySteps.periodStart} — ${weeklySteps.periodEnd}):`,
    `• Сумма: ${fmtNumber(weeklySteps.totalSteps)}`,
    `• Среднее/день: ${fmtNumber(weeklySteps.avgStepsPerDay)}`,
    `• Мин/макс день: ${minLabel} / ${maxLabel}`,
  ].join('\n');
}

const dayBriefingWorkflow = {
  async run(_input, context = {}) {
    const { dateQuery, includeWeeklySteps } = parseDayArgs(context.arg);
    const meetings = await getMeetings(dateQuery);
    const todo = getTodoConfig(context);
    const whoop = await getWhoopDailySummary(dateQuery, context, { includeWeeklySteps });

    const lines = [
      `Утренний брифинг (${dateQuery}):`,
      '',
      '1) Встречи',
      meetings.text,
      '',
      '2) Задачи',
      todo.configured
        ? 'TODO подключен. Используй /tasks для детальной диагностики.'
        : 'TODO не подключен.',
      '',
      '3) WHOOP',
      whoop.text,
      formatWeeklyStepsBlock(whoop.weeklySteps),
    ];

    return {
      response: { text: lines.join('\n') },
      nextState: null,
    };
  },

  async continue(_state, input, context = {}) {
    return this.run(input, context);
  },
};

async function runDayBriefingWorkflow(input, context = {}) {
  const out = await dayBriefingWorkflow.run(input, context);
  return { handled: true, reply: out.response.text };
}

export { dayBriefingWorkflow, runDayBriefingWorkflow };
