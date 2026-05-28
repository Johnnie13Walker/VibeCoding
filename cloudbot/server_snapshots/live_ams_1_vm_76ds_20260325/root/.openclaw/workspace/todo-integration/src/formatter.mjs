import { formatRuDateFromISO } from "./time.mjs";
import { toTimePart } from "./service.mjs";

function escapeHtml(s = "") {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function parseTitleAndLink(task) {
  const content = String(task.content || "").trim();

  const md = content.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/i);
  if (md) {
    return { title: md[1].trim(), link: md[2].trim() };
  }

  const rawUrl = content.match(/^(https?:\/\/\S+)$/i);
  if (rawUrl) {
    try {
      const u = new URL(rawUrl[1]);
      const host = u.hostname.replace(/^www\./, "");
      const title = host.includes("bitrix24") ? "CRM задача" : (host.includes("docs.google.com") ? "Google Sheet" : `Ссылка: ${host}`);
      return { title, link: rawUrl[1] };
    } catch {
      return { title: "Ссылка", link: rawUrl[1] };
    }
  }

  return { title: content || "(без названия)", link: task.url || null };
}

function renderTask(task, idx, tz) {
  const { title, link } = parseTitleAndLink(task);
  const time = toTimePart(task, tz);
  const suffix = time ? ` <i>· ${escapeHtml(time)}</i>` : "";
  const head = `${idx}. ${escapeHtml(title)}${suffix}`;
  const linkLine = link ? `\n   ↗ <a href="${escapeHtml(link)}">Открыть</a>` : "";
  return `${head}${linkLine}`;
}

function renderTaskList(tasks, tz, limit = 20) {
  const shown = limit == null ? tasks : tasks.slice(0, limit);
  const rest = limit == null ? 0 : (tasks.length - shown.length);
  const lines = shown.map((t, i) => renderTask(t, i + 1, tz));
  if (rest > 0) lines.push(`…ещё ${rest}`);
  return lines;
}

export function formatTasksForDate(tasks, isoDate, tz, { titlePrefix = "Задачи на", limit = 20 } = {}) {
  const d = formatRuDateFromISO(isoDate);
  const title = titlePrefix.toLowerCase().includes("сегодня")
    ? `📌 <b>${escapeHtml(titlePrefix)} (${d})</b>`
    : `📌 <b>${escapeHtml(titlePrefix)} ${d}</b>`;

  if (!tasks.length) {
    return `${title}\n\nНа сегодня задач нет ✅`;
  }

  return [title, "", ...renderTaskList(tasks, tz, limit)].join("\n");
}

export function formatOverdue(tasks, tz) {
  if (!tasks.length) return "Просроченных задач нет ✅";
  return ["🔴 <b>Просроченные задачи</b>", "", ...renderTaskList(tasks, tz, 20)].join("\n");
}

export function formatPriorityCounts(title, counts) {
  return [
    title,
    `🔥 Приоритет 1: ${counts.P1 || 0}`,
    `⭐ Приоритет 2: ${counts.P2 || 0}`,
    `⚡ Приоритет 3: ${counts.P3 || 0}`,
    `🧩 Приоритет 4: ${counts.P4 || 0}`
  ].join("\n");
}

export function formatTasksHelp() {
  return [
    "🧭 <b>Команды задач</b>",
    "",
    "Просмотр:",
    "/tasks today",
    "/tasks tomorrow",
    "/tasks aftertomorrow",
    "/tasks YYYY-MM-DD",
    "/tasks full",
    "/overdue",
    "/focus",
    "/replan",
    "/insights",
    "/day today|tomorrow|aftertomorrow|YYYY-MM-DD",
    "/agenda today",
    "/free today",
    "/sync_status",
    "/diag",
    "",
    "Календари:",
    "/connect_google",
    "/oauth_google <callback_url>",
    "/connect_bitrix",
    "/oauth_bitrix <callback_url>",
    "/users_sync",
    "/users_refresh",
    "/users_find <имя>",
    "/users_status",
    "/meet_section <id>",
    "/meet_create <текст>",
    "/meet_move <id|поиск> <новое время>",
    "/meet_cancel <id|поиск>",
    "",
    "Напоминания:",
    "/reminders on",
    "/reminders off",
    "/reminders status",
    "",
    "Продуктивность:",
    "/focus_blocks",
    "/focus_accept",
    "/focus_edit 10:30-11:30,15:00-16:00",
    "/focus_off",
    "/dnd on",
    "/dnd off",
    "/dnd status",
    "/dnd set 22:30 08:30",
    "/reschedule <task_id> <YYYY-MM-DDTHH:MM:SS+03:00|keep>",
    "",
    "Живой ассистент:",
    "/assistant on",
    "/assistant off",
    "/assistant status",
    "/profile on",
    "/profile off",
    "/profile status",
    "/profile wipe",
    "/me",
    "",
    "Добавление:",
    "/add <текст задачи>",
    "/add_cancel",
    "/priority_help",
    "",
    "Можно и обычным текстом: «добавь задачу ...»"
  ].join("\n");
}
