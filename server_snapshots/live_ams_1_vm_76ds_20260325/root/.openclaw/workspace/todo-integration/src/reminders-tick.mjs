import { runRemindersTick } from "./reminders.mjs";

async function main() {
  const r = await runRemindersTick();
  if (r.skipped) {
    console.log(`reminders_skip reason=${r.reason}`);
    return;
  }
  console.log(`reminders_ok checked=${r.checkedTimed} pre=${r.sent.pre} main=${r.sent.main} followup=${r.sent.followup} missed=${r.sent.missed} suppressed=${r.sent.suppressed || 0}`);
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
