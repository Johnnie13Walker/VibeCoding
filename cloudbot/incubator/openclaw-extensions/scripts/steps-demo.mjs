import { evaluatePing, getStepsInsights, recordWebhookSteps, updateGoal } from '../steps/index.js';

const storePath = process.env.STEPS_DATA_FILE || './data/steps-history.json';
const now = new Date();

async function main() {
  const steps = Number(process.argv[2] || 4200);
  await updateGoal(Number(process.env.STEPS_GOAL || 10000), { storePath });
  await recordWebhookSteps(steps, { timestamp: now.toISOString(), storePath });

  const ping = await evaluatePing({ now, storePath });
  const insights = await getStepsInsights({ now, storePath });

  console.log('=== webhook accepted ===');
  console.log({ stepsToday: steps, ts: now.toISOString() });

  console.log('\n=== ping ===');
  if (!ping.shouldSend) {
    console.log(`no message: ${ping.reason}`);
  } else {
    console.log(ping.message);
  }

  console.log('\n=== steps_insights ===');
  console.log(insights.text);
}

main().catch((err) => {
  console.error(err?.message || err);
  process.exit(1);
});
