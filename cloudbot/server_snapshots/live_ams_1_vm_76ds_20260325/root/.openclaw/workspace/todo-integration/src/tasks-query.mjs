import { getConfig } from "./config.mjs";
import { createProvider } from "./provider-factory.mjs";
import {
  formatOverdue,
  formatTasksForDate,
  formatTasksHelp
} from "./formatter.mjs";
import {
  filterOverdue,
  filterTasksForDate,
  loadMatrixHistory,
  loadTasksSnapshot,
  saveTasksSnapshot
} from "./service.mjs";
import {
  buildFocusBlock,
  buildInsightsReport,
  buildReplanSuggestion,
  formatTaskLine,
  prepareExecutiveTasks
} from "./reports/executiveDigestFormatter.mjs";
import { dateISOInTz, parseMoscowDateArg } from "./time.mjs";

async function getTasks(cfg) {
  const snap = loadTasksSnapshot(cfg.stateDir);
  if (snap?.tasks?.length) return snap.tasks;
  const provider = createProvider(cfg);
  const tasks = await provider.getAllOpenTasks();
  saveTasksSnapshot(cfg.stateDir, cfg.tz, tasks, cfg);
  return tasks;
}

function formatFocus(tasks, cfg, tz) {
  const prep = prepareExecutiveTasks(tasks, cfg);
  const { focus } = buildFocusBlock(prep);
  if (!focus.length) return "🎯 Фокус дня\n• Фокус на закрытии текущих задач";
  return ["🎯 Фокус дня", ...focus.map((t) => formatTaskLine(t, { tz }))].join("\n");
}

function formatReplan(tasks, cfg, tz) {
  const prep = prepareExecutiveTasks(tasks, cfg);
  return buildReplanSuggestion(prep, { tz, nowHour: Number(new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", hour12: false }).format(new Date())), dayEndHour: 20 }).text;
}

async function main() {
  const cmd = (process.argv[2] || "").trim().toLowerCase();
  const arg = (process.argv[3] || "").trim();
  const cfg = getConfig();
  const todayIso = dateISOInTz(new Date(), cfg.tz);

  if (cmd === "tasks_help") {
    console.log(formatTasksHelp());
    return;
  }

  const tasks = await getTasks(cfg);

  if (cmd === "overdue") {
    console.log(formatOverdue(filterOverdue(tasks, todayIso), cfg.tz));
    return;
  }

  if (cmd === "tasks") {
    if (arg === "full") {
      const list = filterTasksForDate(tasks, todayIso);
      console.log(formatTasksForDate(list, todayIso, cfg.tz, { titlePrefix: "Полный список на", limit: null }));
      return;
    }

    const parsed = parseMoscowDateArg(arg, todayIso);
    if (!parsed.ok) {
      console.log(parsed.error);
      return;
    }
    const list = filterTasksForDate(tasks, parsed.iso);
    console.log(formatTasksForDate(list, parsed.iso, cfg.tz, { titlePrefix: "Задачи на", limit: 20 }));
    return;
  }

  if (cmd === "focus") {
    const list = filterTasksForDate(tasks, todayIso);
    console.log(formatFocus(list, cfg, cfg.tz));
    return;
  }

  if (cmd === "replan") {
    const list = filterTasksForDate(tasks, todayIso);
    console.log(formatReplan(list, cfg, cfg.tz));
    return;
  }

  if (cmd === "insights") {
    const history = loadMatrixHistory(cfg.stateDir).entries || [];
    const minDate = dateISOInTz(new Date(Date.now() - 13 * 24 * 3600 * 1000), cfg.tz);
    const last14 = history.filter((x) => x.date >= minDate);
    console.log(buildInsightsReport(last14));
    return;
  }

  console.log(formatTasksHelp());
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
