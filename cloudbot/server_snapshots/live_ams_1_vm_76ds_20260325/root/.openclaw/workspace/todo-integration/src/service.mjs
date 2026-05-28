import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { dateISOInTz } from "./time.mjs";
import { collectTaskSnapshotTelemetry } from "./personal/telemetryCollector.mjs";

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

export function toDatePart(task) {
  if (task.dueDate) return task.dueDate;
  if (task.dueDateTime) return task.dueDateTime.slice(0, 10);
  return null;
}

export function toTimePart(task, tz) {
  if (!task.dueDateTime) return null;
  const d = new Date(task.dueDateTime);
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: tz,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(d);
}

export function filterTasksForDate(tasks, isoDate) {
  return tasks.filter((t) => toDatePart(t) === isoDate && !t.completed);
}

export function filterOverdue(tasks, todayIso) {
  return tasks.filter((t) => {
    const d = toDatePart(t);
    return d && d < todayIso && !t.completed;
  });
}

export function filterDueToday(tasks, todayIso) {
  return tasks.filter((t) => toDatePart(t) === todayIso && !t.completed);
}

export function filterOverdueAndToday(tasks, todayIso) {
  return tasks.filter((t) => {
    const d = toDatePart(t);
    return d && d <= todayIso && !t.completed;
  });
}

export function loadDigestState(stateDir) {
  ensureDir(stateDir);
  const file = path.join(stateDir, "digest_state.json");
  if (!fs.existsSync(file)) return { entries: [] };
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return { entries: [] };
  }
}

export function saveDigestState(stateDir, state) {
  ensureDir(stateDir);
  const file = path.join(stateDir, "digest_state.json");
  fs.writeFileSync(file, JSON.stringify(state, null, 2));
}

export function alreadySent(state, dateIso, slot) {
  return state.entries.some((x) => x.date === dateIso && x.slot === slot);
}

export function markSent(stateDir, dateIso, slot) {
  const s = loadDigestState(stateDir);
  s.entries = s.entries.filter((x) => !(x.date === dateIso && x.slot === slot));
  s.entries.push({ date: dateIso, slot, sent_at: new Date().toISOString() });
  if (s.entries.length > 120) s.entries = s.entries.slice(-120);
  saveDigestState(stateDir, s);
}

export function saveTasksSnapshot(stateDir, tz, tasks, cfg = null) {
  ensureDir(stateDir);
  const file = path.join(stateDir, "tasks_snapshot.json");
  const now = new Date();
  const today = dateISOInTz(now, tz);
  const payload = {
    generatedAt: now.toISOString(),
    timezone: tz,
    today,
    tasks
  };
  fs.writeFileSync(file, JSON.stringify(payload, null, 2));
  if (cfg) {
    try {
      collectTaskSnapshotTelemetry(cfg, tasks, now);
    } catch {
      // no-op telemetry failure
    }
  }
  return file;
}

export function loadTasksSnapshot(stateDir) {
  const file = path.join(stateDir, "tasks_snapshot.json");
  if (!fs.existsSync(file)) return null;
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

export function loadMatrixHistory(stateDir) {
  ensureDir(stateDir);
  const file = path.join(stateDir, "matrix_history.json");
  if (!fs.existsSync(file)) return { entries: [] };
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return { entries: [] };
  }
}

export function saveMatrixHistory(stateDir, state) {
  ensureDir(stateDir);
  const file = path.join(stateDir, "matrix_history.json");
  fs.writeFileSync(file, JSON.stringify(state, null, 2));
}

export function markMatrixSnapshot(stateDir, row) {
  const s = loadMatrixHistory(stateDir);
  s.entries = s.entries.filter((x) => !(x.date === row.date && x.slot === row.slot));
  s.entries.push({ ...row, saved_at: new Date().toISOString() });
  if (s.entries.length > 200) s.entries = s.entries.slice(-200);
  saveMatrixHistory(stateDir, s);
}

function loadShortLinksState(stateDir) {
  ensureDir(stateDir);
  const file = path.join(stateDir, "short_links.json");
  if (!fs.existsSync(file)) return { entries: [] };
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return { entries: [] };
  }
}

function saveShortLinksState(stateDir, state) {
  ensureDir(stateDir);
  const file = path.join(stateDir, "short_links.json");
  fs.writeFileSync(file, JSON.stringify(state, null, 2));
}

function normalizeBaseUrl(baseUrl) {
  const clean = String(baseUrl || "").trim();
  return clean.replace(/\/$/, "");
}

function tokenForUrl(url) {
  const hash = crypto.createHash("sha1").update(url).digest("base64url");
  return hash.slice(0, 10);
}

export function getOrCreateShortLink(stateDir, baseUrl, originalUrl, ttlDays = 30) {
  const safeBase = normalizeBaseUrl(baseUrl);
  if (!safeBase || !originalUrl) return originalUrl || "";

  const now = Date.now();
  const expiresAt = now + ttlDays * 24 * 3600 * 1000;
  const state = loadShortLinksState(stateDir);

  state.entries = (state.entries || []).filter((x) => Number(x.expiresAt || 0) > now && x.url);

  const existing = state.entries.find((x) => x.url === originalUrl);
  if (existing) {
    existing.expiresAt = expiresAt;
    existing.updatedAt = new Date().toISOString();
    saveShortLinksState(stateDir, state);
    return `${safeBase}/r/${existing.token}`;
  }

  const token = tokenForUrl(originalUrl);
  state.entries.push({
    token,
    url: originalUrl,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    expiresAt
  });
  if (state.entries.length > 5000) state.entries = state.entries.slice(-5000);
  saveShortLinksState(stateDir, state);
  return `${safeBase}/r/${token}`;
}

export function loadRemindersState(stateDir) {
  ensureDir(stateDir);
  const file = path.join(stateDir, "reminders_state.json");
  if (!fs.existsSync(file)) return { entries: [], lastRunAt: null };
  try {
    const data = JSON.parse(fs.readFileSync(file, "utf8"));
    if (!Array.isArray(data.entries)) return { entries: [], lastRunAt: null };
    return data;
  } catch {
    return { entries: [], lastRunAt: null };
  }
}

export function saveRemindersState(stateDir, state) {
  ensureDir(stateDir);
  const file = path.join(stateDir, "reminders_state.json");
  fs.writeFileSync(file, JSON.stringify(state, null, 2));
}

export function loadRemindersSettings(stateDir, defaults = {}) {
  ensureDir(stateDir);
  const file = path.join(stateDir, "reminders_settings.json");
  if (!fs.existsSync(file)) return { enabled: !!defaults.enabled };
  try {
    const data = JSON.parse(fs.readFileSync(file, "utf8"));
    return { enabled: data.enabled !== false };
  } catch {
    return { enabled: !!defaults.enabled };
  }
}

export function saveRemindersSettings(stateDir, settings) {
  ensureDir(stateDir);
  const file = path.join(stateDir, "reminders_settings.json");
  const payload = { enabled: settings.enabled !== false, updatedAt: new Date().toISOString() };
  fs.writeFileSync(file, JSON.stringify(payload, null, 2));
}
