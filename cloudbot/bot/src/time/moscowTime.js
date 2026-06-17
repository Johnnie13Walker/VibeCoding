const MOSCOW_TZ = "Europe/Moscow";

function pad2(value) {
  return String(value).padStart(2, "0");
}

export function getMoscowParts(timestampMs = Date.now()) {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: MOSCOW_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  });

  const parts = formatter.formatToParts(new Date(timestampMs));
  const byType = Object.fromEntries(parts.map((p) => [p.type, p.value]));

  return {
    year: Number(byType.year),
    month: Number(byType.month),
    day: Number(byType.day),
    hour: Number(byType.hour),
    minute: Number(byType.minute)
  };
}

export function toMoscowDateString(timestampMs = Date.now()) {
  const p = getMoscowParts(timestampMs);
  return `${p.year}-${pad2(p.month)}-${pad2(p.day)}`;
}

export function toMoscowTimeString(timestampMs = Date.now()) {
  const p = getMoscowParts(timestampMs);
  return `${pad2(p.hour)}:${pad2(p.minute)}`;
}

export function parseMoscowDate(dateString) {
  const m = String(dateString || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return null;

  const year = Number(m[1]);
  const month = Number(m[2]);
  const day = Number(m[3]);
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;

  return { year, month, day };
}

export function parseMoscowTime(timeString) {
  const m = String(timeString || "").match(/^(\d{2}):(\d{2})$/);
  if (!m) return null;

  const hour = Number(m[1]);
  const minute = Number(m[2]);
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;

  return { hour, minute };
}

export function toUnixSecondsFromMoscowDateTime(dateString, timeString) {
  const date = parseMoscowDate(dateString);
  const time = parseMoscowTime(timeString);
  if (!date || !time) return null;

  const utcMs = Date.UTC(
    date.year,
    date.month - 1,
    date.day,
    time.hour - 3,
    time.minute,
    0,
    0
  );
  return Math.floor(utcMs / 1000);
}

export function compareMoscowDates(a, b) {
  if (a === b) return 0;
  return a < b ? -1 : 1;
}

export { MOSCOW_TZ };
