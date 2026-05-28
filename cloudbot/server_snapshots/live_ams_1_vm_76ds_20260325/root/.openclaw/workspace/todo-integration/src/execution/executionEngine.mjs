import fs from "node:fs";
import path from "node:path";
import { getConfig } from "../config.mjs";
import { getAgenda } from "../agenda/aggregate.mjs";
import { dateISOInTz } from "../time.mjs";
import { sendTelegramMessage } from "../telegram.mjs";
import { resolveExecutionContext } from "./contextResolver.mjs";
import { getNextBestAction } from "./nextActionSelector.mjs";
import { adaptNextActionByRhythm, getExecutionCooldownMultiplier, getPersonalizationSnapshot } from "../personal/personalizationEngine.mjs";
import { recordAssistantEvent } from "../personal/telemetryCollector.mjs";

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function readJson(file, fallback) {
  try {
    if (!fs.existsSync(file)) return fallback;
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return fallback;
  }
}

function writeJson(file, data) {
  ensureDir(path.dirname(file));
  fs.writeFileSync(file, JSON.stringify(data, null, 2));
}

function fp(stateDir, name) {
  ensureDir(stateDir);
  return path.join(stateDir, name);
}

function loadExecutionState(stateDir) {
  return readJson(fp(stateDir, "execution_state.json"), {
    lastRunAt: null,
    lastAdviceAt: null,
    lastAdviceKey: null,
    lastPreByMeeting: {},
    lastPostByMeeting: {}
  });
}

function saveExecutionState(stateDir, state) {
  writeJson(fp(stateDir, "execution_state.json"), state);
}

function loadExecutionSettings(stateDir, defaults = {}) {
  const s = readJson(fp(stateDir, "execution_settings.json"), null);
  if (!s) {
    return { enabled: defaults.enabled !== false };
  }
  return { enabled: s.enabled !== false };
}

function saveExecutionSettings(stateDir, settings) {
  writeJson(fp(stateDir, "execution_settings.json"), {
    enabled: settings.enabled !== false,
    updatedAt: new Date().toISOString()
  });
}

function keyForMeeting(m) {
  return `${String(m?.id || "noid")}:${String(m?.start || "")}`;
}

function toHHMM(dt, tz) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(dt));
}

function formatMeetingPeople(meeting) {
  const list = (meeting?.attendees || []).map((x) => String(x || "").trim()).filter(Boolean);
  if (!list.length) return null;
  const shown = list.slice(0, 5);
  const extra = list.length - shown.length;
  return extra > 0 ? `${shown.join(", ")} + ещё ${extra}` : shown.join(", ");
}

function findTaskForWindow(tasks, maxMinutes, maxPriority = 3) {
  return (tasks || []).find((t) => Number(t.displayPriority || 4) <= maxPriority && Number(t.etaMin || 999) <= maxMinutes) || null;
}

function buildPreMeetingMessage(ctx) {
  const m = ctx.nextMeeting;
  if (!m) return "";
  const lines = [
    `⏰ Через ${ctx.minutesToNextMeeting} минут:`,
    `${m.title || "Встреча"}`
  ];

  const ppl = formatMeetingPeople(m);
  if (ppl) {
    lines.push("", "👥 Участники:", `• ${ppl}`);
  }

  if (ctx.afterMeetingGapMin != null) {
    lines.push("", `🕒 После встречи свободно: ${ctx.afterMeetingGapMin} минут.`);
    const task = findTaskForWindow(ctx.tasks, Math.max(20, Math.min(45, ctx.afterMeetingGapMin)), 3);
    if (task) {
      lines.push("", "🎯 После встречи рекомендую:", `• ${task.title || task.content || "Задача"}`);
    }
  }

  return lines.join("\n");
}

function formatMeetingSummary(meeting, tz = "Europe/Moscow") {
  if (!meeting) return "встреча";
  const title = String(meeting.title || "встреча").trim();
  if (!meeting.start || !meeting.end) return title;
  return title + " (" + toHHMM(meeting.start, tz) + "–" + toHHMM(meeting.end, tz) + ")";
}

function buildPostMeetingMessage(ctx) {
  const tz = "Europe/Moscow";
  const ended = formatMeetingSummary(ctx.lastEndedMeeting, tz);
  const lines = ["✅ Завершилась: " + ended + "."];

  const free = Number(ctx.freeUntilNextMeeting || 0);
  const next = ctx.nextMeeting || null;
  const minsToNext = Number(ctx.minutesToNextMeeting);

  if (next && Number.isFinite(minsToNext) && minsToNext >= 0) {
    const nextTitle = String(next.title || "встреча").trim();
    const nextAt = next.start ? toHHMM(next.start, tz) : "";
    lines.push(
      "",
      "➡️ Следующая: " + nextTitle + (nextAt ? (" в " + nextAt) : "") + ".",
      "⏱ До начала: " + minsToNext + " минут."
    );
  } else if (free > 0) {
    lines.push("", "➡️ Следующих встреч на сегодня нет.", "⏱ Свободно: " + free + " минут.");
  }

  const task = findTaskForWindow(ctx.tasks, free >= 40 ? 50 : 30, 3) || ctx.tasks.find((t) => Number(t.displayPriority || 4) <= 3);
  if (task) {
    lines.push("", "Быстрый win:", "• " + (task.title || task.content || "Задача"));
  }
  return lines.join("\n");
}

function shouldSendByCooldown(lastIso, nowMs, cooldownMin) {
  if (!lastIso) return true;
  const lastMs = new Date(lastIso).getTime();
  if (!Number.isFinite(lastMs)) return true;
  return nowMs - lastMs >= cooldownMin * 60 * 1000;
}

function nextCheckHHMM(nowMs, checkMin, tz) {
  const d = new Date(nowMs);
  const min = d.getUTCMinutes();
  const add = checkMin - (min % checkMin || checkMin);
  const next = new Date(nowMs + add * 60 * 1000);
  return toHHMM(next, tz);
}

export function setExecutionEnabled(stateDir, enabled) {
  saveExecutionSettings(stateDir, { enabled: !!enabled });
  return { enabled: !!enabled };
}

export function getExecutionStatus(cfg, now = new Date()) {
  const settings = loadExecutionSettings(cfg.stateDir, { enabled: cfg.executionModeEnabled });
  const state = loadExecutionState(cfg.stateDir);
  const nowMs = new Date(now).getTime();
  return {
    enabled: settings.enabled,
    lastAdviceAt: state.lastAdviceAt || null,
    nextCheckAt: nextCheckHHMM(nowMs, cfg.executionCheckMinutes, cfg.tz)
  };
}

export async function runExecutionTick(override = {}) {
  const cfg = { ...getConfig(), ...override };
  const settings = loadExecutionSettings(cfg.stateDir, { enabled: cfg.executionModeEnabled });
  if (!settings.enabled) {
    return { skipped: true, reason: "disabled" };
  }

  const nowMs = Number(override.nowMs || Date.now());
  const now = new Date(nowMs);
  const todayIso = dateISOInTz(now, cfg.tz);

  const sendFn = override.sendFn || (async (text) => {
    if (!cfg.telegramBotToken || !cfg.telegramOwnerId) return;
    await sendTelegramMessage(cfg.telegramBotToken, cfg.telegramOwnerId, text);
  });

  const agenda = override.agenda || await getAgenda(cfg, todayIso);
  const ctx = resolveExecutionContext(now, agenda, cfg);
  const state = loadExecutionState(cfg.stateDir);
  const personalSnapshot = getPersonalizationSnapshot(cfg);

  let sentType = null;
  let sentText = null;

  const checkWindowMin = Math.max(5, Number(cfg.executionCheckMinutes || 15));

  if (!ctx.inMeeting && ctx.nextMeeting && ctx.minutesToNextMeeting != null && ctx.minutesToNextMeeting <= Number(cfg.executionPreMeetingMin || 10) && ctx.minutesToNextMeeting >= 0) {
    const key = keyForMeeting(ctx.nextMeeting);
    if (!state.lastPreByMeeting[key]) {
      sentType = "pre_meeting";
      sentText = buildPreMeetingMessage(ctx);
      state.lastPreByMeeting[key] = new Date(nowMs).toISOString();
    }
  }

  if (!sentType && !ctx.inMeeting && ctx.lastEndedMeeting && ctx.minutesSinceLastMeetingEnded != null) {
    const postMin = Number(cfg.executionPostMeetingMin || 5);
    const key = keyForMeeting(ctx.lastEndedMeeting);
    if (!state.lastPostByMeeting[key] && ctx.minutesSinceLastMeetingEnded >= postMin && ctx.minutesSinceLastMeetingEnded <= postMin + checkWindowMin) {
      sentType = "post_meeting";
      sentText = buildPostMeetingMessage(ctx);
      state.lastPostByMeeting[key] = new Date(nowMs).toISOString();
    }
  }

  if (!sentType) {
    const hour = Number(String(ctx.nowHHMM || "00:00").slice(0, 2));
    const mult = getExecutionCooldownMultiplier(personalSnapshot, hour);
    const canSendAdvice = shouldSendByCooldown(state.lastAdviceAt, nowMs, Math.round(Number(cfg.executionCooldownMinutes || 60) * mult));
    if (canSendAdvice) {
      let action = getNextBestAction(now, ctx, cfg);
      action = adaptNextActionByRhythm(action, ctx, personalSnapshot);
      if (action.kind === "next_action" && action.text) {
        if (action.key !== state.lastAdviceKey) {
          sentType = "next_action";
          sentText = action.text;
          state.lastAdviceAt = new Date(nowMs).toISOString();
          state.lastAdviceKey = action.key;
        }
      }
    }
  }

  if (sentType && sentText) {
    await sendFn(sentText);
    try {
      recordAssistantEvent(cfg, "suggestion_sent", sentType, { text: sentText.slice(0, 300) });
    } catch {}
  }

  state.lastRunAt = new Date(nowMs).toISOString();
  saveExecutionState(cfg.stateDir, state);

  return {
    skipped: false,
    sentType,
    sent: !!sentType,
    nowHHMM: toHHMM(now, cfg.tz),
    inMeeting: ctx.inMeeting,
    freeUntilNextMeeting: ctx.freeUntilNextMeeting,
    minutesToNextMeeting: ctx.minutesToNextMeeting
  };
}
