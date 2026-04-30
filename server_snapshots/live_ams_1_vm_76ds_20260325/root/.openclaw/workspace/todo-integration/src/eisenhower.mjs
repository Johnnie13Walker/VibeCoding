import { addDaysISO } from "./time.mjs";
import { toDatePart, toTimePart } from "./service.mjs";

const DEFAULT_IMPORTANT_WORDS = [
  "клиент",
  "договор",
  "деньги",
  "оплата",
  "дедлайн",
  "проект",
  "встреча",
  "отч",
  "kpi",
  "презентац"
];

const DEFAULT_NOT_IMPORTANT_WORDS = [
  "почитать",
  "посмотреть",
  "идея",
  "на будущее",
  "когда-нибудь"
];

function normalize(s = "") {
  return String(s).toLowerCase();
}

function hasAny(text, words) {
  return words.some((w) => text.includes(w));
}

function todoistPriorityToInternal(priorityNum) {
  const n = Number(priorityNum || 2);
  if (n >= 4) return "P1";
  if (n === 3) return "P2";
  if (n === 2) return "P3";
  return "P4";
}

export function resolveImportantKeywords(cfg) {
  const raw = String(cfg.eisenhowerImportantKeywords || "").trim();
  if (!raw) return DEFAULT_IMPORTANT_WORDS;
  return raw.split(",").map((x) => x.trim().toLowerCase()).filter(Boolean);
}

export function evaluateImportant(task, cfg) {
  const text = normalize(task.content || "");
  const importantWords = resolveImportantKeywords(cfg);

  let score = 0.5;
  const p = task.priorityInternal || todoistPriorityToInternal(task.todoistPriority || task.priority);
  if (p === "P1" || p === "P2") score = Math.max(score, 0.8);
  if (p === "P4") score = Math.min(score, 0.25);

  if (hasAny(text, importantWords)) score = Math.max(score, 0.85);
  if (hasAny(text, DEFAULT_NOT_IMPORTANT_WORDS)) score = Math.min(score, 0.2);

  return {
    score,
    value: score > 0.6
  };
}

export function evaluateUrgent(task, todayIso, tz) {
  const text = normalize(task.content || "");
  const due = toDatePart(task);
  const time = toTimePart(task, tz);

  let score = 0.2;

  if (/(срочно|горит|сегодня обязательно|немедленно|asap)/i.test(text)) score = Math.max(score, 0.9);
  if (/(потом|когда будет время|не срочно)/i.test(text)) score = Math.min(score, 0.25);

  if (!due) {
    return { score: Math.max(0, score), value: score > 0.6 };
  }

  if (due < todayIso) score = Math.max(score, 1);
  if (due === todayIso) score = Math.max(score, 0.95);

  const tomorrowIso = addDaysISO(todayIso, 1);
  if (due === tomorrowIso && time) {
    const [h] = time.split(":").map(Number);
    if (Number.isFinite(h) && h < 12) score = Math.max(score, 0.75);
  }

  const farIso = addDaysISO(todayIso, 3);
  if (due > farIso) score = Math.min(score, 0.3);

  return { score, value: score > 0.6 };
}

export function quadrantFrom(urgent, important) {
  if (urgent && important) return "Q1";
  if (!urgent && important) return "Q2";
  if (urgent && !important) return "Q3";
  return "Q4";
}

export function classifyTask(task, ctx) {
  const important = evaluateImportant(task, ctx.cfg);
  const urgent = evaluateUrgent(task, ctx.todayIso, ctx.tz);
  const quadrant = quadrantFrom(urgent.value, important.value);

  return {
    ...task,
    urgentScore: Number(urgent.score.toFixed(2)),
    importantScore: Number(important.score.toFixed(2)),
    quadrant
  };
}

export function classifyTasks(tasks, ctx) {
  return tasks.map((t) => classifyTask(t, ctx));
}

export function splitByQuadrant(tasks) {
  return {
    Q1: tasks.filter((t) => t.quadrant === "Q1"),
    Q2: tasks.filter((t) => t.quadrant === "Q2"),
    Q3: tasks.filter((t) => t.quadrant === "Q3"),
    Q4: tasks.filter((t) => t.quadrant === "Q4")
  };
}

function dueSortValue(task) {
  const d = toDatePart(task) || "9999-99-99";
  const t = task.dueDateTime || `${d}T23:59:59`;
  return `${d}|${t}`;
}

function shortness(task) {
  const txt = String(task.content || "");
  return txt.length;
}

export function suggestExecutionOrder(tasks) {
  const groups = splitByQuadrant(tasks);
  const q1 = groups.Q1.slice().sort((a, b) => dueSortValue(a).localeCompare(dueSortValue(b)));
  const q2 = groups.Q2.slice().sort((a, b) => (b.todoistPriority || b.priority || 2) - (a.todoistPriority || a.priority || 2));
  const q3 = groups.Q3.slice().sort((a, b) => shortness(a) - shortness(b));
  const q4 = groups.Q4.slice();
  return [...q1, ...q2, ...q3, ...q4];
}

export function buildInsights14Days(historyEntries) {
  const counts = { Q1: 0, Q2: 0, Q3: 0, Q4: 0 };
  let stuckQ3 = 0;
  let stuckQ4 = 0;
  let q12Morning = 0;
  let q12Evening = 0;

  for (const e of historyEntries) {
    counts.Q1 += Number(e.Q1 || 0);
    counts.Q2 += Number(e.Q2 || 0);
    counts.Q3 += Number(e.Q3 || 0);
    counts.Q4 += Number(e.Q4 || 0);
    if (e.slot === "evening") {
      stuckQ3 += Number(e.Q3 || 0);
      stuckQ4 += Number(e.Q4 || 0);
      q12Evening += Number(e.Q1 || 0) + Number(e.Q2 || 0);
    }
    if (e.slot === "morning") {
      q12Morning += Number(e.Q1 || 0) + Number(e.Q2 || 0);
    }
  }

  const closurePct = q12Morning > 0 ? Math.max(0, Math.min(100, Math.round(((q12Morning - q12Evening) / q12Morning) * 100))) : 100;
  const stuck = stuckQ3 >= stuckQ4 ? "Q3" : "Q4";

  return { counts, stuck, closurePct };
}
