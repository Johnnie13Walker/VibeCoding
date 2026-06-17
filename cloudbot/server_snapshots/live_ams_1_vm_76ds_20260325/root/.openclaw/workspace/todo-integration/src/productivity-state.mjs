import fs from "node:fs";
import path from "node:path";

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function readJson(file, fallback) {
  try {
    if (!fs.existsSync(file)) return fallback;
    const parsed = JSON.parse(fs.readFileSync(file, "utf8"));
    return parsed ?? fallback;
  } catch {
    return fallback;
  }
}

function writeJson(file, data) {
  ensureDir(path.dirname(file));
  fs.writeFileSync(file, JSON.stringify(data, null, 2));
}

function fp(stateDir, name) {
  ensureDir(stateDir);
  return path.join(stateDir, name);
}

export function loadFocusBlocks(stateDir) {
  return readJson(fp(stateDir, "focus_blocks.json"), { entries: [] });
}

export function saveFocusBlocks(stateDir, state) {
  writeJson(fp(stateDir, "focus_blocks.json"), state);
}

export function loadFocusProposal(stateDir) {
  return readJson(fp(stateDir, "focus_proposal.json"), { proposal: null });
}

export function saveFocusProposal(stateDir, state) {
  writeJson(fp(stateDir, "focus_proposal.json"), state);
}

export function loadTaskReschedules(stateDir) {
  return readJson(fp(stateDir, "task_reschedules.json"), { entries: [] });
}

export function saveTaskReschedules(stateDir, state) {
  writeJson(fp(stateDir, "task_reschedules.json"), state);
}

export function loadReschedulePending(stateDir) {
  return readJson(fp(stateDir, "reschedule_pending.json"), { byUser: {} });
}

export function saveReschedulePending(stateDir, state) {
  writeJson(fp(stateDir, "reschedule_pending.json"), state);
}

export function loadSuppressedNotifications(stateDir) {
  return readJson(fp(stateDir, "suppressed_notifications.json"), { entries: [], lastFlushAt: null });
}

export function saveSuppressedNotifications(stateDir, state) {
  writeJson(fp(stateDir, "suppressed_notifications.json"), state);
}

export function loadDndSettings(stateDir, defaults = {}) {
  const base = readJson(fp(stateDir, "dnd_settings.json"), null);
  if (!base) {
    return {
      enabled: defaults.enabled !== false,
      nightStart: defaults.nightStart || "23:00",
      nightEnd: defaults.nightEnd || "08:00"
    };
  }
  return {
    enabled: base.enabled !== false,
    nightStart: String(base.nightStart || defaults.nightStart || "23:00"),
    nightEnd: String(base.nightEnd || defaults.nightEnd || "08:00")
  };
}

export function saveDndSettings(stateDir, settings) {
  writeJson(fp(stateDir, "dnd_settings.json"), {
    enabled: settings.enabled !== false,
    nightStart: String(settings.nightStart || "23:00"),
    nightEnd: String(settings.nightEnd || "08:00"),
    updatedAt: new Date().toISOString()
  });
}
