import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';

function nowIso() {
  return new Date().toISOString();
}

function defaultDb() {
  return {
    contacts: [],
    invites: [],
    sessions: {},
    audit: [],
    seq: { contactId: 1 },
    created_at: nowIso(),
    updated_at: nowIso(),
  };
}

function ensureSchema(db) {
  if (!db || typeof db !== 'object') return defaultDb();
  if (!Array.isArray(db.contacts)) db.contacts = [];
  if (!Array.isArray(db.invites)) db.invites = [];
  if (!db.sessions || typeof db.sessions !== 'object') db.sessions = {};
  if (!Array.isArray(db.audit)) db.audit = [];
  if (!db.seq || typeof db.seq !== 'object') db.seq = { contactId: 1 };
  if (!Number.isInteger(db.seq.contactId) || db.seq.contactId < 1) db.seq.contactId = 1;
  if (!db.created_at) db.created_at = nowIso();
  db.updated_at = nowIso();
  return db;
}

export async function loadDb(dbPath) {
  try {
    const raw = await readFile(dbPath, 'utf8');
    return ensureSchema(JSON.parse(raw));
  } catch (err) {
    if (err && err.code === 'ENOENT') return defaultDb();
    throw err;
  }
}

export async function saveDb(dbPath, db) {
  await mkdir(dirname(dbPath), { recursive: true });
  const normalized = ensureSchema(db);
  const tmp = `${dbPath}.tmp`;
  await writeFile(tmp, `${JSON.stringify(normalized, null, 2)}\n`, 'utf8');
  await rename(tmp, dbPath);
}

export async function withDb(dbPath, fn) {
  const db = await loadDb(dbPath);
  const out = await fn(db);
  await saveDb(dbPath, db);
  return out;
}
