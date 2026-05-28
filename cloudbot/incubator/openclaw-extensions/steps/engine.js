import { addStepEvent, getDayMeta, getGoalSteps, getTimezone, loadStore, markSent, saveStore, setGoalSteps } from './storage.js';
import { buildActivityProfile } from './profile.js';
import { computeStepState } from './forecast.js';
import { buildStatusMessage } from './messages.js';
import { buildInsights } from './insights.js';
import { dayKey } from './time.js';

const MAX_MESSAGES_PER_DAY = 6;

function shouldMandatoryPing(nowHour, sentFlags) {
  const mandatory = [10, 15, 20];
  for (const h of mandatory) {
    if (nowHour === h && !sentFlags[`mandatory_${h}`]) {
      return `mandatory_${h}`;
    }
  }
  return null;
}

function shouldExtraPing(state, sentFlags) {
  if (
    state.nowHourInt >= 15
    && state.nowHourInt <= 16
    && sentFlags.mandatory_15
    && state.deviationFromProfile <= -0.25
    && !sentFlags.deviation_15
  ) {
    return 'deviation_15';
  }

  if (state.nowHourInt >= 16 && state.nowHourInt <= 19 && state.forecast < state.goalSteps && !sentFlags.forecast_16_19) {
    return 'forecast_16_19';
  }

  if (state.nowHourInt >= 21 && state.remainingSteps <= 1500 && !sentFlags.close_21) {
    return 'close_21';
  }

  return null;
}

function truncate(text, maxLen = 2000) {
  if (text.length <= maxLen) return text;
  return `${text.slice(0, maxLen - 3)}...`;
}

export async function recordWebhookSteps(stepsToday, { timestamp = new Date().toISOString(), storePath } = {}) {
  const store = await loadStore(storePath);
  addStepEvent(store, { timestamp, stepsToday });
  await saveStore(store, storePath);

  return {
    ok: true,
    stepsToday: Number(stepsToday) || 0,
    timestamp,
  };
}

export async function updateGoal(goalSteps, { storePath } = {}) {
  const store = await loadStore(storePath);
  const goal = setGoalSteps(store, goalSteps);
  await saveStore(store, storePath);
  return { goalSteps: goal };
}

export async function getStepsInsights({ now = new Date(), storePath } = {}) {
  const store = await loadStore(storePath);
  const tz = getTimezone(store);
  const goal = getGoalSteps(store);
  const profile = buildActivityProfile(store.events, { now, timeZone: tz, lookbackDays: 14, minDays: 7 });
  const insights = buildInsights(profile, goal);

  return {
    timezone: tz,
    goalSteps: goal,
    profile,
    insights,
    text: insights.text,
  };
}

export async function evaluatePing({ now = new Date(), storePath } = {}) {
  const store = await loadStore(storePath);
  const tz = getTimezone(store);
  const goal = getGoalSteps(store);
  const profile = buildActivityProfile(store.events, { now, timeZone: tz, lookbackDays: 14, minDays: 7 });

  const state = computeStepState(store.events, profile, {
    now,
    timeZone: tz,
    goalSteps: goal,
  });
  state.goalSteps = goal;

  const today = dayKey(now, tz);
  const meta = getDayMeta(store, today);

  if (meta.sentCount >= MAX_MESSAGES_PER_DAY) {
    return {
      shouldSend: false,
      reason: 'daily_limit_reached',
      state,
      profile,
    };
  }

  const mandatoryFlag = shouldMandatoryPing(state.nowHourInt, meta.sentFlags);
  const extraFlag = shouldExtraPing(state, meta.sentFlags);
  const flag = mandatoryFlag || extraFlag;

  if (!flag) {
    return {
      shouldSend: false,
      reason: 'no_trigger',
      state,
      profile,
    };
  }

  const msg = buildStatusMessage(state, profile, goal);
  markSent(store, today, flag);
  await saveStore(store, storePath);

  return {
    shouldSend: true,
    reason: flag,
    scenario: msg.scenario,
    message: truncate(msg.text, 2000),
    state,
    profile,
  };
}
