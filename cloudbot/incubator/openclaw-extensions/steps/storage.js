import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname } from 'node:path';

const DEFAULT_PATH = process.env.STEPS_DATA_FILE || './data/steps-history.json';
const MAX_DAYS_HISTORY = 60;

function defaultStore() {
  return {
    version: 1,
    settings: {
      goalSteps: Number(process.env.STEPS_GOAL || 10000),
      timezone: process.env.STEPS_TIMEZONE || 'Europe/Moscow',
    },
    events: [],
    dailyMeta: {},
  };
}

function sanitizeSteps(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0) return 0;
  return Math.round(n);
}

function cutoffMs(days) {
  return Date.now() - days * 24 * 60 * 60 * 1000;
}

function normalizeMeta(meta = {}) {
  const out = {};
  for (const [k, v] of Object.entries(meta)) {
    out[k] = {
      sentCount: Number(v?.sentCount || 0),
      sentFlags: typeof v?.sentFlags === 'object' && v.sentFlags ? v.sentFlags : {},
    };
  }
  return out;
}

function prune(store) {
  const cutoff = cutoffMs(MAX_DAYS_HISTORY);
  store.events = (store.events || []).filter((e) => {
    const ts = Date.parse(e.ts);
    return Number.isFinite(ts) && ts >= cutoff;
  });
}

export async function loadStore(path = DEFAULT_PATH) {
  if (!existsSync(path)) {
    return defaultStore();
  }
  const raw = await readFile(path, 'utf8');
  const parsed = JSON.parse(raw);
  const store = {
    ...defaultStore(),
    ...parsed,
    settings: { ...defaultStore().settings, ...(parsed.settings || {}) },
    events: Array.isArray(parsed.events) ? parsed.events : [],
    dailyMeta: normalizeMeta(parsed.dailyMeta),
  };
  prune(store);
  return store;
}

export async function saveStore(store, path = DEFAULT_PATH) {
  const dir = dirname(path);
  await mkdir(dir, { recursive: true });
  prune(store);
  await writeFile(path, JSON.stringify(store, null, 2), 'utf8');
}

export function addStepEvent(store, { timestamp, stepsToday }) {
  const ts = new Date(timestamp || Date.now()).toISOString();
  store.events.push({ ts, stepsToday: sanitizeSteps(stepsToday) });
}

export function setGoalSteps(store, goalSteps) {
  const n = sanitizeSteps(goalSteps);
  if (n <= 0) throw new Error('goalSteps must be > 0');
  store.settings.goalSteps = n;
  return n;
}

export function getGoalSteps(store) {
  return sanitizeSteps(store?.settings?.goalSteps || 10000);
}

export function getTimezone(store) {
  return String(store?.settings?.timezone || process.env.STEPS_TIMEZONE || 'Europe/Moscow');
}

export function getDayMeta(store, day) {
  if (!store.dailyMeta[day]) {
    store.dailyMeta[day] = { sentCount: 0, sentFlags: {} };
  }
  return store.dailyMeta[day];
}

export function markSent(store, day, flag) {
  const meta = getDayMeta(store, day);
  if (meta.sentFlags[flag]) return false;
  meta.sentFlags[flag] = true;
  meta.sentCount += 1;
  return true;
}
