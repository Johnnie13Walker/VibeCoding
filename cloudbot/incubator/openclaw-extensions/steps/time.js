export const DEFAULT_TIMEZONE = 'Europe/Moscow';

function partsMap(date, timeZone) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    weekday: 'short',
  }).formatToParts(date);

  const out = {};
  for (const p of parts) {
    if (p.type !== 'literal') out[p.type] = p.value;
  }
  return out;
}

export function zonedDateParts(date, timeZone = DEFAULT_TIMEZONE) {
  const p = partsMap(date, timeZone);
  return {
    year: Number(p.year),
    month: Number(p.month),
    day: Number(p.day),
    hour: Number(p.hour),
    minute: Number(p.minute),
    weekday: String(p.weekday || ''),
  };
}

export function dayKey(date, timeZone = DEFAULT_TIMEZONE) {
  const p = zonedDateParts(date, timeZone);
  const mm = String(p.month).padStart(2, '0');
  const dd = String(p.day).padStart(2, '0');
  return `${p.year}-${mm}-${dd}`;
}

export function hourFloat(date, timeZone = DEFAULT_TIMEZONE) {
  const p = zonedDateParts(date, timeZone);
  return p.hour + p.minute / 60;
}

export function hourInt(date, timeZone = DEFAULT_TIMEZONE) {
  return zonedDateParts(date, timeZone).hour;
}

export function formatHour(hour) {
  return `${String(hour).padStart(2, '0')}:00`;
}

export function formatHourWindow(hour) {
  const next = Math.min(hour + 1, 23);
  return `${formatHour(hour)}-${formatHour(next)}`;
}
