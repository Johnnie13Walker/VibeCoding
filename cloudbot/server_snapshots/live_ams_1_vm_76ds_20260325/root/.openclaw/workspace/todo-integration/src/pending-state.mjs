import fs from "node:fs";
import path from "node:path";

const FILE = "pending_tasks.json";
const TTL_MS = 30 * 60 * 1000;

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function readState(stateDir) {
  ensureDir(stateDir);
  const p = path.join(stateDir, FILE);
  if (!fs.existsSync(p)) return { users: {} };
  try {
    const data = JSON.parse(fs.readFileSync(p, "utf8"));
    if (!data.users || typeof data.users !== "object") return { users: {} };
    return data;
  } catch {
    return { users: {} };
  }
}

function writeState(stateDir, data) {
  ensureDir(stateDir);
  fs.writeFileSync(path.join(stateDir, FILE), JSON.stringify(data, null, 2));
}

function fallbackPriorityIfExpired(pending) {
  const next = { ...pending };

  if (next.step === "await_priority") {
    next.step = "await_confirm";
    next.priority = "P3";
    next.todoistPriority = 2;
    next.priorityConfidence = 0;
    return next;
  }

  if (next.step === "voice_waiting_priority_resolution") {
    if (Array.isArray(next.tasks)) {
      next.tasks = next.tasks.map((task) => ({
        ...task,
        priority: task.priority || "P3",
        todoistPriority: task.todoistPriority || 2,
        priorityConfidence: task.priorityConfidence ?? 0
      }));
    }
    next.step = "voice_waiting_confirmation";
    next.unresolvedPriorityIndexes = [];
    next.priorityCursor = 0;
    return next;
  }

  return null;
}

export function getPending(stateDir, userId) {
  const s = readState(stateDir);
  const p = s.users[String(userId)];
  if (!p) return null;
  const createdAt = new Date(p.created_at || 0).getTime();
  if (!createdAt || Date.now() - createdAt > TTL_MS) {
    const fallback = fallbackPriorityIfExpired(p);
    if (fallback) {
      s.users[String(userId)] = { ...fallback, created_at: new Date().toISOString() };
      writeState(stateDir, s);
      return s.users[String(userId)];
    }
    delete s.users[String(userId)];
    writeState(stateDir, s);
    return null;
  }
  return p;
}

export function setPending(stateDir, userId, pending) {
  const s = readState(stateDir);
  s.users[String(userId)] = { ...pending, created_at: new Date().toISOString() };
  writeState(stateDir, s);
}

export function clearPending(stateDir, userId) {
  const s = readState(stateDir);
  if (s.users[String(userId)]) {
    delete s.users[String(userId)];
    writeState(stateDir, s);
  }
}
