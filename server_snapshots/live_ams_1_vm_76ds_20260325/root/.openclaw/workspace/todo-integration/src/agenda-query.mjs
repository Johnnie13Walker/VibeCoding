import { fileURLToPath } from "node:url";
import { getConfig } from "./config.mjs";
import { dateISOInTz, parseMoscowDateArg } from "./time.mjs";
import { getAgenda } from "./agenda/aggregate.mjs";
import { formatAgendaOnly, formatFreeSlotsOnly, formatMorningSecretaryDigest } from "./reports/morningSecretaryDigest.mjs";
import { classifyBitrixEvent, extractOtherAttendees } from "./reports/calendarDailyRenderer.mjs";
import { buildGoogleConnectUrl, completeGoogleConnect, googleConnected } from "./agenda/providers/googleCalendar.mjs";
import { bitrixConnected, buildBitrixConnectUrl, completeBitrixConnect } from "./agenda/providers/bitrixCalendar.mjs";
import { getBitrixUsersSyncMeta } from "./agenda/providers/bitrixUsers.mjs";
import { loadAgendaSyncStatus } from "./agenda/state.mjs";
import { createProvider } from "./provider-factory.mjs";

function parseDateArgOrToday(arg, todayIso) {
  if (!arg) return { ok: true, iso: todayIso };
  return parseMoscowDateArg(arg, todayIso);
}

function escapeHtml(s = "") {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function toMyUserCode(cfg) {
  const raw = String(cfg?.bitrixUserId || "").trim();
  if (!raw) return "";
  const m = raw.match(/^[Uu](\d+)$/);
  if (m) return `U${m[1]}`;
  if (/^\d+$/.test(raw)) return `U${raw}`;
  return raw.toUpperCase();
}

function diagSampleLine(label, event, myUserCode) {
  if (!event) return `<b>${label}:</b> —`;
  const title = escapeHtml(event?.title || event?.NAME || event?.name || "Без названия");
  const count = extractOtherAttendees(event, myUserCode).length;
  return `<b>${label}:</b> ${title} (участников: ${count})`;
}

function formatDiagHtml({ agenda, cfg, dateIso }) {
  const myUserCode = toMyUserCode(cfg);
  const events = Array.isArray(agenda?.meetings) ? agenda.meetings : [];
  const buckets = {
    meeting: [],
    work_block: [],
    personal_block: []
  };

  events.forEach((event) => {
    const type = classifyBitrixEvent(event, { myUserId: cfg?.bitrixUserId, myUserCode });
    if (!buckets[type]) buckets.work_block.push(event);
    else buckets[type].push(event);
  });

  return [
    "🧪 <b>/diag календаря</b>",
    `<b>timezone:</b> ${escapeHtml(cfg?.tz || "Europe/Moscow")}`,
    `<b>myUserCode:</b> ${escapeHtml(myUserCode || "не задан")}`,
    `<b>дата:</b> ${escapeHtml(dateIso)}`,
    `<b>событий получено:</b> ${events.length}`,
    `<b>classified:</b> meetings=${buckets.meeting.length} • work=${buckets.work_block.length} • personal=${buckets.personal_block.length}`,
    diagSampleLine("meeting", buckets.meeting[0], myUserCode),
    diagSampleLine("work_block", buckets.work_block[0], myUserCode),
    diagSampleLine("personal_block", buckets.personal_block[0], myUserCode)
  ].join("\n");
}

export async function runAgendaCommand(cmdRaw, argRaw = "") {
  const cmd = String(cmdRaw || "").trim().toLowerCase();
  const arg = String(argRaw || "").trim();
  const cfg = getConfig();
  const todayIso = dateISOInTz(new Date(), cfg.tz);

  if (cmd === "connect_google") {
    const r = buildGoogleConnectUrl(cfg);
    if (!r.ok) return r.error;
    return `Подключение Google Calendar:\n${r.url}\n\nПосле авторизации пришлите: /oauth_google <callback_url>`;
  }

  if (cmd === "oauth_google") {
    const r = await completeGoogleConnect(cfg, arg);
    return r.ok ? "Google Calendar подключено ✅" : `Google connect error: ${r.error}`;
  }

  if (cmd === "connect_bitrix") {
    const r = buildBitrixConnectUrl(cfg);
    if (!r.ok) return r.error;
    return `Подключение Bitrix24 Calendar:\n${r.url}\n\nПосле авторизации пришлите: /oauth_bitrix <callback_url>`;
  }

  if (cmd === "oauth_bitrix") {
    const r = await completeBitrixConnect(cfg, arg);
    return r.ok ? "Bitrix24 Calendar подключено ✅" : `Bitrix connect error: ${r.error}`;
  }

  if (cmd === "sync_status") {
    const status = loadAgendaSyncStatus(cfg.stateDir);
    const g = await googleConnected(cfg);
    const b = await bitrixConnected(cfg);

    let todoOk = false;
    try {
      const p = createProvider(cfg);
      await p.getTasksForDate(todayIso);
      todoOk = true;
    } catch {
      todoOk = false;
    }

    const usersMeta = getBitrixUsersSyncMeta(cfg.stateDir);

    return [
      "🔄 Статус синхронизации",
      `Google: ${g ? "connected" : "not connected"}${status.google?.last_success_at ? ` (last: ${status.google.last_success_at})` : ""}`,
      `Bitrix: ${b ? "connected" : "not connected"}${status.bitrix?.last_success_at ? ` (last: ${status.bitrix.last_success_at})` : ""}`,
      `Bitrix users: ${usersMeta.lastSyncStatus || "unknown"}${usersMeta.lastSyncAt ? ` (last: ${usersMeta.lastSyncAt})` : ""}`,
      `To-do: ${todoOk ? "connected" : "not connected"}${status.todo?.last_success_at ? ` (last: ${status.todo.last_success_at})` : ""}`
    ].join("\n");
  }

  if (cmd === "diag") {
    const parsed = parseDateArgOrToday(arg, todayIso);
    if (!parsed.ok) return parsed.error;
    const agenda = await getAgenda(cfg, parsed.iso);
    return formatDiagHtml({ agenda, cfg, dateIso: parsed.iso });
  }

  if (cmd === "agenda") {
    const parsed = parseDateArgOrToday(arg, todayIso);
    if (!parsed.ok) return parsed.error;
    const agenda = await getAgenda(cfg, parsed.iso);
    return formatAgendaOnly(agenda, cfg);
  }

  if (cmd === "free") {
    const parsed = parseDateArgOrToday(arg, todayIso);
    if (!parsed.ok) return parsed.error;
    const agenda = await getAgenda(cfg, parsed.iso);
    return formatFreeSlotsOnly(agenda, cfg);
  }

  if (cmd === "day") {
    const parsed = parseDateArgOrToday(arg, todayIso);
    if (!parsed.ok) return parsed.error;
    const agenda = await getAgenda(cfg, parsed.iso);
    return formatMorningSecretaryDigest(agenda, cfg, { withHintTomorrow: false });
  }

  if (cmd === "morning_secretary") {
    const agenda = await getAgenda(cfg, todayIso);
    return formatMorningSecretaryDigest(agenda, cfg, { withHintTomorrow: true });
  }

  return "__NOOP__";
}

async function main() {
  const cmd = process.argv[2] || "";
  const arg = process.argv.slice(3).join(" ");
  const text = await runAgendaCommand(cmd, arg);
  console.log(text);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  main().catch((err) => {
    console.error(err.message || err);
    process.exit(1);
  });
}
