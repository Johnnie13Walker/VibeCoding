import { addDaysISO, dateISOInTz } from "./time.mjs";

const weekdayPatterns = [
  { pattern: /(?:^|\s)(?:в|на)?\s*понедельник(?:а|у|ом|е)?(?:[\s,.;]|$)/i, weekday: 1 },
  { pattern: /(?:^|\s)(?:в|на)?\s*вторник(?:а|у|ом|е)?(?:[\s,.;]|$)/i, weekday: 2 },
  { pattern: /(?:^|\s)(?:в|на)?\s*сред(?:а|у|е|ой)(?:[\s,.;]|$)/i, weekday: 3 },
  { pattern: /(?:^|\s)(?:в|на)?\s*четверг(?:а|у|ом|е)?(?:[\s,.;]|$)/i, weekday: 4 },
  { pattern: /(?:^|\s)(?:в|на)?\s*пятниц(?:а|у|е|ы|ой)(?:[\s,.;]|$)/i, weekday: 5 },
  { pattern: /(?:^|\s)(?:в|на)?\s*суббот(?:а|у|е|ы|ой)(?:[\s,.;]|$)/i, weekday: 6 },
  { pattern: /(?:^|\s)(?:в|на)?\s*воскресень(?:е|я|ю|ем|и)(?:[\s,.;]|$)/i, weekday: 0 }
];

function toMoscowWeekday(date = new Date(), tz = "Europe/Moscow") {
  const s = new Intl.DateTimeFormat("en-US", { timeZone: tz, weekday: "short" }).format(date);
  return { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 }[s] ?? 0;
}

function toIsoMskDateForWeekday(targetWeekday, tz = "Europe/Moscow") {
  const todayIso = dateISOInTz(new Date(), tz);
  const current = toMoscowWeekday(new Date(), tz);
  const shiftRaw = (targetWeekday - current + 7) % 7;
  const shift = shiftRaw === 0 ? 7 : shiftRaw;
  return addDaysISO(todayIso, shift);
}

function hasNoDatePhrase(raw) {
  return /(без\s*даты|без\s*срока|без\s*дедлайна|без\s*напоминания)/i.test(raw);
}

function parseDateToken(raw, tz = "Europe/Moscow") {
  const text = raw.toLowerCase();
  const todayIso = dateISOInTz(new Date(), tz);

  if (text.includes("послезавтра")) return { dueDate: addDaysISO(todayIso, 2), token: /послезавтра/i };
  if (text.includes("завтра")) return { dueDate: addDaysISO(todayIso, 1), token: /завтра/i };
  if (text.includes("сегодня")) return { dueDate: todayIso, token: /сегодня/i };

  const inDays = text.match(/через\s+(\d{1,3})\s+д(?:ней|ня|ень|ен|н)/i);
  if (inDays) return { dueDate: addDaysISO(todayIso, Number(inDays[1])), token: inDays[0] };

  for (const entry of weekdayPatterns) {
    const m = raw.match(entry.pattern);
    if (m) {
      return { dueDate: toIsoMskDateForWeekday(entry.weekday, tz), token: m[0].trim() };
    }
  }

  const iso = text.match(/\b(\d{4}-\d{2}-\d{2})\b/);
  if (iso) return { dueDate: iso[1], token: iso[1] };

  const ru = text.match(/\b(\d{2})\.(\d{2})(?:\.(\d{4}))?\b/);
  if (ru) {
    const y = ru[3] ? ru[3] : todayIso.slice(0, 4);
    return { dueDate: `${y}-${ru[2]}-${ru[1]}`, token: ru[0] };
  }

  return null;
}

function parseTime(raw) {
  const m = raw.match(/\b([01]?\d|2[0-3]):([0-5]\d)\b/);
  if (!m) return null;
  return { hh: m[1].padStart(2, "0"), mm: m[2], token: m[0] };
}

function normalizeWhitespace(s) {
  return s.replace(/\s+/g, " ").trim();
}

export function detectAddIntent(text) {
  const t = text.trim().toLowerCase();
  if (t.startsWith("/add")) return { isAdd: true, forced: true };
  if (/^(добавь|добавить|задача|todo|поставь|ставь|напомни)(?:\s|$|[:.,;!?])/i.test(t)) return { isAdd: true, forced: true };
  if (/(задача:|todo:)/i.test(t)) return { isAdd: true, forced: true };
  if (/(?:^|\s)(добавь|добавить|задача|todo|поставь|ставь|напомни|туду|todoist|to-do)(?:\s|$|[:.,;!?])/i.test(t)) return { isAdd: true, forced: false };
  return { isAdd: false, forced: false };
}

export function extractCandidateContent(text) {
  let t = text.trim();
  t = t.replace(/^\/add\s*/i, "");
  t = t.replace(/^\s*(добавь|добавить|задача|todo|поставь|ставь|напомни)\s*:?\s*(?:задач[ауеы]\s+)?/i, "");
  t = t.replace(/(задача:|todo:)/i, "");
  t = t.replace(/^\s*задач[ауеы]\s+/i, "");
  t = t.replace(/\s+(?:в|во)?\s*(?:туду|todo|todoist|to-do)\s*(?:лист|list|листе)?\s*$/i, "");
  return normalizeWhitespace(t);
}

export function parseAddDraft(text, tz = "Europe/Moscow") {
  const candidate = extractCandidateContent(text);
  const dateParsed = parseDateToken(text, tz);
  const timeParsed = parseTime(text);
  const noDate = hasNoDatePhrase(text);

  let content = candidate;
  if (dateParsed?.token) {
    if (typeof dateParsed.token === "string") {
      content = content.replace(dateParsed.token.trim(), "");
    } else {
      content = content.replace(dateParsed.token, "");
    }
  }
  if (timeParsed?.token) content = content.replace(timeParsed.token, "");
  content = normalizeWhitespace(content.replace(/^на\s+/i, "").replace(/[\s,.;:]+$/, ""));

  let dueDate = null;
  let dueDateTime = null;
  let needDateClarify = false;

  if (!noDate) {
    dueDate = dateParsed?.dueDate || null;
    if (timeParsed && dueDate) {
      dueDateTime = `${dueDate}T${timeParsed.hh}:${timeParsed.mm}:00+03:00`;
      dueDate = null;
    } else if (timeParsed && !dueDate) {
      needDateClarify = true;
    }

    if (!dueDate && !dueDateTime && !timeParsed) {
      needDateClarify = true;
    }
  }

  return {
    content,
    dueDate,
    dueDateTime,
    hasTime: !!timeParsed,
    needDateClarify,
    parsed: {
      dateToken: dateParsed?.dueDate || null,
      timeToken: timeParsed ? `${timeParsed.hh}:${timeParsed.mm}` : null,
      noDate
    }
  };
}
