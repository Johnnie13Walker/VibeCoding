import { formatRuDateFromISO } from "../time.mjs";
import { getOrCreateShortLink, toTimePart } from "../service.mjs";

const SEP = "━━━━━━━━━━━━";

function escapeHtml(s = "") {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function cleanText(s = "") {
  return String(s).replace(/\s+/g, " ").trim();
}

function parseLink(content = "", fallback = "") {
  const md = String(content).match(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/i);
  if (md) return { title: cleanText(md[1]), url: md[2] };
  const raw = String(content).match(/https?:\/\/\S+/i);
  if (raw) return { title: "", url: raw[0] };
  return fallback ? { title: "", url: fallback } : null;
}

function urlDomain(url = "") {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function normalizeUrlTitle(url = "") {
  const host = urlDomain(url);
  if (!host) return "Ссылка";
  if (host.includes("bitrix24")) return "CRM задача";
  if (host.includes("docs.google.com") && url.includes("spreadsheets")) return "Google Sheet";
  if (host.includes("docs.google.com")) return "Документ";
  return `Ссылка: ${host}`;
}

function stripLinks(content = "") {
  return cleanText(String(content)
    .replace(/\[[^\]]+\]\((https?:\/\/[^\s)]+)\)/gi, " ")
    .replace(/https?:\/\/\S+/gi, " "));
}

function mapPriority(task) {
  const p = Number(task.priority || task.todoistPriority || 2);
  if (p >= 4) return 1;
  if (p === 3) return 2;
  if (p === 2) return 3;
  return 4;
}

function taskKey(task) {
  const link = parseLink(task.content || "", task.url || "");
  const urlKey = link?.url ? `u:${link.url}` : "";
  const text = stripLinks(task.content || "").toLowerCase();
  const date = task.dueDate || (task.dueDateTime ? task.dueDateTime.slice(0, 10) : "");
  return urlKey || `t:${text}|d:${date}`;
}

function dedupe(tasks = []) {
  const seen = new Set();
  const out = [];
  for (const t of tasks) {
    const k = taskKey(t);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(t);
  }
  return out;
}

function normalizeTask(task, cfg) {
  const link = parseLink(task.content || "", task.url || "");
  const url = link?.url || "";
  const textTitle = stripLinks(link?.title || task.content || "");
  const title = textTitle || (url ? normalizeUrlTitle(url) : "(без названия)");
  const shortUrl = url ? getOrCreateShortLink(cfg.stateDir, cfg.digestShortLinkBase, url, 30) : "";

  return {
    ...task,
    displayPriority: mapPriority(task),
    title: cleanText(title),
    link: shortUrl || url || ""
  };
}

function normalizeTasks(tasks, cfg) {
  return dedupe(tasks).map((t) => normalizeTask(t, cfg));
}

function toDate(task) {
  return task.dueDate || (task.dueDateTime ? task.dueDateTime.slice(0, 10) : "9999-12-31");
}

function sortByPriorityAndDate(tasks) {
  return [...tasks].sort((a, b) => {
    if (a.displayPriority !== b.displayPriority) return a.displayPriority - b.displayPriority;
    return toDate(a).localeCompare(toDate(b));
  });
}

function isLikelyQuickTask(task) {
  return /^(созвон|звонок|ответить|письмо|сверить|проверить|написать|позвонить)/i.test(task.title);
}

export function formatTaskLine(task, opts = {}) {
  const { idx = null, tz = "Europe/Moscow" } = opts;
  const prefix = idx == null ? "•" : `${idx}️⃣`;
  const time = toTimePart(task, tz);
  const timePart = time ? ` (${time})` : "";
  const open = task.link ? ` <a href="${escapeHtml(task.link)}">Открыть</a>` : "";
  return `${prefix} ${escapeHtml(task.title)}${timePart}${open}`;
}

export function buildPrioritySummary(tasks, opts = {}) {
  const { dateIso, overdueCount = 0 } = opts;
  const p1 = tasks.filter((t) => t.displayPriority === 1).length;
  const p2 = tasks.filter((t) => t.displayPriority === 2).length;
  const p3 = tasks.filter((t) => t.displayPriority === 3).length;
  const p4 = tasks.filter((t) => t.displayPriority === 4).length;

  return [
    `📅 ${formatRuDateFromISO(dateIso)}`,
    `📌 Всего: ${tasks.length}`,
    `🔥 Приоритет 1: ${p1}`,
    `⭐ Приоритет 2: ${p2}`,
    `⚡ Приоритет 3: ${p3}`,
    `🧩 Приоритет 4: ${p4}`,
    `⚠️ Просрочки: ${overdueCount}`
  ].join("\n");
}

export function buildFocusBlock(tasks) {
  const prepared = tasks.map((t) => ({
    ...t,
    displayPriority: t.displayPriority || mapPriority(t),
    title: t.title || stripLinks(t.content || "") || normalizeUrlTitle(parseLink(t.content || "", t.url || "")?.url || ""),
    link: t.link || parseLink(t.content || "", t.url || "")?.url || ""
  }));
  const sorted = sortByPriorityAndDate(prepared);
  const p1 = sorted.filter((t) => t.displayPriority === 1);
  const p2 = sorted.filter((t) => t.displayPriority === 2);

  let focus = [];
  if (p1.length) focus = p1.slice(0, 2);
  else focus = p2.slice(0, 2);
  if (sorted.length <= 2) focus = sorted.slice(0, 1);

  return { focus: dedupe(focus) };
}

export function buildRecommendedOrder(tasks, opts = {}) {
  const maxItems = Number(opts.maxItems || 7);
  const focusKeys = new Set((opts.focus || []).map(taskKey));
  const sorted = sortByPriorityAndDate(tasks);

  const p1 = sorted.filter((t) => t.displayPriority === 1 && !focusKeys.has(taskKey(t)));
  const p2 = sorted.filter((t) => t.displayPriority === 2 && !focusKeys.has(taskKey(t)));
  const p3Quick = sorted.filter((t) => t.displayPriority === 3 && isLikelyQuickTask(t) && !focusKeys.has(taskKey(t)));
  const p3 = sorted.filter((t) => t.displayPriority === 3 && !isLikelyQuickTask(t) && !focusKeys.has(taskKey(t)));
  const p4 = sorted.filter((t) => t.displayPriority === 4 && !focusKeys.has(taskKey(t)));

  let order = [...p1, ...p2, ...p3Quick, ...p3];
  if (order.length < maxItems) {
    order = [...order, ...p4.slice(0, maxItems - order.length)];
  }

  return dedupe(order).slice(0, maxItems);
}

export function suggestDailyScope(tasks, opts = {}) {
  const nowHour = Number(opts.nowHour ?? 9);
  const dayEndHour = Number(opts.dayEndHour ?? 20);
  const hoursLeft = Math.max(0, dayEndHour - nowHour);
  const estimatedCapacity = Math.max(1, Math.round(hoursLeft * 0.75));

  const prepared = tasks.map((t) => ({
    ...t,
    displayPriority: t.displayPriority || mapPriority(t),
    title: t.title || stripLinks(t.content || "") || normalizeUrlTitle(parseLink(t.content || "", t.url || "")?.url || ""),
    link: t.link || parseLink(t.content || "", t.url || "")?.url || ""
  }));
  const sorted = sortByPriorityAndDate(prepared);
  const must = sorted.filter((t) => t.displayPriority <= 2);
  const normal = sorted.filter((t) => t.displayPriority === 3);
  const low = sorted.filter((t) => t.displayPriority === 4);

  const doable = [];
  doable.push(...must.slice(0, estimatedCapacity));
  if (doable.length < estimatedCapacity) doable.push(...normal.slice(0, estimatedCapacity - doable.length));
  if (doable.length < estimatedCapacity) doable.push(...low.slice(0, estimatedCapacity - doable.length));

  const doableKeys = new Set(doable.map(taskKey));
  const postpone = sorted.filter((t) => !doableKeys.has(taskKey(t)) && t.displayPriority >= 3);
  const drop = postpone.filter((t) => t.displayPriority === 4);

  return {
    remaining: sorted.length,
    estimatedCapacity,
    doable: dedupe(doable),
    postpone: dedupe(postpone),
    drop: dedupe(drop)
  };
}

export function buildReplanSuggestion(tasks, opts = {}) {
  const scope = suggestDailyScope(tasks, opts);
  const lines = [
    "⚠️ Обновление плана",
    `Осталось ${scope.remaining} задач.`,
    `Реально успеть ≈ ${scope.estimatedCapacity}.`,
    "",
    "Реально сегодня:",
    `✔ сделать ${scope.doable.length}`,
    `⏳ перенести ${scope.postpone.length}`,
    `❌ убрать ${scope.drop.length} (низкий приоритет)`,
    "",
    "🎯 Сфокусируйся:"
  ];

  const top = scope.doable.slice(0, 3);
  if (!top.length) lines.push("• Закрой хотя бы одну приоритетную задачу");
  else lines.push(...top.map((t) => formatTaskLine(t, { idx: null, tz: opts.tz || "Europe/Moscow" })));

  return { text: lines.join("\n"), scope };
}

function buildPriorityBlock(tasks) {
  const p1 = tasks.filter((t) => t.displayPriority === 1).length;
  const p2 = tasks.filter((t) => t.displayPriority === 2).length;
  const p3 = tasks.filter((t) => t.displayPriority === 3).length;
  const p4 = tasks.filter((t) => t.displayPriority === 4).length;
  return [
    "📊 Приоритеты",
    `🔥 Приоритет 1 — ${p1}`,
    `⭐ Приоритет 2 — ${p2}`,
    `⚡ Приоритет 3 — ${p3}`,
    `🧩 Приоритет 4 — ${p4}`
  ].join("\n");
}

function applyPruning(list, maxVisible) {
  const shown = list.slice(0, maxVisible);
  const hidden = Math.max(0, list.length - shown.length);
  return { shown, hidden };
}

export function formatExecutiveMorning(data, options = {}) {
  const cfg = options.cfg;
  const tz = options.tz || "Europe/Moscow";
  const tasks = normalizeTasks(data.tasks || [], cfg);
  const overdueCount = Number(data.overdueCount || 0);

  const summary = buildPrioritySummary(tasks, { dateIso: data.dateIso, overdueCount });
  const { focus } = buildFocusBlock(tasks);
  const order = buildRecommendedOrder(tasks, { focus, maxItems: 7 });

  const pruned = applyPruning(order, cfg.digestMaxVisibleTasks || 7);

  const lines = [summary, "", SEP, "🎯 Фокус дня"];
  if (!focus.length) lines.push("• Фокус на закрытии текущих задач");
  else lines.push(...focus.map((t) => formatTaskLine(t, { tz })));

  lines.push("", SEP, "🧠 Рекомендованный порядок");
  lines.push(...pruned.shown.map((t, i) => formatTaskLine(t, { idx: i + 1, tz })));

  if (pruned.hidden > 0) {
    lines.push(`ещё ${pruned.hidden} задач скрыто (команда /tasks full)`);
  }

  if (cfg.digestShowPriorityBlock) {
    lines.push("", SEP, buildPriorityBlock(tasks));
  }

  return {
    text: lines.join("\n"),
    meta: {
      focusCount: focus.length,
      orderCount: pruned.shown.length,
      hiddenCount: pruned.hidden,
      containsQ: /\bQ[1-4]\b/.test(lines.join("\n"))
    }
  };
}

export function formatExecutiveEvening(data, options = {}) {
  const cfg = options.cfg;
  const tz = options.tz || "Europe/Moscow";
  const overdue = normalizeTasks(data.overdue || [], cfg);
  const dueToday = normalizeTasks(data.dueToday || [], cfg);

  const merged = dedupe([...overdue, ...dueToday]);
  const critical = merged.filter((t) => t.displayPriority <= 2);
  const rest = merged.filter((t) => t.displayPriority >= 3);

  const lines = [
    "🌙 Вечерний чек",
    "",
    `⚠️ Просрочено: ${overdue.length}`,
    `⏳ Осталось на сегодня: ${dueToday.length}`,
    "",
    SEP,
    "🔥 Критичное (Приоритет 1/2)"
  ];

  if (!critical.length) lines.push("Критичных задач не осталось 👍");
  else lines.push(...critical.slice(0, cfg.digestMaxVisibleTasks || 7).map((t) => formatTaskLine(t, { tz })));

  lines.push("", SEP, "🧩 Остальное");
  if (!rest.length) lines.push("• Пусто");
  else lines.push(...rest.slice(0, cfg.digestMaxVisibleTasks || 7).map((t) => formatTaskLine(t, { tz })));

  const left = merged.length;
  if (left >= 6) lines.push("", "Сегодня перегруз. Закрой 1 ключевую и 2 быстрые задачи.");
  else if (left <= 2) lines.push("", "Отличный темп. Почти всё закрыто 👏");
  else lines.push("", "Хороший прогресс. Дожми самое важное.");

  return { text: lines.join("\n") };
}

export function buildInsightsReport(historyRows = []) {
  const rows = historyRows.slice(-28);
  if (!rows.length) return "📈 Инсайты\n• Недостаточно данных за период.";

  const byDate = new Map();
  for (const r of rows) {
    if (!byDate.has(r.date)) byDate.set(r.date, {});
    byDate.get(r.date)[r.slot] = r;
  }

  let p2Carry = 0;
  let overload = 0;
  let highOps = 0;
  let days = 0;

  for (const [, d] of byDate) {
    if (!d.morning) continue;
    days += 1;
    const m = d.morning;
    const e = d.evening || {};
    const mP2 = Number(m.P2 || m.Q2 || 0);
    const eP2 = Number(e.P2 || e.Q2 || 0);
    const mTotal = Number(m.total || (Number(m.P1 || 0) + Number(m.P2 || 0) + Number(m.P3 || 0) + Number(m.P4 || 0)) || 0);
    const eTotal = Number(e.total || (Number(e.P1 || 0) + Number(e.P2 || 0) + Number(e.P3 || 0) + Number(e.P4 || 0)) || 0);

    if (mP2 > 0 && eP2 >= mP2) p2Carry += 1;
    if (mTotal >= 9) overload += 1;
    if (mTotal > 0 && Number(m.P3 || 0) + Number(m.P4 || 0) >= Math.ceil(mTotal * 0.6)) highOps += 1;
    if (eTotal >= Math.ceil(mTotal * 0.7)) p2Carry += 0;
  }

  const lines = ["📈 Инсайты (14 дней)"];
  if (!days) return "📈 Инсайты\n• Недостаточно данных за период.";

  if (p2Carry / days >= 0.4) lines.push("• Ты часто переносишь задачи приоритета 2.");
  if (overload / days >= 0.3) lines.push("• В днях часто перегруз по количеству задач.");
  if (highOps / days >= 0.4) lines.push("• Высокая доля операционки (приоритет 3/4). ");
  if (lines.length === 1) lines.push("• Динамика стабильная, серьёзных слепых зон не найдено.");

  return lines.join("\n");
}

export function prepareExecutiveTasks(tasks, cfg) {
  return normalizeTasks(tasks, cfg);
}
