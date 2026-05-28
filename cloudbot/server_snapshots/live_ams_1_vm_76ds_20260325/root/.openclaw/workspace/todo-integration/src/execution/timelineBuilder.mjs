function hhmmToMinutes(v) {
  const m = String(v || "").match(/^(\d{2}):(\d{2})$/);
  if (!m) return null;
  return Number(m[1]) * 60 + Number(m[2]);
}

function minsDiff(start, end) {
  const s = hhmmToMinutes(start);
  const e = hhmmToMinutes(end);
  if (s == null || e == null) return 0;
  return Math.max(0, e - s);
}

function toHHMM(dt, tz) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(dt));
}

function mapPriority(task) {
  const p = Number(task.priority || task.todoistPriority || 2);
  if (p >= 4) return 1;
  if (p === 3) return 2;
  if (p === 2) return 3;
  return 4;
}

function normalizeTaskTitle(content = "") {
  return String(content)
    .replace(/\[[^\]]+\]\((https?:\/\/[^\s)]+)\)/gi, " ")
    .replace(/https?:\/\/\S+/gi, " ")
    .replace(/\s+/g, " ")
    .trim() || "Задача";
}

function pickFocusTasks(tasks, n = 2) {
  return [...(tasks || [])]
    .map((t) => ({ ...t, displayPriority: mapPriority(t), title: normalizeTaskTitle(t.content) }))
    .sort((a, b) => a.displayPriority - b.displayPriority)
    .slice(0, n);
}

function summarizeMeetings(meetings, tz) {
  const timed = (meetings || [])
    .filter((m) => !m?.isAllDay)
    .sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime());

  if (!timed.length) return null;
  const first = timed[0];
  const last = timed[timed.length - 1];
  return `${toHHMM(first.start, tz)}–${toHHMM(last.end, tz)} → встречи`;
}

export function buildDayTimeline(agenda, cfg) {
  const lines = [];
  const deep = (agenda?.freeSlots || []).filter((s) => minsDiff(s.start, s.end) >= 60);
  const short = (agenda?.freeSlots || []).filter((s) => minsDiff(s.start, s.end) >= 20 && minsDiff(s.start, s.end) <= 40);
  const meetingsBand = summarizeMeetings(agenda?.meetings || [], cfg.tz);

  if (deep.length) lines.push(`${deep[0].start}–${deep[0].end} → лучшее окно для задач`);
  if (meetingsBand) lines.push(meetingsBand);
  if (deep.length > 1) lines.push(`${deep[1].start}–${deep[1].end} → deep work`);
  else if (short.length) lines.push(`${short[0].start}–${short[0].end} → короткие задачи`);

  return lines.slice(0, 4);
}

export function buildDayScenarioMessage(agenda, cfg) {
  const timeline = buildDayTimeline(agenda, cfg);
  const focus = pickFocusTasks(agenda?.tasks || [], 2);
  const lines = ["🧭 Сценарий дня", ""];

  if (!timeline.length) {
    lines.push(`${cfg.workdayStart}–${cfg.workdayEnd} → свободное окно для задач`);
  } else {
    lines.push(...timeline);
  }

  if (focus.length) {
    lines.push("", "🎯 Фокус:");
    focus.forEach((t) => lines.push(`• ${t.title}`));
  }

  return lines.join("\n");
}
