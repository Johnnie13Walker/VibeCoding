import { evaluatePing, getStepsInsights, recordWebhookSteps, updateGoal } from './engine.js';
import { loadStore } from './storage.js';
import { buildActivityProfile } from './profile.js';
import { computeStepState } from './forecast.js';

export {
  evaluatePing,
  getStepsInsights,
  recordWebhookSteps,
  updateGoal,
  loadStore,
  buildActivityProfile,
  computeStepState,
};

export async function runStepsCommand(command, payload = {}) {
  if (command === 'steps_insights') {
    return getStepsInsights(payload);
  }
  if (command === 'steps_goal_set') {
    return updateGoal(payload.goalSteps, payload);
  }
  if (command === 'steps_ping_check') {
    return evaluatePing(payload);
  }
  if (command === 'steps_webhook') {
    return recordWebhookSteps(payload.stepsToday, payload);
  }
  throw new Error(`Unknown command: ${command}`);
}
