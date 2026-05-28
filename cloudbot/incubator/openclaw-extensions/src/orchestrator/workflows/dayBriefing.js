import { getMeetings } from '../../../provider.gcal.js';
import { getTodoConfig } from '../../../provider.todo.js';
import { getWhoopDailySummary } from '../../../provider.whoop.js';

export async function runDayBriefingWorkflow(_input, ctx = {}) {
  const dateQuery = String(ctx.arg || '').trim() || 'сегодня';
  const meetings = await getMeetings(dateQuery);
  const todo = getTodoConfig(ctx);
  const whoop = await getWhoopDailySummary(dateQuery, ctx);

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
  ];

  return { handled: true, reply: lines.join('\n') };
}
