import { getConfig } from "./config.mjs";
import { createProvider } from "./provider-factory.mjs";
import { saveTasksSnapshot } from "./service.mjs";
import { runPersonalTtlCleanup } from "./personal/ttlCleanup.mjs";
import { maybeSyncUsersBySchedule } from "./agenda/providers/bitrixUsers.mjs";

async function main() {
  const cfg = getConfig();
  const provider = createProvider(cfg);
  const tasks = await provider.getAllOpenTasks();
  const file = saveTasksSnapshot(cfg.stateDir, cfg.tz, tasks, cfg);
  runPersonalTtlCleanup(cfg);
  const usersSync = await maybeSyncUsersBySchedule(cfg).catch((e) => ({ ok: false, error: e.message || String(e) }));
  console.log(`snapshot_saved=${file} tasks=${tasks.length} users_sync=${JSON.stringify(usersSync)}`);
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
