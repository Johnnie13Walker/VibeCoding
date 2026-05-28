import { MOSCOW_TZ } from "./config.mjs";

export function datePartsInTz(date = new Date(), tz = MOSCOW_TZ) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(date);
  const pick = (t) => parts.find((p) => p.type === t)?.value;
  return { year: pick("year"), month: pick("month"), day: pick("day") };
}

export function dateISOInTz(date = new Date(), tz = MOSCOW_TZ) {
  const p = datePartsInTz(date, tz);
  return `${p.year}-${p.month}-${p.day}`;
}

export function addDaysISO(iso, days) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function formatRuDateFromISO(iso) {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}`;
}

export function parseMoscowDateArg(arg, todayIso) {
  const raw = (arg || "").trim().toLowerCase();
  if (!raw || raw === "today") return { ok: true, iso: todayIso };
  if (raw === "tomorrow") return { ok: true, iso: addDaysISO(todayIso, 1) };
  if (raw === "aftertomorrow") return { ok: true, iso: addDaysISO(todayIso, 2) };
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return { ok: true, iso: raw };
  return { ok: false, error: "Неверная дата. Используйте: today|tomorrow|aftertomorrow|YYYY-MM-DD" };
}
