import { getStateForStatus, getState, resetState, setState } from '../storage/stateStore.js';
import { dayBriefingWorkflow } from '../workflows/dayBriefingWorkflow.js';
import { diagnosticsWorkflow } from '../workflows/diagnosticsWorkflow.js';
import { legacyContactsWorkflow } from '../workflows/legacyContactsWorkflow.js';
import { meetingWorkflow } from '../workflows/meetingWorkflow.js';
import { tasksWorkflow } from '../workflows/tasksWorkflow.js';
import { whoopReportWorkflow } from '../workflows/whoopReportWorkflow.js';
import { resolveIntent } from '../workflows/intentParser.js';

const WORKFLOWS = {
  day_briefing: dayBriefingWorkflow,
  diagnostics: diagnosticsWorkflow,
  legacy_contacts: legacyContactsWorkflow,
  meeting_create: meetingWorkflow,
  tasks: tasksWorkflow,
  whoop_report: whoopReportWorkflow,
};

function normalize(text) {
  return String(text || '').trim().toLowerCase();
}

function isResetCommand(text) {
  const t = normalize(text);
  return t === 'отмена' || t === 'сброс' || t === '/cancel' || t === '/reset';
}

function isStatusCommand(text) {
  return normalize(text) === 'статус';
}

function formatStatus(state) {
  if (!state) return 'Активного сценария нет. Жду новую команду.';
  return `Активный сценарий: ${state.activeFlow}\nТекущий шаг: ${state.step}`;
}

function toResult(payload) {
  if (!payload?.response || typeof payload.response.text !== 'string') {
    return { handled: false, reply: null };
  }

  const out = {
    handled: true,
    reply: payload.response.text,
  };

  if (payload.response.parse_mode) out.parse_mode = payload.response.parse_mode;
  if (payload.response.reply_markup) out.reply_markup = payload.response.reply_markup;

  return out;
}

export async function routeIncoming(input, ctx = {}) {
  if (isResetCommand(input.text)) {
    await resetState(input, ctx);
    return {
      handled: true,
      reply: 'Ок, отменил, начинаем с чистого листа',
    };
  }

  if (isStatusCommand(input.text)) {
    const activeState = await getStateForStatus(input, ctx);
    return {
      handled: true,
      reply: formatStatus(activeState),
    };
  }

  const activeState = await getState(input, ctx);
  if (activeState) {
    const workflow = WORKFLOWS[activeState.activeFlow];
    if (!workflow || typeof workflow.continue !== 'function') {
      await resetState(input, ctx);
      return {
        handled: true,
        reply: 'Активный сценарий потерян. Начинаем заново, сформулируй запрос.',
      };
    }

    const payload = await workflow.continue(activeState, input, ctx);
    await setState(input, payload?.nextState || null, ctx);
    return toResult(payload);
  }

  const { intent, arg, command } = resolveIntent(input.text);
  const workflow = WORKFLOWS[intent] || legacyContactsWorkflow;
  const payload = await workflow.run(input, { ...ctx, arg, intent, command });

  await setState(input, payload?.nextState || null, ctx);
  return toResult(payload);
}
