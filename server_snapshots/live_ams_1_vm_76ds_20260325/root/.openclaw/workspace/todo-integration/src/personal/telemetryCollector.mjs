import fs from "node:fs";
import path from "node:path";
import { dateISOInTz } from "../time.mjs";
import {
  insertAssistantEvent,
  insertTaskEvent,
  isProfileEnabled,
  queryOne,
  upsertDailyMetrics,
  upsertMeetingBucket
} from "./storage.mjs";

function stateFile(stateDir, name) {
  fs.mkdirSync(stateDir, { recursive: true });
  return path.join(stateDir, name);
}

function readJson(file, fallback) {
  try {
    if (!fs.existsSync(file)) return fallback;
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return fallback;
  }
}

function writeJson(file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(data, null, 2));
}

function toDatePart(task) {
  if (task.dueDate) return task.dueDate;
  if (task.dueDateTime) return String(task.dueDateTime).slice(0, 10);
  return null;
}

function mapPriority(task) {
  const p = Number(task.priority || task.todoistPriority || 2);
  if (p >= 4) return 1;
  if (p === 3) return 2;
  if (p === 2) return 3;
  return 4;
}

function hhmm(dt, tz = "Europe/Moscow") {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(dt));
}

function hourBucket(dt, tz = "Europe/Moscow") {
  const h = new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    hour: "2-digit",
    hour12: false
  }).format(new Date(dt));
  return Number(h);
}

function overlapMinutes(s1, e1, s2, e2) {
  const s = Math.max(s1, s2);
  const e = Math.min(e1, e2);
  return Math.max(0, Math.round((e - s) / 60000));
}

export function collectTaskSnapshotTelemetry(cfg, tasks, now = new Date()) {
  if (!isProfileEnabled(cfg.stateDir, cfg.profileEnabledDefault !== false)) return;

  const todayIso = dateISOInTz(now, cfg.tz);
  const key = stateFile(cfg.stateDir, "personal_last_open_tasks.json");
  const markFile = stateFile(cfg.stateDir, "personal_overdue_marks.json");

  const prev = readJson(key, { byId: {} });
  const marks = readJson(markFile, { map: {} });

  const nowIso = now.toISOString();
  const currentById = {};
  for (const t of tasks || []) {
    const id = String(t.id || "");
    if (!id) continue;
    currentById[id] = {
      id,
      priority: mapPriority(t),
      due_datetime: t.dueDateTime || t.dueDate || null,
      content: String(t.content || "")
    };

    if (!prev.byId[id]) {
      insertTaskEvent(cfg.stateDir, {
        task_id: id,
        ts: nowIso,
        event_type: "created",
        priority: currentById[id].priority,
        due_datetime: currentById[id].due_datetime,
        source: "snapshot"
      });
      upsertDailyMetrics(cfg.stateDir, todayIso, { tasks_created: 1 });
    }
  }

  for (const [id, oldTask] of Object.entries(prev.byId || {})) {
    if (!currentById[id]) {
      insertTaskEvent(cfg.stateDir, {
        task_id: id,
        ts: nowIso,
        event_type: "completed",
        priority: Number(oldTask.priority || 3),
        due_datetime: oldTask.due_datetime || null,
        source: "snapshot"
      });
      const p = Number(oldTask.priority || 3);
      const patch = { tasks_completed: 1 };
      patch[`p${p}_completed`] = 1;
      upsertDailyMetrics(cfg.stateDir, todayIso, patch);
    }
  }

  for (const t of tasks || []) {
    const id = String(t.id || "");
    if (!id) continue;
    const due = toDatePart(t);
    if (!due || due >= todayIso) continue;

    const dayKey = `${todayIso}:${id}`;
    if (marks.map[dayKey]) continue;

    insertTaskEvent(cfg.stateDir, {
      task_id: id,
      ts: nowIso,
      event_type: "overdue",
      priority: mapPriority(t),
      due_datetime: t.dueDateTime || t.dueDate || null,
      source: "snapshot"
    });
    upsertDailyMetrics(cfg.stateDir, todayIso, { tasks_overdue: 1 });
    marks.map[dayKey] = nowIso;
  }

  const keepPrefix = `${todayIso.slice(0, 7)}-`;
  marks.map = Object.fromEntries(Object.entries(marks.map || {}).filter(([k]) => k.startsWith(keepPrefix)));

  writeJson(key, { byId: currentById, ts: nowIso });
  writeJson(markFile, marks);
}

export function collectAgendaTelemetry(cfg, agenda) {
  if (!isProfileEnabled(cfg.stateDir, cfg.profileEnabledDefault !== false)) return;
  const dateIso = agenda?.date;
  if (!dateIso) return;

  const meetings = agenda.meetings || [];
  const freeSlots = agenda.freeSlots || [];

  let meetingsMinutes = 0;
  for (const m of meetings) {
    if (m?.isAllDay) continue;
    const s = new Date(m.start).getTime();
    const e = new Date(m.end).getTime();
    if (!Number.isFinite(s) || !Number.isFinite(e)) continue;
    meetingsMinutes += Math.max(0, Math.round((e - s) / 60000));
  }

  const freeMinutes = freeSlots.reduce((acc, s) => {
    const a = String(s.start || "").match(/^(\d{2}):(\d{2})$/);
    const b = String(s.end || "").match(/^(\d{2}):(\d{2})$/);
    if (!a || !b) return acc;
    const start = Number(a[1]) * 60 + Number(a[2]);
    const end = Number(b[1]) * 60 + Number(b[2]);
    return acc + Math.max(0, end - start);
  }, 0);

  upsertDailyMetrics(cfg.stateDir, dateIso, {
    meetings_minutes: meetingsMinutes,
    free_minutes: freeMinutes
  });

  for (let h = 6; h <= 23; h += 1) {
    const bStart = new Date(`${dateIso}T${String(h).padStart(2, "0")}:00:00+03:00`).getTime();
    const bEnd = new Date(`${dateIso}T${String(h + 1).padStart(2, "0")}:00:00+03:00`).getTime();
    let count = 0;
    let mins = 0;
    for (const m of meetings) {
      if (m?.isAllDay) continue;
      const s = new Date(m.start).getTime();
      const e = new Date(m.end).getTime();
      if (!Number.isFinite(s) || !Number.isFinite(e)) continue;
      const ov = overlapMinutes(s, e, bStart, bEnd);
      if (ov > 0) {
        count += 1;
        mins += ov;
      }
    }
    upsertMeetingBucket(cfg.stateDir, dateIso, h, count, mins);
  }
}

export function recordTaskCreateTelemetry(cfg, taskLike, source = "text") {
  if (!isProfileEnabled(cfg.stateDir, cfg.profileEnabledDefault !== false)) return;
  const now = new Date();
  const dateIso = dateISOInTz(now, cfg.tz);
  insertTaskEvent(cfg.stateDir, {
    task_id: String(taskLike.id || `tmp_${now.getTime()}`),
    ts: now.toISOString(),
    event_type: "created",
    priority: mapPriority(taskLike),
    due_datetime: taskLike.dueDateTime || taskLike.dueDate || null,
    source
  });
  upsertDailyMetrics(cfg.stateDir, dateIso, { tasks_created: 1 });
}

export function recordAssistantEvent(cfg, eventType, context = "generic", payload = null) {
  if (!isProfileEnabled(cfg.stateDir, cfg.profileEnabledDefault !== false)) return;
  insertAssistantEvent(cfg.stateDir, {
    ts: new Date().toISOString(),
    event_type: eventType,
    context,
    payload_json: payload || undefined
  });
}

export function getAssistantLastEvent(cfg, eventType, maxAgeMin = 120) {
  const row = queryOne(cfg.stateDir, `
    SELECT ts, context, payload_json
    FROM assistant_events
    WHERE event_type = ?
      AND ts >= datetime('now', ?)
    ORDER BY ts DESC
    LIMIT 1
  `, [eventType, `-${Number(maxAgeMin || 120)} minutes`]);
  return row || null;
}

export function inferAssistantReactionFromMessage(cfg, text) {
  const t = String(text || "").trim().toLowerCase();
  if (!t) return;

  if (/^(ок|окей|сделал|готово|принял|да)$/i.test(t)) {
    recordAssistantEvent(cfg, "suggestion_accepted", "chat_reply", { text: t });
    return;
  }

  if (/^(позже|не сейчас|потом|нет)$/i.test(t)) {
    recordAssistantEvent(cfg, "suggestion_ignored", "chat_reply", { text: t });
  }
}
