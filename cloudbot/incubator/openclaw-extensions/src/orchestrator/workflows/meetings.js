import { getMeetings } from '../../../provider.gcal.js';

export async function runMeetingsWorkflow(_input, ctx = {}) {
  const query = String(ctx.arg || '').trim() || 'сегодня';
  const meetings = await getMeetings(query);

  const header = `Встречи (${query}):`;
  return {
    handled: true,
    reply: `${header}\n${meetings.text}`,
  };
}

