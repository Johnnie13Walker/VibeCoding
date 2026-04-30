import { getConfig } from "./config.mjs";
import { createProvider } from "./provider-factory.mjs";
import { saveTasksSnapshot } from "./service.mjs";
import { runPersonalTtlCleanup } from "./personal/ttlCleanup.mjs";
import { maybeSyncUsersBySchedule } from "./agenda/providers/bitrixUsers.mjs";

async function runOnce() {
  const cfg = getConfig();
  const provider = createProvider(cfg);
  const tasks = await provider.getAllOpenTasks();
  saveTasksSnapshot(cfg.stateDir, cfg.tz, tasks, cfg);
  const usersSync = await maybeSyncUsersBySchedule(cfg).catch((e) => ({ ok: false, error: e.message || String(e) }));
  runPersonalTtlCleanup(cfg);
  console.log(`[todo-daemon] synced tasks=${tasks.length} users_sync=${JSON.stringify(usersSync)} at ${new Date().toISOString()}`);
}

async function main() {
  await runOnce();
  setInterval(() => {
    runOnce().catch((e) => console.error(`[todo-daemon] sync failed: ${e.message || e}`));
  }, 10 * 60 * 1000);
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
