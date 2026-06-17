function hhmmToMinutes(v) {
  const [h, m] = String(v).split(":").map((x) => Number(x));
  return h * 60 + m;
}

function toMoscowMinutes(dt, tz = "Europe/Moscow") {
  const hh = new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", hour12: false }).format(new Date(dt));
  const mm = new Intl.DateTimeFormat("en-GB", { timeZone: tz, minute: "2-digit", hour12: false }).format(new Date(dt));
  return Number(hh) * 60 + Number(mm);
}

function minutesToHHMM(total) {
  const h = String(Math.floor(total / 60)).padStart(2, "0");
  const m = String(total % 60).padStart(2, "0");
  return `${h}:${m}`;
}

export function computeFreeSlots(meetings, opts = {}) {
  const tz = opts.tz || "Europe/Moscow";
  const ws = hhmmToMinutes(opts.workdayStart || "09:00");
  const we = hhmmToMinutes(opts.workdayEnd || "19:00");
  const minLen = Number(opts.minMinutes || 30);

  const timed = (meetings || [])
    .filter((m) => !m.isAllDay)
    .map((m) => ({ start: toMoscowMinutes(m.start, tz), end: toMoscowMinutes(m.end, tz) }))
    .sort((a, b) => a.start - b.start);

  const merged = [];
  for (const t of timed) {
    if (!merged.length || t.start > merged[merged.length - 1].end) merged.push({ ...t });
    else merged[merged.length - 1].end = Math.max(merged[merged.length - 1].end, t.end);
  }

  const slots = [];
  let cursor = ws;
  for (const m of merged) {
    if (m.start > cursor && m.start - cursor >= minLen) {
      slots.push({ start: minutesToHHMM(cursor), end: minutesToHHMM(m.start) });
    }
    cursor = Math.max(cursor, m.end);
  }

  if (we > cursor && we - cursor >= minLen) {
    slots.push({ start: minutesToHHMM(cursor), end: minutesToHHMM(we) });
  }

  return slots;
}
