import { cleanupOldData } from "./storage.mjs";

export function runPersonalTtlCleanup(cfg) {
  cleanupOldData(cfg.stateDir, cfg.personalDataTtlDays || 180);
}
