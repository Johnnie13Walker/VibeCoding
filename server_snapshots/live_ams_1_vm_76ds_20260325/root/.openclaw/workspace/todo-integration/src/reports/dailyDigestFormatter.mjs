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

function titleFromUrl(url = "") {
  try {
    const u = new URL(url);
    return (u.hostname || "ссылка").replace(/^www\./, "");
  } catch {
    return "ссылка";
  }
}

function extractLink(content = "", fallbackUrl = "") {
  const md = String(content).match(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/i);
  if (md) return { title: cleanText(md[1]), url: md[2] };

  const raw = String(content).match(/https?:\/\/\S+/i);
  if (raw) return { title: "", url: raw[0] };

  return fallbackUrl ? { title: "", url: fallbackUrl } : null;
}

function stripServiceWords(content) {
  return cleanText(String(content)
    .replace(/\[[^\]]+\]\((https?:\/\/[^\s)]+)\)/gi, " ")
    .replace(/https?:\/\/\S+/gi, " "));
}

function taskKey(task) {
  const id = task.id ? `id:${task.id}` : "";
  const extracted = extractLink(task.content || "", task.url || "");
  const url = extracted?.url ? `url:${extracted.url}` : "";
  const text = stripServiceWords(task.content || "").toLowerCase();
  const byTextDate = `txt:${text}|d:${task.dueDate || ""}|dt:${task.dueDateTime || ""}`;
  return url || id || byTextDate;
}

function dedupeTasks(tasks = []) {
  const seen = new Set();
  const out = [];
  for (const task of tasks) {
    const key = taskKey(task);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(task);
  }
  return out;
}

function normalizeTask(task, cfg) {
  const linkObj = extractLink(task.content || "", task.url || "");
  const url = linkObj?.url || "";
  const rawTitle = stripServiceWords(linkObj?.title || task.content || "") || (url ? `Ссылка: ${titleFromUrl(url)}` : "(без названия)");
  const shortUrl = url ? getOrCreateShortLink(cfg.stateDir, cfg.digestShortLinkBase, url, 30) : "";

  return {
    ...task,
    title: cleanText(rawTitle),
    url,
    shortUrl,
    domain: titleFromUrl(url)
  };
}

function withNorm(tasks, cfg) {
  return dedupeTasks(tasks).map((t) => normalizeTask(t, cfg));
}

export function formatTaskLine(task, opts = {}) {
  const { idx = null, tz = "Europe/Moscow" } = opts;
  const prefix = idx == null ? "•" : `${idx}️⃣`;
  const time = toTimePart(task, tz);
  const timePart = time ? ` (${time})` : "";
  const link = task.shortUrl ? ` <a href="${escapeHtml(task.shortUrl)}">Открыть</a>` : (task.url ? ` <a href="${escapeHtml(task.url)}">Открыть</a>` : "");
  return `${prefix} ${escapeHtml(task.title)}${timePart}${link}`;
}

function compactItems(items, cfg, tz, max = null) {
  const lim = max ?? cfg.digestMaxTasksPerSection;
  return items.slice(0, lim).map((t, i) => formatTaskLine(t, { idx: i + 1, tz }));
}

function pickFocus(matrix) {
  const byPriority = [...matrix.Q1, ...matrix.Q2, ...matrix.Q3, ...matrix.Q4];
  return byPriority.slice(0, 2);
}

function buildOrder(order, focus, cfg) {
  const focusKeys = new Set(focus.map(taskKey));
  const clean = dedupeTasks(order).filter((t) => !focusKeys.has(taskKey(t)));
  const minLen = 3;
  if (clean.length >= minLen) return clean.slice(0, 7);
  const fallback = dedupeTasks([...focus, ...order]);
  return fallback.slice(0, 7);
}

export function formatMatrixCompact(matrix, opts = {}) {
  const { cfg, tz = "Europe/Moscow" } = opts;
  const lim = cfg.digestMaxTasksPerSection;
  const lines = ["📊 Матрица"];

  for (const [icon, key, title] of [["🔥", "Q1", "Q1"], ["⭐", "Q2", "Q2"], ["⚡", "Q3", "Q3"], ["🧩", "Q4", "Q4"]]) {
    const items = matrix[key] || [];
    if (!items.length) {
      lines.push(`${icon} ${title} — нет`);
      continue;
    }
    lines.push(`${icon} ${title} — ${items.length}`);
    lines.push(...compactItems(items, cfg, tz, lim));
    if (items.length > lim) lines.push(`…ещё ${items.length - lim}`);
  }

  return lines.join("\n");
}

function buildSummary(dateIso, matrix, overdueCount, allCount) {
  return [
    `📅 ${formatRuDateFromISO(dateIso)}`,
    `📌 Всего: ${allCount}  🔥Q1:${matrix.Q1.length} ⭐Q2:${matrix.Q2.length} ⚡Q3:${matrix.Q3.length} 🧩Q4:${matrix.Q4.length}  ⚠️Просрочки:${overdueCount}`
  ].join("\n");
}

export function formatMorningDigest(data, options = {}) {
  const cfg = options.cfg || {};
  const tz = options.tz || "Europe/Moscow";
  const matrix = {
    Q1: withNorm(data.matrix?.Q1 || [], cfg),
    Q2: withNorm(data.matrix?.Q2 || [], cfg),
    Q3: withNorm(data.matrix?.Q3 || [], cfg),
    Q4: withNorm(data.matrix?.Q4 || [], cfg)
  };

  const allTasks = dedupeTasks([...matrix.Q1, ...matrix.Q2, ...matrix.Q3, ...matrix.Q4]).slice(0, cfg.digestMaxTotalTasks);
  const focus = pickFocus(matrix);
  const order = buildOrder(withNorm(data.order || [], cfg), focus, cfg);

  const lines = [
    buildSummary(data.dateIso, matrix, Number(data.overdueCount || 0), allTasks.length),
    "",
    SEP,
    "🎯 Фокус дня"
  ];

  if (!focus.length) lines.push("• Критичных задач нет");
  else lines.push(...focus.map((t, i) => formatTaskLine(t, { idx: i + 1, tz })));

  lines.push("", SEP, "🧠 Порядок");
  lines.push(...order.slice(0, 7).map((t, i) => formatTaskLine(t, { idx: i + 1, tz })));

  if (cfg.digestShowMatrix) {
    lines.push("", SEP, formatMatrixCompact(matrix, { cfg, tz }));
  }

  return {
    text: lines.join("\n"),
    meta: {
      focusKeys: focus.map(taskKey),
      orderKeys: order.map(taskKey),
      counts: { total: allTasks.length, Q1: matrix.Q1.length, Q2: matrix.Q2.length, Q3: matrix.Q3.length, Q4: matrix.Q4.length },
      focusCount: focus.length,
      orderCount: order.length
    }
  };
}

export function formatEveningDigest(data, options = {}) {
  const cfg = options.cfg || {};
  const tz = options.tz || "Europe/Moscow";
  const overdue = withNorm(data.overdue || [], cfg);
  const dueToday = withNorm(data.dueToday || [], cfg);
  const critical = withNorm(data.criticalOpen || [], cfg);

  const lines = [
    `🌙 Вечерний чек (${formatRuDateFromISO(data.dateIso)})`,
    `⏳ Осталось: ${dueToday.length}`,
    `⚠️ Просрочено: ${overdue.length}`,
    "",
    SEP,
    "🔥 Критичное"
  ];

  if (!critical.length) lines.push("• Нет");
  else lines.push(...critical.slice(0, cfg.digestMaxTasksPerSection).map((t) => formatTaskLine(t, { tz })));

  if (critical.length > cfg.digestMaxTasksPerSection) lines.push(`…ещё ${critical.length - cfg.digestMaxTasksPerSection}`);

  lines.push("", SEP, "🧩 Остальное на сегодня");
  if (!dueToday.length && !overdue.length) {
    lines.push("• Всё закрыто ✅");
  } else {
    const merged = dedupeTasks([...overdue, ...dueToday]);
    lines.push(...merged.slice(0, cfg.digestMaxTotalTasks).map((t) => formatTaskLine(t, { tz })));
    if (merged.length > cfg.digestMaxTotalTasks) lines.push(`…ещё ${merged.length - cfg.digestMaxTotalTasks}`);
  }

  lines.push("", data.motivation || "Держим темп. Закрой главное до конца дня.");

  return { text: lines.join("\n") };
}
