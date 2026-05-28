import { formatTelegramNewsDigest } from "./telegramNews.formatter";
import { formatTelegramWeather } from "./telegramWeather.formatter";
import type { CalendarBriefBlock, DayBrief, TasksBriefBlock } from "../schemas/brief.schema";

function renderMeetings(calendar: CalendarBriefBlock): string {
  if (!calendar.sourceAvailable) {
    return calendar.limitation ?? "Календарный источник недоступен.";
  }

  const meetings = calendar.meetings;

  if (meetings.length === 0) {
    return "Нет подтвержденных встреч.";
  }

  return meetings
    .map((meeting) => {
      return `- ${formatTimeRange(meeting.startAtMsk, meeting.endAtMsk)} ${meeting.title}`;
    })
    .join("\n");
}

function renderTasks(tasks: TasksBriefBlock): string {
  if (!tasks.sourceAvailable) {
    return tasks.limitation ?? "Источник задач недоступен.";
  }

  const lines: string[] = [];
  const tasksForToday = tasks.tasksForToday;
  const overdueTasks = tasks.overdueTasks;

  if (tasksForToday.length === 0) {
    lines.push("Сегодня: нет подтвержденных задач.");
  } else {
    lines.push(...tasksForToday.map((task) => `- Сегодня: ${task.title}`));
  }

  if (overdueTasks.length === 0) {
    lines.push("- Просроченное: нет.");
  } else {
    lines.push(...overdueTasks.map((task) => `- Просрочено: ${task.title}`));
  }

  return lines.join("\n");
}

function renderFreeWindows(calendar: CalendarBriefBlock): string {
  if (!calendar.sourceAvailable) {
    return calendar.limitation ?? "Свободные окна нельзя рассчитать без календаря.";
  }

  const windows = calendar.freeWindows;

  if (windows.length === 0) {
    return "Свободных окон в рамках рабочего дня не найдено.";
  }

  return windows
    .map((windowItem) => `- ${windowItem.startAtMsk}-${windowItem.endAtMsk}`)
    .join("\n");
}

function renderHighlights(brief: DayBrief): string {
  const highlights = brief.highlights.length > 0 ? brief.highlights : brief.actionItems;

  if (highlights.length === 0) {
    return "Нет подтвержденных акцентов дня.";
  }

  return highlights.map((item) => `- ${item}`).join("\n");
}

function formatTimeRange(startAtMsk: string, endAtMsk: string): string {
  return `${extractClock(startAtMsk)}-${extractClock(endAtMsk)}`;
}

function extractClock(value: string): string {
  return value.includes("T") ? value.slice(11, 16) : value.slice(0, 5);
}

export function formatTelegramBrief(brief: DayBrief): string {
  const lines = [
    `${brief.header.dateMsk}, ${brief.header.weekdayMsk}`,
    "",
    `Фокус дня: ${brief.focus}`,
    "",
    "Встречи:",
    renderMeetings(brief.calendar),
    "",
    "Свободные окна:",
    renderFreeWindows(brief.calendar),
    "",
    "Задачи:",
    renderTasks(brief.tasks),
    "",
    `Погода: ${brief.header.city}`,
    formatTelegramWeather(brief.weather),
    "",
    "Новости по темам:",
    formatTelegramNewsDigest(brief.news),
    "",
    "Акценты дня:",
    renderHighlights(brief),
  ];

  if (brief.limitations.length > 0) {
    lines.push("", "Ограничения:", ...brief.limitations.map((item) => `- ${item}`));
  }

  return lines.join("\n");
}
