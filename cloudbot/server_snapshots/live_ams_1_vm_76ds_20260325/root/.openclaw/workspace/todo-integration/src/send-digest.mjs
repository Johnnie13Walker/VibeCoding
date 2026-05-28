import { getConfig } from "./config.mjs";
import { createProvider } from "./provider-factory.mjs";
import {
  buildReplanSuggestion,
  formatExecutiveEvening,
  formatExecutiveMorning,
  suggestDailyScope
} from "./reports/executiveDigestFormatter.mjs";
import {
  alreadySent,
  filterDueToday,
  filterOverdue,
  filterTasksForDate,
  loadDigestState,
  markMatrixSnapshot,
  markSent,
  saveTasksSnapshot
} from "./service.mjs";
import { classifyTasks, splitByQuadrant, suggestExecutionOrder } from "./eisenhower.mjs";
import { dateISOInTz } from "./time.mjs";
import { sendTelegramMessage } from "./telegram.mjs";
import { getAgenda } from "./agenda/aggregate.mjs";
import { formatMorningSecretaryDigest } from "./reports/morningSecretaryDigest.mjs";
import { renderDailyCalendarDigest } from "./reports/calendarDailyRenderer.mjs";
import { buildDayScenarioMessage } from "./execution/timelineBuilder.mjs";
import { getExecutionStatus } from "./execution/executionEngine.mjs";
import { getPersonalizationSnapshot } from "./personal/personalizationEngine.mjs";
import {
  buildFocusProposal,
  createRescheduleSuggestion,
  formatFocusBlocksMessage,
  formatRescheduleSuggestions,
  pickCriticalForReschedule,
  saveFocusProposalForDate
} from "./productivity.mjs";

function moscowHourNow() {
  const hh = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Moscow", hour: "2-digit", hour12: false }).format(new Date());
  return Number(hh);
}

function toPriorityCounts(split) {
  return {
    P1: split.Q1.length,
    P2: split.Q2.length,
    P3: split.Q3.length,
    P4: split.Q4.length
  };
}

function escapeHtml(s = "") {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;");
}

function toMyUserCode(cfg) {
  const raw = String(cfg?.bitrixUserId || "").trim();
  if (!raw) return "";
  const m = raw.match(/^[Uu](\d+)$/);
  if (m) return `U${m[1]}`;
  if (/^\d+$/.test(raw)) return `U${raw}`;
  return raw.toUpperCase();
}

function formatBitrixOnlyMorning({ dateIso, tz, meetings, todoWarning, myUserCode }) {
  const digest = renderDailyCalendarDigest({
    agenda: {
      date: dateIso,
      meetings: meetings || [],
      freeSlots: [],
      tasks: [],
      overdueCount: 0
    },
    cfg: { tz },
    myUserCode
  });
  return `${todoWarning}\n\n${digest}`;
}

function buildTodoWarning(err) {
  const reason = String(err?.message || err || "неизвестная ошибка")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 220);
  return `⚠️ ToDo (Todoist) временно недоступен: ${escapeHtml(reason)}. Отправляю отчет только по встречам Bitrix.`;
}

async function main() {
  const slot = process.argv[2];
  if (!["morning", "evening", "midday"].includes(slot)) {
    throw new Error("Usage: node src/send-digest.mjs <morning|evening|midday>");
  }

  const cfg = getConfig();
  if (!cfg.digestEnabled) {
    console.log("digest_disabled");
    return;
  }

  if (slot === "midday" && !cfg.middayReplanEnabled) {
    console.log("midday_replan_disabled");
    return;
  }

  if (!cfg.telegramBotToken || !cfg.telegramOwnerId) {
    throw new Error("TELEGRAM_BOT_TOKEN or TELEGRAM_OWNER_ID is missing");
  }

  const dateIso = dateISOInTz(new Date(), cfg.tz);
  const state = loadDigestState(cfg.stateDir);
  if (alreadySent(state, dateIso, slot)) {
    console.log(`skip_duplicate slot=${slot} date=${dateIso}`);
    return;
  }

  let tasks = [];
  let todoWarning = "";
  let todoUnavailable = false;

  try {
    const provider = createProvider(cfg);
    tasks = await provider.getAllOpenTasks();
    saveTasksSnapshot(cfg.stateDir, cfg.tz, tasks, cfg);
  } catch (err) {
    if (slot !== "morning") throw err;
    todoUnavailable = true;
    todoWarning = buildTodoWarning(err);
    console.error(`[digest] todo_unavailable slot=${slot} reason=${err?.message || err}`);
  }

  let text = "";
  let extraMessages = [];

  if (slot === "morning") {
    let morningAgenda = null;
    let todayTasks = [];
    let overdue = [];
    let split = { Q1: [], Q2: [], Q3: [], Q4: [] };
    let order = [];

    if (todoUnavailable) {
      morningAgenda = await getAgenda(cfg, dateIso, {
        skipTodoFetch: true,
        todoWarning
      });
    } else {
      todayTasks = filterTasksForDate(tasks, dateIso);
      overdue = filterOverdue(tasks, dateIso);
      const withMatrix = classifyTasks(todayTasks, { todayIso: dateIso, tz: cfg.tz, cfg });
      split = splitByQuadrant(withMatrix);
      order = suggestExecutionOrder(withMatrix);
    }

    if (cfg.morningSecretaryEnabled) {
      if (!morningAgenda) {
        morningAgenda = await getAgenda(cfg, dateIso, { prefetchedTasks: tasks });
      }
      const personalSnapshot = getPersonalizationSnapshot(cfg);
      text = formatMorningSecretaryDigest(morningAgenda, cfg, {
        withHintTomorrow: false,
        personalSnapshot
      });
      if (todoUnavailable) {
        text = `${todoWarning}\n\n${text}`;
      }
    } else if (todoUnavailable) {
      text = formatBitrixOnlyMorning({
        dateIso,
        tz: cfg.tz,
        meetings: morningAgenda?.meetings || [],
        todoWarning,
        myUserCode: toMyUserCode(cfg)
      });
    } else {
      text = formatExecutiveMorning({
        dateIso,
        tasks: todayTasks,
        order,
        overdueCount: overdue.length
      }, { cfg, tz: cfg.tz }).text;
    }

    if (!todoUnavailable) {
      const focusProposal = buildFocusProposal(todayTasks, cfg, dateIso);
      saveFocusProposalForDate(cfg.stateDir, focusProposal);
      if (focusProposal?.blocks?.length) {
        extraMessages.push(formatFocusBlocksMessage(focusProposal.blocks));
      }

      markMatrixSnapshot(cfg.stateDir, {
        date: dateIso,
        slot,
        ...toPriorityCounts(split),
        total: todayTasks.length
      });
    }

    const assistantStatus = getExecutionStatus(cfg, new Date());
    if (cfg.dayScenarioMessageEnabled && cfg.executionModeEnabled && assistantStatus.enabled) {
      if (!morningAgenda) {
        morningAgenda = await getAgenda(cfg, dateIso, {
          prefetchedTasks: todoUnavailable ? [] : tasks,
          skipTodoFetch: todoUnavailable,
          todoWarning
        });
      }
      extraMessages.push(buildDayScenarioMessage(morningAgenda, cfg));
    }
  }

  if (slot === "evening") {
    const overdue = filterOverdue(tasks, dateIso);
    const dueToday = filterDueToday(tasks, dateIso);

    text = formatExecutiveEvening({
      dateIso,
      overdue,
      dueToday
    }, { cfg, tz: cfg.tz }).text + "\n\nКоманда: /day tomorrow";

    const critical = pickCriticalForReschedule([...overdue, ...dueToday]);
    const suggestions = critical.slice(0, 5).map((t) => createRescheduleSuggestion(t, new Date()));
    if (suggestions.length) {
      extraMessages.push(formatRescheduleSuggestions(suggestions));
    }

    const withMatrix = classifyTasks([...overdue, ...dueToday], { todayIso: dateIso, tz: cfg.tz, cfg });
    const split = splitByQuadrant(withMatrix);
    markMatrixSnapshot(cfg.stateDir, {
      date: dateIso,
      slot,
      ...toPriorityCounts(split),
      total: overdue.length + dueToday.length
    });
  }

  if (slot === "midday") {
    const overdue = filterOverdue(tasks, dateIso);
    const dueToday = filterDueToday(tasks, dateIso);
    const todayOpen = [...overdue, ...dueToday];
    const normalizedHour = moscowHourNow();
    const scope = suggestDailyScope(todayOpen, { nowHour: normalizedHour, dayEndHour: 20 });

    if (scope.remaining <= scope.estimatedCapacity) {
      console.log(`midday_skip_balanced remaining=${scope.remaining} cap=${scope.estimatedCapacity}`);
      return;
    }

    text = buildReplanSuggestion(todayOpen, { nowHour: normalizedHour, dayEndHour: 20, tz: cfg.tz }).text;
  }

  const r = await sendTelegramMessage(cfg.telegramBotToken, cfg.telegramOwnerId, text);
  for (const msg of extraMessages) {
    await sendTelegramMessage(cfg.telegramBotToken, cfg.telegramOwnerId, msg);
  }
  markSent(cfg.stateDir, dateIso, slot);
  console.log(`sent slot=${slot} date=${dateIso} message_id=${r?.result?.message_id ?? "n/a"} extras=${extraMessages.length}`);
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
