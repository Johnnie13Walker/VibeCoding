import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function dbPath(stateDir) {
  ensureDir(stateDir);
  return path.join(stateDir, "personal.db");
}

function openDb(stateDir) {
  const db = new DatabaseSync(dbPath(stateDir));
  db.exec(`
    PRAGMA journal_mode=WAL;
    PRAGMA synchronous=NORMAL;

    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT,
      updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS user_metrics_daily (
      date TEXT PRIMARY KEY,
      meetings_minutes INTEGER DEFAULT 0,
      free_minutes INTEGER DEFAULT 0,
      tasks_created INTEGER DEFAULT 0,
      tasks_completed INTEGER DEFAULT 0,
      tasks_overdue INTEGER DEFAULT 0,
      p1_completed INTEGER DEFAULT 0,
      p2_completed INTEGER DEFAULT 0,
      p3_completed INTEGER DEFAULT 0,
      p4_completed INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS task_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      task_id TEXT,
      ts TEXT,
      event_type TEXT,
      priority INTEGER,
      due_datetime TEXT,
      source TEXT,
      meta_json TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_task_events_ts ON task_events(ts);
    CREATE INDEX IF NOT EXISTS idx_task_events_type ON task_events(event_type);

    CREATE TABLE IF NOT EXISTS assistant_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts TEXT,
      event_type TEXT,
      context TEXT,
      payload_json TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_assistant_events_ts ON assistant_events(ts);

    CREATE TABLE IF NOT EXISTS meeting_stats (
      date TEXT,
      hour_bucket INTEGER,
      meetings_count INTEGER DEFAULT 0,
      meetings_minutes INTEGER DEFAULT 0,
      PRIMARY KEY(date, hour_bucket)
    );

    CREATE TABLE IF NOT EXISTS focus_blocks_stats (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      date TEXT,
      start_time TEXT,
      duration INTEGER,
      accepted INTEGER,
      completed_hint INTEGER
    );
  `);
  return db;
}

function nowIso() {
  return new Date().toISOString();
}

export function withDb(stateDir, fn) {
  const db = openDb(stateDir);
  try {
    return fn(db);
  } finally {
    db.close();
  }
}

export function getSetting(stateDir, key, fallback = null) {
  return withDb(stateDir, (db) => {
    const row = db.prepare("SELECT value FROM settings WHERE key = ?").get(String(key));
    if (!row || row.value == null) return fallback;
    return row.value;
  });
}

export function setSetting(stateDir, key, value) {
  return withDb(stateDir, (db) => {
    db.prepare(`
      INSERT INTO settings(key, value, updated_at)
      VALUES (?, ?, ?)
      ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
    `).run(String(key), String(value), nowIso());
  });
}

export function deleteSetting(stateDir, key) {
  return withDb(stateDir, (db) => {
    db.prepare("DELETE FROM settings WHERE key = ?").run(String(key));
  });
}

export function isProfileEnabled(stateDir, defaultEnabled = true) {
  const raw = getSetting(stateDir, "profile_enabled", defaultEnabled ? "1" : "0");
  return String(raw) !== "0";
}

export function setProfileEnabled(stateDir, enabled) {
  setSetting(stateDir, "profile_enabled", enabled ? "1" : "0");
}

export function setProfileWipePending(stateDir, userId) {
  setSetting(stateDir, `profile_wipe_pending_${String(userId)}`, nowIso());
}

export function getProfileWipePending(stateDir, userId) {
  return getSetting(stateDir, `profile_wipe_pending_${String(userId)}`, null);
}

export function clearProfileWipePending(stateDir, userId) {
  deleteSetting(stateDir, `profile_wipe_pending_${String(userId)}`);
}

export function upsertDailyMetrics(stateDir, dateIso, patch = {}) {
  return withDb(stateDir, (db) => {
    db.prepare("INSERT OR IGNORE INTO user_metrics_daily(date) VALUES (?)").run(dateIso);
    const fields = [
      "meetings_minutes",
      "free_minutes",
      "tasks_created",
      "tasks_completed",
      "tasks_overdue",
      "p1_completed",
      "p2_completed",
      "p3_completed",
      "p4_completed"
    ];
    for (const f of fields) {
      const v = Number(patch[f] || 0);
      if (!v) continue;
      db.prepare(`UPDATE user_metrics_daily SET ${f} = COALESCE(${f}, 0) + ? WHERE date = ?`).run(v, dateIso);
    }
  });
}

export function insertTaskEvent(stateDir, ev) {
  return withDb(stateDir, (db) => {
    db.prepare(`
      INSERT INTO task_events(task_id, ts, event_type, priority, due_datetime, source, meta_json)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).run(
      String(ev.task_id || ""),
      String(ev.ts || nowIso()),
      String(ev.event_type || "unknown"),
      ev.priority == null ? null : Number(ev.priority),
      ev.due_datetime || null,
      ev.source || null,
      ev.meta_json ? JSON.stringify(ev.meta_json) : null
    );
  });
}

export function insertAssistantEvent(stateDir, ev) {
  return withDb(stateDir, (db) => {
    db.prepare(`
      INSERT INTO assistant_events(ts, event_type, context, payload_json)
      VALUES (?, ?, ?, ?)
    `).run(
      String(ev.ts || nowIso()),
      String(ev.event_type || "unknown"),
      ev.context || null,
      ev.payload_json ? JSON.stringify(ev.payload_json) : null
    );
  });
}

export function upsertMeetingBucket(stateDir, dateIso, hour, meetingsCount, meetingsMinutes) {
  return withDb(stateDir, (db) => {
    db.prepare(`
      INSERT INTO meeting_stats(date, hour_bucket, meetings_count, meetings_minutes)
      VALUES (?, ?, ?, ?)
      ON CONFLICT(date, hour_bucket) DO UPDATE SET
        meetings_count = excluded.meetings_count,
        meetings_minutes = excluded.meetings_minutes
    `).run(dateIso, Number(hour), Number(meetingsCount || 0), Number(meetingsMinutes || 0));
  });
}

export function insertFocusBlockStat(stateDir, row) {
  return withDb(stateDir, (db) => {
    db.prepare(`
      INSERT INTO focus_blocks_stats(date, start_time, duration, accepted, completed_hint)
      VALUES (?, ?, ?, ?, ?)
    `).run(
      row.date,
      row.start_time,
      Number(row.duration || 0),
      row.accepted ? 1 : 0,
      row.completed_hint == null ? null : (row.completed_hint ? 1 : 0)
    );
  });
}

export function queryAll(stateDir, sql, params = []) {
  return withDb(stateDir, (db) => db.prepare(sql).all(...params));
}

export function queryOne(stateDir, sql, params = []) {
  return withDb(stateDir, (db) => db.prepare(sql).get(...params));
}

export function wipeTelemetry(stateDir) {
  return withDb(stateDir, (db) => {
    db.exec(`
      DELETE FROM user_metrics_daily;
      DELETE FROM task_events;
      DELETE FROM assistant_events;
      DELETE FROM meeting_stats;
      DELETE FROM focus_blocks_stats;
    `);
  });
}

export function cleanupOldData(stateDir, keepDays = 180) {
  const keep = Math.max(60, Math.min(180, Number(keepDays || 180)));
  return withDb(stateDir, (db) => {
    db.prepare("DELETE FROM task_events WHERE ts < datetime('now', ?)").run(`-${keep} days`);
    db.prepare("DELETE FROM assistant_events WHERE ts < datetime('now', ?)").run(`-${keep} days`);
    db.prepare("DELETE FROM focus_blocks_stats WHERE date < date('now', ?)").run(`-${keep} days`);
    db.prepare("DELETE FROM meeting_stats WHERE date < date('now', ?)").run(`-${keep} days`);
    db.prepare("DELETE FROM user_metrics_daily WHERE date < date('now', ?)").run(`-${keep} days`);
  });
}
