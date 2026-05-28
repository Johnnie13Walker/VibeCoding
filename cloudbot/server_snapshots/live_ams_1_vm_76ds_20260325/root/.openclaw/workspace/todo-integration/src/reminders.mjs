import { getConfig } from "./config.mjs";
import { createProvider } from "./provider-factory.mjs";
import {
  getOrCreateShortLink,
  loadRemindersSettings,
  loadRemindersState,
  saveRemindersSettings,
  saveRemindersState
} from "./service.mjs";
import { sendTelegramMessage } from "./telegram.mjs";
import {
  flushSuppressedSummary,
  isDndActive,
  queueSuppressedNotification,
  shouldAllowDuringDnd
} from "./productivity.mjs";
import { adaptReminderParams, getPersonalizationSnapshot } from "./personal/personalizationEngine.mjs";

const RECENT_MAIN_WINDOW_MS = 5 * 60 * 1000;
const STALE_KEEP_DAYS = 14;

function normalizeStyle(style) {
  const s = String(style || "normal").toLowerCase();
  if (s === "soft" || s === "normal" || s === "brutal") return s;
  return "normal";
}

function stripLinks(content = "") {
  return String(content)
    .replace(/\[[^\]]+\]\((https?:\/\/[^\s)]+)\)/gi, " ")
    .replace(/https?:\/\/\S+/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function parseLink(content = "", fallback = "") {
  const md = String(content).match(/\[[^\]]+\]\((https?:\/\/[^\s)]+)\)/i);
  if (md) return md[1];
  const raw = String(content).match(/https?:\/\/\S+/i);
  if (raw) return raw[0];
  return fallback || "";
}

function normalizeTitle(task) {
  const text = stripLinks(task.content || "");
  if (text) return text;
  const url = parseLink(task.content || "", task.url || "");
  if (!url) return "Задача";
  try {
    const host = new URL(url).hostname.replace(/^www\./, "");
    if (host.includes("bitrix24")) return "CRM задача";
    if (host.includes("docs.google.com") && url.includes("spreadsheets")) return "Google Sheet";
    if (host.includes("docs.google.com")) return "Документ";
    return `Задача (${host})`;
  } catch {
    return "Задача";
  }
}

function taskDueTs(task) {
  if (!task.dueDateTime) return null;
  const ts = new Date(task.dueDateTime).getTime();
  return Number.isFinite(ts) ? ts : null;
}

function mapPriority(task) {
  const p = Number(task.priority || task.todoistPriority || 2);
  if (p >= 4) return 1;
  if (p === 3) return 2;
  if (p === 2) return 3;
  return 4;
}

function stateKey(task) {
  return `${String(task.id)}::${String(task.dueDateTime || "")}`;
}

function findEntry(state, key) {
  return state.entries.find((x) => x.key === key) || null;
}

function ensureEntry(state, task) {
  const key = stateKey(task);
  let entry = findEntry(state, key);
  if (!entry) {
    entry = {
      key,
      task_id: String(task.id),
      due_datetime: task.dueDateTime,
      pre_sent_at: null,
      main_sent_at: null,
      followup_sent_at: null,
      missed_sent_at: null,
      updated_at: new Date().toISOString()
    };
    state.entries.push(entry);
  }
  return entry;
}

function cleanupState(state, nowMs) {
  const keepSince = nowMs - STALE_KEEP_DAYS * 24 * 3600 * 1000;
  state.entries = state.entries.filter((e) => {
    const dueTs = new Date(e.due_datetime || 0).getTime();
    return dueTs && dueTs >= keepSince;
  });
}

function baseMainText(style) {
  if (style === "soft") return "⏰ Напоминаю про задачу";
  if (style === "brutal") return "🔥 Время пришло. Делай задачу.";
  return "🔥 Время задачи";
}

function buildMessage(kind, task, cfg, styleOverride = null, preMinOverride = null) {
  const title = normalizeTitle(task);
  const style = normalizeStyle(styleOverride || cfg.reminderStyle);

  if (kind === "pre") {
    return { text: `⏰ Через ${cfg.taskReminderPreMin} минут:\n• ${title}` };
  }

  if (kind === "main") {
    return { text: `${baseMainText(style)}\n• ${title}\nПора делать.` };
  }

  if (kind === "missed") {
    return { text: `⏱️ Пропущено уведомление:\n• ${title}` };
  }

  return { text: `⚠️ Задача ещё не закрыта:\n• ${title}` };
}

function toReplyMarkup(task, cfg) {
  const original = parseLink(task.content || "", task.url || "");
  if (!original) return null;
  const short = getOrCreateShortLink(cfg.stateDir, cfg.digestShortLinkBase, original, 30);
  return {
    inline_keyboard: [[{ text: "Открыть", url: short || original }]]
  };
}

async function deliverReminder(kind, task, cfg, sendFn, nowMs, adapt = null) {
  const dnd = isDndActive(cfg, new Date(nowMs));
  const dueTs = taskDueTs(task) || nowMs;
  const displayPriority = mapPriority(task);
  const meta = {
    displayPriority,
    hasFixedTime: !!task.dueDateTime,
    isOverdue: dueTs < nowMs,
    type: kind
  };

  if (dnd.active && !shouldAllowDuringDnd(meta)) {
    queueSuppressedNotification(cfg.stateDir, {
      type: kind,
      task_id: String(task.id || ""),
      title: normalizeTitle(task),
      reason: dnd.reason,
      payload: { due_datetime: task.dueDateTime || null, priority: displayPriority }
    });
    return { sent: false, suppressed: true };
  }

  const msg = buildMessage(kind, task, cfg, adapt?.style, adapt?.preMin);
  const replyMarkup = toReplyMarkup(task, cfg);
  await sendFn(msg.text, replyMarkup);
  return { sent: true, suppressed: false };
}

function shouldSendPre(nowMs, dueTs, entry, preMin) {
  if (entry.pre_sent_at) return false;
  const preTs = dueTs - Number(preMin || 10) * 60 * 1000;
  return nowMs >= preTs && nowMs < dueTs;
}

function shouldSendMain(nowMs, dueTs, entry) {
  if (entry.main_sent_at || entry.missed_sent_at) return false;
  if (nowMs < dueTs) return false;
  return nowMs - dueTs <= RECENT_MAIN_WINDOW_MS;
}

function shouldSendMissed(nowMs, dueTs, entry) {
  if (entry.main_sent_at || entry.missed_sent_at) return false;
  return nowMs > dueTs + RECENT_MAIN_WINDOW_MS;
}

function shouldSendFollowup(nowMs, dueTs, entry, followupMin) {
  if (entry.followup_sent_at) return false;
  if (!entry.main_sent_at) return false;
  const followTs = dueTs + Number(followupMin || 10) * 60 * 1000;
  return nowMs >= followTs;
}

export async function runRemindersTick(override = {}) {
  const cfg = { ...getConfig(), ...override };
  if (!cfg.telegramBotToken || !cfg.telegramOwnerId) {
    throw new Error("TELEGRAM_BOT_TOKEN or TELEGRAM_OWNER_ID is missing");
  }

  const settings = loadRemindersSettings(cfg.stateDir, { enabled: cfg.remindersEnabledDefault });
  if (!settings.enabled) {
    return { skipped: true, reason: "disabled" };
  }

  const provider = override.provider || createProvider(cfg);
  const sendFn = override.sendFn || (async (text, replyMarkup) => sendTelegramMessage(cfg.telegramBotToken, cfg.telegramOwnerId, text, { replyMarkup }));
  const openTasks = await provider.getAllOpenTasks();
  const timed = openTasks.filter((t) => !!t.dueDateTime && !t.completed);
  const nowMs = Number(override.nowMs || Date.now());

  const dnd = isDndActive(cfg, new Date(nowMs));
  if (!dnd.active) {
    const summary = flushSuppressedSummary(cfg.stateDir);
    if (summary) await sendFn(summary, null);
  }

  const state = loadRemindersState(cfg.stateDir);
  const personalSnapshot = getPersonalizationSnapshot(cfg);
  cleanupState(state, nowMs);

  const sent = { pre: 0, main: 0, followup: 0, missed: 0, suppressed: 0 };

  for (const task of timed) {
    const dueTs = taskDueTs(task);
    if (!dueTs) continue;

    const entry = ensureEntry(state, task);

    const displayPriority = mapPriority(task);
    const adapt = adaptReminderParams(personalSnapshot, {
      preMin: cfg.taskReminderPreMin,
      followupMin: cfg.taskReminderFollowupMin,
      style: cfg.reminderStyle
    }, { displayPriority });

    if (shouldSendPre(nowMs, dueTs, entry, adapt.preMin)) {
      const r = await deliverReminder("pre", task, cfg, sendFn, nowMs, adapt);
      entry.pre_sent_at = new Date(nowMs).toISOString();
      if (r.suppressed) sent.suppressed += 1;
      else sent.pre += 1;
    }

    if (shouldSendMain(nowMs, dueTs, entry)) {
      const r = await deliverReminder("main", task, cfg, sendFn, nowMs, adapt);
      entry.main_sent_at = new Date(nowMs).toISOString();
      if (r.suppressed) sent.suppressed += 1;
      else sent.main += 1;
    } else if (shouldSendMissed(nowMs, dueTs, entry)) {
      const r = await deliverReminder("missed", task, cfg, sendFn, nowMs, adapt);
      entry.missed_sent_at = new Date(nowMs).toISOString();
      if (r.suppressed) sent.suppressed += 1;
      else sent.missed += 1;
    }

    if (shouldSendFollowup(nowMs, dueTs, entry, adapt.followupMin)) {
      const r = await deliverReminder("followup", task, cfg, sendFn, nowMs, adapt);
      entry.followup_sent_at = new Date(nowMs).toISOString();
      if (r.suppressed) sent.suppressed += 1;
      else sent.followup += 1;
    }

    entry.updated_at = new Date(nowMs).toISOString();
  }

  state.lastRunAt = new Date(nowMs).toISOString();
  if (state.entries.length > 5000) state.entries = state.entries.slice(-5000);
  saveRemindersState(cfg.stateDir, state);

  return {
    skipped: false,
    checkedTimed: timed.length,
    sent
  };
}

export function setRemindersEnabled(stateDir, enabled) {
  saveRemindersSettings(stateDir, { enabled: !!enabled });
  return { enabled: !!enabled };
}

export function getRemindersStatus(stateDir, cfg = {}) {
  const settings = loadRemindersSettings(stateDir, { enabled: cfg.remindersEnabledDefault !== false });
  const state = loadRemindersState(stateDir);
  return {
    enabled: settings.enabled,
    preMin: Number(cfg.taskReminderPreMin || 10),
    followupMin: Number(cfg.taskReminderFollowupMin || 10),
    style: normalizeStyle(cfg.reminderStyle || "normal"),
    lastRunAt: state.lastRunAt || null
  };
}
