import {
  toMoscowDateString,
  parseMoscowDate,
  parseMoscowTime,
  toUnixSecondsFromMoscowDateTime
} from "../time/moscowTime.js";

function normalizeTaskId(rawTask, index) {
  const value = rawTask?.id ?? rawTask?.taskId ?? rawTask?.externalId;
  if (value === undefined || value === null || value === "") {
    return `task_${index + 1}`;
  }
  return String(value);
}

function pickTitle(rawTask, index) {
  const title = rawTask?.title || rawTask?.name || rawTask?.text;
  if (title && String(title).trim()) return String(title).trim();
  return `Задача ${index + 1}`;
}

function normalizeDueDate(rawDueDate, rawDueTime, nowTs) {
  const dateCandidate = rawDueDate ? String(rawDueDate).trim() : "";
  if (parseMoscowDate(dateCandidate)) return dateCandidate;
  if (rawDueTime && parseMoscowTime(String(rawDueTime).trim())) {
    return toMoscowDateString(nowTs);
  }
  return null;
}

function normalizeDueTime(rawDueTime) {
  const timeCandidate = rawDueTime ? String(rawDueTime).trim() : "";
  if (!timeCandidate) return null;
  return parseMoscowTime(timeCandidate) ? timeCandidate : null;
}

function isTaskClosed(rawTask) {
  return Boolean(
    rawTask?.isClosed ||
      rawTask?.closed ||
      rawTask?.isDone ||
      rawTask?.done ||
      rawTask?.completed
  );
}

export function normalizeTask(rawTask, { nowTs = Date.now(), index = 0 } = {}) {
  const dueTime = normalizeDueTime(rawTask?.dueTime);
  const dueDate = normalizeDueDate(rawTask?.dueDate, dueTime, nowTs);
  const computedDueDateTime =
    dueDate && dueTime
      ? toUnixSecondsFromMoscowDateTime(dueDate, dueTime)
      : null;

  return {
    id: normalizeTaskId(rawTask, index),
    title: pickTitle(rawTask, index),
    dueDate,
    dueTime,
    computedDueDateTime,
    project: rawTask?.project || rawTask?.projectName || null,
    label: rawTask?.label || rawTask?.tag || null,
    isClosed: isTaskClosed(rawTask),
    raw: rawTask
  };
}

export function normalizeTasks(rawTasks, { nowTs = Date.now() } = {}) {
  const rows = Array.isArray(rawTasks) ? rawTasks : [];
  return rows.map((task, index) => normalizeTask(task, { nowTs, index }));
}
