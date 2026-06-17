import { createProvider } from "../provider-factory.mjs";
import { filterOverdue, filterTasksForDate } from "../service.mjs";
import { dedupeMeetings } from "./merge.mjs";
import { computeFreeSlots } from "./freeSlots.mjs";
import { fetchGoogleAgendaForDate, googleConnected } from "./providers/googleCalendar.mjs";
import { fetchBitrixAgendaForDate, bitrixConnected } from "./providers/bitrixCalendar.mjs";
import { markAgendaSync } from "./state.mjs";
import { collectAgendaTelemetry } from "../personal/telemetryCollector.mjs";

function mapTaskPriority(task) {
  const p = Number(task.priority || task.todoistPriority || 2);
  if (p >= 4) return 1;
  if (p === 3) return 2;
  if (p === 2) return 3;
  return 4;
}

function pickFocus(tasks) {
  return tasks
    .map((t) => ({ ...t, displayPriority: mapTaskPriority(t) }))
    .sort((a, b) => a.displayPriority - b.displayPriority)
    .slice(0, 2);
}

function normalizeError(err) {
  return String(err?.message || err || "todo_unavailable")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 240);
}

function dateIsoInTz(dt, tz = "Europe/Moscow") {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(new Date(dt));

  const y = parts.find((p) => p.type === "year")?.value;
  const m = parts.find((p) => p.type === "month")?.value;
  const d = parts.find((p) => p.type === "day")?.value;
  if (!y || !m || !d) return null;
  return `${y}-${m}-${d}`;
}

function filterMeetingsByDate(meetings, dateISO, tz) {
  return (meetings || []).filter((m) => {
    if (!m?.start) return false;
    const startIso = dateIsoInTz(m.start, tz);
    if (!startIso) return false;
    if (startIso === dateISO) return true;

    if (!m?.end) return false;
    const endIso = dateIsoInTz(m.end, tz);
    if (!endIso) return false;
    return dateISO >= startIso && dateISO <= endIso;
  });
}

export async function getAgenda(cfg, dateISO, opts = {}) {
  const prefetchedTasks = Array.isArray(opts.prefetchedTasks) ? opts.prefetchedTasks : null;
  const skipTodoFetch = opts.skipTodoFetch === true;
  const todoWarning = String(opts.todoWarning || "").trim();

  let allTasks = [];
  let todoConnected = true;
  let todoIssue = "";

  if (skipTodoFetch) {
    allTasks = prefetchedTasks || [];
    todoConnected = false;
    todoIssue = todoWarning || "todo_fetch_skipped";
    markAgendaSync(cfg.stateDir, "todo", false, todoIssue);
  } else if (prefetchedTasks !== null) {
    allTasks = prefetchedTasks;
    markAgendaSync(cfg.stateDir, "todo", true);
  } else {
    try {
      const provider = createProvider(cfg);
      allTasks = await provider.getAllOpenTasks();
      markAgendaSync(cfg.stateDir, "todo", true);
    } catch (err) {
      allTasks = [];
      todoConnected = false;
      todoIssue = normalizeError(err);
      markAgendaSync(cfg.stateDir, "todo", false, todoIssue);
    }
  }

  const tasks = filterTasksForDate(allTasks, dateISO);
  const overdue = filterOverdue(allTasks, dateISO);

  const [googleIsConnected, bitrixIsConnected] = await Promise.all([
    googleConnected(cfg),
    bitrixConnected(cfg)
  ]);

  const [googleMeetings, bitrixMeetings] = await Promise.all([
    fetchGoogleAgendaForDate(cfg, dateISO),
    fetchBitrixAgendaForDate(cfg, dateISO)
  ]);

  const dedupedMeetings = dedupeMeetings([...(googleMeetings || []), ...(bitrixMeetings || [])]);
  const meetings = filterMeetingsByDate(dedupedMeetings, dateISO, cfg.tz);
  const freeSlots = computeFreeSlots(meetings, {
    tz: cfg.tz,
    workdayStart: cfg.workdayStart,
    workdayEnd: cfg.workdayEnd,
    minMinutes: cfg.freeSlotMinMinutes
  });

  const focus = pickFocus(tasks);

  const result = {
    date: dateISO,
    meetings,
    tasks,
    overdueCount: overdue.length,
    freeSlots,
    focus,
    sourceStatus: {
      googleConnected: !!googleIsConnected,
      bitrixConnected: !!bitrixIsConnected,
      todoConnected
    }
  };

  if (!todoConnected) {
    result.sourceWarnings = { todo: todoIssue || "todo_unavailable" };
  }

  try {
    collectAgendaTelemetry(cfg, result);
  } catch {
    // no-op telemetry failure
  }

  return result;
}
