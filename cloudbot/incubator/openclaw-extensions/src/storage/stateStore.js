import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';

const DEFAULT_STATE_PATH = './data/dialog-state.json';
const TTL_MS = 2 * 60 * 60 * 1000;

function nowMs() {
  return Date.now();
}

function nowIso() {
  return new Date().toISOString();
}

function statePath(ctx = {}) {
  return String(ctx.statePath || process.env.STATE_DB_PATH || DEFAULT_STATE_PATH).trim() || DEFAULT_STATE_PATH;
}

function ensureDb(raw) {
  const db = raw && typeof raw === 'object' ? raw : {};
  if (!db.states || typeof db.states !== 'object') db.states = {};
  if (!db.updatedAt) db.updatedAt = nowIso();
  return db;
}

function normalizeState(input) {
  if (!input || typeof input !== 'object') return null;

  const activeFlow = String(input.activeFlow || '').trim();
  const step = String(input.step || '').trim();
  if (!activeFlow || !step) return null;

  const payload = input.payload && typeof input.payload === 'object' ? input.payload : {};
  const updatedAt = String(input.updatedAt || nowIso());

  return {
    activeFlow,
    step,
    payload,
    updatedAt,
  };
}

async function loadDb(path) {
  try {
    const raw = await readFile(path, 'utf8');
    return ensureDb(JSON.parse(raw));
  } catch (err) {
    if (err?.code === 'ENOENT') return ensureDb({});
    throw err;
  }
}

async function saveDb(path, db) {
  await mkdir(dirname(path), { recursive: true });
  const normalized = ensureDb(db);
  normalized.updatedAt = nowIso();

  const tmp = `${path}.tmp`;
  await writeFile(tmp, `${JSON.stringify(normalized, null, 2)}\n`, 'utf8');
  await rename(tmp, path);
}

function isExpired(state) {
  if (!state?.updatedAt) return true;
  const ts = Date.parse(state.updatedAt);
  if (!Number.isFinite(ts)) return true;
  return nowMs() - ts > TTL_MS;
}

function keyFromInput(input = {}) {
  const userId = String(input.userId || '').trim();
  if (userId) return `u:${userId}`;

  const chatId = String(input.chatId || '').trim();
  if (chatId) return `c:${chatId}`;

  return null;
}

export async function getState(input, ctx = {}) {
  const key = keyFromInput(input);
  if (!key) return null;

  const path = statePath(ctx);
  const db = await loadDb(path);
  const state = normalizeState(db.states[key]);

  if (!state) return null;
  if (isExpired(state)) {
    delete db.states[key];
    await saveDb(path, db);
    return null;
  }

  return state;
}

export async function setState(input, nextState, ctx = {}) {
  const key = keyFromInput(input);
  if (!key) return;

  const path = statePath(ctx);
  const db = await loadDb(path);

  const normalized = normalizeState(nextState);
  if (!normalized) {
    delete db.states[key];
  } else {
    db.states[key] = {
      ...normalized,
      updatedAt: nowIso(),
    };
  }

  await saveDb(path, db);
}

export async function resetState(input, ctx = {}) {
  await setState(input, null, ctx);
}

export async function getStateForStatus(input, ctx = {}) {
  return getState(input, ctx);
}
