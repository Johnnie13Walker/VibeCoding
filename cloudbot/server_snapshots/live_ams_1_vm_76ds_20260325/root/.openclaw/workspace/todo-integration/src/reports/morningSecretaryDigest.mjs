import { extractOtherAttendees, renderDailyCalendarDigest } from "./calendarDailyRenderer.mjs";

function escapeHtml(s = "") {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function hhmm(dt, tz = "Europe/Moscow") {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(dt));
}

function normalizeMyUserCode(cfg = {}) {
  const raw = String(cfg?.bitrixUserId || "").trim();
  if (!raw) return "";
  const m = raw.match(/^[Uu](\d+)$/);
  if (m) return `U${m[1]}`;
  if (/^\d+$/.test(raw)) return `U${raw}`;
  return raw.toUpperCase();
}

function formatAttendeesInline(list = []) {
  const names = list.map((x) => String(x || "").trim()).filter(Boolean);
  if (!names.length) return "";
  const shown = names.slice(0, 5).map((x) => `<b>${escapeHtml(x)}</b>`);
  const extra = names.length - shown.length;
  return extra > 0 ? ` (с: ${shown.join(", ")} + ещё ${extra})` : ` (с: ${shown.join(", ")})`;
}

export function formatMeetingLine(meeting, cfg) {
  const tz = cfg?.tz || "Europe/Moscow";
  const time = meeting?.isAllDay ? "Весь день" : `${hhmm(meeting?.start, tz)}–${hhmm(meeting?.end, tz)}`;
  const attendees = extractOtherAttendees(meeting, normalizeMyUserCode(cfg));
  return `${time}  ${escapeHtml(meeting?.title || "Без названия")}${formatAttendeesInline(attendees)}`;
}

export function formatMorningSecretaryDigest(agenda, cfg, opts = {}) {
  let text = renderDailyCalendarDigest({
    agenda,
    cfg,
    myUserCode: normalizeMyUserCode(cfg)
  });

  if (opts.withHintTomorrow) {
    text += "\n\nКоманда: /day tomorrow";
  }

  return text;
}

export function formatAgendaOnly(agenda, cfg) {
  const meetings = Array.isArray(agenda?.meetings) ? agenda.meetings : [];
  const date = String(agenda?.date || "");
  const dateLabel = date ? `${date.slice(8, 10)}.${date.slice(5, 7)}.${date.slice(0, 4)}` : date;
  const lines = [`Календарь на ${dateLabel}`, ""];
  if (!meetings.length) return `Календарь на ${dateLabel}\n\nНа этот день встреч нет.`;
  meetings.slice(0, 20).forEach((m, i) => lines.push(`${i + 1}. ${formatMeetingLine(m, cfg)}`));
  if (meetings.length > 20) lines.push(`ещё ${meetings.length - 20}`);
  return lines.join("\n");
}

export function formatFreeSlotsOnly(agenda) {
  const free = Array.isArray(agenda?.freeSlots) ? agenda.freeSlots : [];
  if (!free.length) return "Свободные слоты\n\nСвободных окон нет.";
  return ["Свободные слоты", "", ...free.map((s) => `${s.start}–${s.end}`)].join("\n");
}
