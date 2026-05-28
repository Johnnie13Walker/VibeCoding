import { LARISA_IVANOVNA_TIMEZONE, larisaIvanovnaConfig } from "../config";
import type { CalendarProvider } from "../providers/calendar.provider";
import type { NewsProvider } from "../providers/news.provider";
import type { TasksProvider } from "../providers/tasks.provider";
import type { WeatherProvider } from "../providers/weather.provider";
import type { DayBrief, DayBriefRequest, FreeWindow } from "../schemas/brief.schema";
import type { CalendarDaySnapshot, CalendarEvent } from "../schemas/calendar.schema";
import type { NewsDigest } from "../schemas/news.schema";
import type { TaskDaySnapshot } from "../schemas/task.schema";

export interface DailyBriefWorkflowDeps {
  calendarProvider: CalendarProvider;
  tasksProvider: TasksProvider;
  weatherProvider: WeatherProvider;
  newsProvider: NewsProvider;
}

export async function buildDayBrief(
  input: DayBriefRequest,
  deps: DailyBriefWorkflowDeps,
): Promise<DayBrief> {
  const topics = input.newsTopics ?? [...larisaIvanovnaConfig.defaultNewsTopics];
  const city = input.city ?? larisaIvanovnaConfig.defaultCity;

  const [calendarSnapshot, taskSnapshot, weather, news] = await Promise.all([
    loadCalendarSnapshot(input, deps),
    loadTaskSnapshot(input, deps),
    loadWeatherSnapshot(input, city, deps),
    loadNewsDigest(input, topics, deps),
  ]);

  const freeWindows = calendarSnapshot.sourceAvailable
    ? calculateFreeWindows(
        calendarSnapshot.meetings,
        larisaIvanovnaConfig.brief.workingHours.startAtMsk,
        larisaIvanovnaConfig.brief.workingHours.endAtMsk,
      )
    : [];
  const limitations = [
    calendarSnapshot.limitation,
    taskSnapshot.limitation,
    weather.limitation,
    news.limitation,
  ].filter((item): item is string => item !== undefined && item.length > 0);

  const focus = buildDayFocus({
    meetings: calendarSnapshot.meetings,
    tasksForToday: taskSnapshot.tasksForToday,
    overdueTasks: taskSnapshot.overdueTasks,
    freeWindows,
  });

  return {
    header: {
      dateMsk: input.dateMsk,
      weekdayMsk: input.weekdayMsk,
      timezone: LARISA_IVANOVNA_TIMEZONE,
      city: weather.city,
    },
    calendar: {
      meetings: calendarSnapshot.meetings,
      freeWindows,
      sourceAvailable: calendarSnapshot.sourceAvailable,
      limitation: calendarSnapshot.limitation,
    },
    tasks: {
      tasksForToday: taskSnapshot.tasksForToday,
      overdueTasks: taskSnapshot.overdueTasks,
      sourceAvailable: taskSnapshot.sourceAvailable,
      limitation: taskSnapshot.limitation,
    },
    weather,
    news: {
      ...news,
      items: news.items.slice(0, larisaIvanovnaConfig.brief.maxNewsItems),
    },
    focus,
    highlights: buildHighlights({
      meetings: calendarSnapshot.meetings,
      tasksForToday: taskSnapshot.tasksForToday,
      overdueTasks: taskSnapshot.overdueTasks,
      freeWindows,
    }),
    actionItems: buildActionItems({
      meetings: calendarSnapshot.meetings,
      tasksForToday: taskSnapshot.tasksForToday,
      overdueTasks: taskSnapshot.overdueTasks,
      freeWindows,
    }),
    limitations:
      larisaIvanovnaConfig.brief.includeLimitations
        ? limitations
        : [],
  };
}

async function loadCalendarSnapshot(
  input: DayBriefRequest,
  deps: DailyBriefWorkflowDeps,
): Promise<CalendarDaySnapshot> {
  try {
    return await deps.calendarProvider.getDaySnapshot({
      dateMsk: input.dateMsk,
      timezone: LARISA_IVANOVNA_TIMEZONE,
    });
  } catch (error) {
    return {
      dateMsk: input.dateMsk,
      meetings: [],
      sourceAvailable: false,
      limitation: appendProviderFailureDetails(
        "Календарный источник временно недоступен. Блок встреч и свободных окон собран без данных.",
        error,
      ),
    };
  }
}

async function loadTaskSnapshot(
  input: DayBriefRequest,
  deps: DailyBriefWorkflowDeps,
): Promise<TaskDaySnapshot> {
  try {
    return await deps.tasksProvider.getDaySnapshot({
      dateMsk: input.dateMsk,
      timezone: LARISA_IVANOVNA_TIMEZONE,
    });
  } catch (error) {
    return {
      dateMsk: input.dateMsk,
      tasksForToday: [],
      overdueTasks: [],
      sourceAvailable: false,
      limitation: appendProviderFailureDetails(
        "Источник задач временно недоступен. Блок задач собран без данных.",
        error,
      ),
    };
  }
}

async function loadWeatherSnapshot(
  input: DayBriefRequest,
  city: string,
  deps: DailyBriefWorkflowDeps,
): Promise<DayBrief["weather"]> {
  try {
    return await deps.weatherProvider.getWeather({
      dateMsk: input.dateMsk,
      city,
      timezone: LARISA_IVANOVNA_TIMEZONE,
    });
  } catch (error) {
    return {
      city,
      summary: "Погодный источник временно недоступен.",
      alerts: [],
      sourceAvailable: false,
      limitation: appendProviderFailureDetails(
        "Погодный источник временно недоступен. Блок погоды пропущен.",
        error,
      ),
      source: "weather",
    };
  }
}

async function loadNewsDigest(
  input: DayBriefRequest,
  topics: readonly string[],
  deps: DailyBriefWorkflowDeps,
): Promise<NewsDigest> {
  try {
    return await deps.newsProvider.getDigest({
      dateMsk: input.dateMsk,
      topics,
      timezone: LARISA_IVANOVNA_TIMEZONE,
    });
  } catch (error) {
    return {
      dateMsk: input.dateMsk,
      topics,
      items: [],
      sourceAvailable: false,
      limitation: appendProviderFailureDetails(
        "Источник новостей временно недоступен. Блок новостей пропущен.",
        error,
      ),
    };
  }
}

function appendProviderFailureDetails(baseMessage: string, error: unknown): string {
  const errorMessage = normalizeProviderErrorMessage(error);

  if (errorMessage === undefined) {
    return baseMessage;
  }

  return `${baseMessage} Причина: ${errorMessage}.`;
}

function normalizeProviderErrorMessage(error: unknown): string | undefined {
  if (!(error instanceof Error)) {
    return undefined;
  }

  const normalized = error.message.trim().replace(/\.+$/u, "");

  if (normalized.length === 0) {
    return undefined;
  }

  const httpStatusMatch = normalized.match(/\bHTTP(?:\s+Error)?\s+(\d{3})\b/i);
  const statusCode = Number(httpStatusMatch?.[1]);

  if (!Number.isNaN(statusCode)) {
    if (statusCode >= 500) {
      return "сервис задач временно недоступен на стороне источника";
    }

    if (statusCode === 429) {
      return "источник временно ограничил запросы";
    }

    if (statusCode >= 400) {
      return "источник отклонил запрос";
    }
  }

  if (/\b(?:timed?\s*out|timeout|etimedout)\b/i.test(normalized)) {
    return "истекло время ожидания ответа от источника";
  }

  if (/\b(?:econnrefused|enotfound|eai_again|network\s+error|fetch\s+failed)\b/i.test(normalized)) {
    return "не удалось установить соединение с источником";
  }

  return "внутренняя ошибка интеграции";
}

export function calculateFreeWindows(
  meetings: CalendarEvent[],
  dayStart = larisaIvanovnaConfig.brief.workingHours.startAtMsk,
  dayEnd = larisaIvanovnaConfig.brief.workingHours.endAtMsk,
): FreeWindow[] {
  if (meetings.length === 0) {
    return [
      {
        startAtMsk: dayStart,
        endAtMsk: dayEnd,
        source: "calendar",
      },
    ];
  }

  const sortedMeetings = [...meetings].sort((left, right) => {
    return toMinutes(extractClock(left.startAtMsk)) - toMinutes(extractClock(right.startAtMsk));
  });

  const windows: FreeWindow[] = [];
  let cursor = toMinutes(dayStart);
  const dayEndMinutes = toMinutes(dayEnd);

  for (const meeting of sortedMeetings) {
    const meetingStart = toMinutes(extractClock(meeting.startAtMsk));
    const meetingEnd = toMinutes(extractClock(meeting.endAtMsk));

    if (meetingStart > cursor) {
      windows.push({
        startAtMsk: fromMinutes(cursor),
        endAtMsk: fromMinutes(meetingStart),
        source: "calendar",
      });
    }

    if (meetingEnd > cursor) {
      cursor = meetingEnd;
    }
  }

  if (cursor < dayEndMinutes) {
    windows.push({
      startAtMsk: fromMinutes(cursor),
      endAtMsk: fromMinutes(dayEndMinutes),
      source: "calendar",
    });
  }

  return windows;
}

function buildDayFocus(input: {
  meetings: CalendarEvent[];
  tasksForToday: Array<{ title: string }>;
  overdueTasks: Array<{ title: string }>;
  freeWindows: FreeWindow[];
}): string {
  if (input.meetings.length === 0 && input.tasksForToday.length === 0 && input.overdueTasks.length === 0) {
    return "Подтвержденных событий мало. День можно собрать вокруг личных приоритетов и уточнения задач.";
  }

  if (input.overdueTasks.length > 0) {
    return `Сначала закрыть просроченное: ${input.overdueTasks[0].title}.`;
  }

  if (input.meetings.length > 0) {
    return `День привязан к встрече ${extractClock(input.meetings[0].startAtMsk)}: ${input.meetings[0].title}.`;
  }

  if (input.freeWindows.length > 0) {
    return `Есть окно ${input.freeWindows[0].startAtMsk}-${input.freeWindows[0].endAtMsk} для фокусной работы.`;
  }

  return `Главный приоритет дня: ${input.tasksForToday[0].title}.`;
}

function buildActionItems(input: {
  meetings: CalendarEvent[];
  tasksForToday: Array<{ title: string }>;
  overdueTasks: Array<{ title: string }>;
  freeWindows: FreeWindow[];
}): string[] {
  const actionItems: string[] = [];

  if (input.overdueTasks.length > 0) {
    actionItems.push(`Закрыть просроченную задачу: ${input.overdueTasks[0].title}.`);
  }

  if (input.tasksForToday.length > 0) {
    actionItems.push(`Зафиксировать время на задачу: ${input.tasksForToday[0].title}.`);
  }

  if (input.meetings.length > 0) {
    actionItems.push(
      `Подготовиться к встрече ${extractClock(input.meetings[0].startAtMsk)}: ${input.meetings[0].title}.`,
    );
  } else if (input.freeWindows.length > 0) {
    actionItems.push(
      `Использовать окно ${input.freeWindows[0].startAtMsk}-${input.freeWindows[0].endAtMsk} для фокусной работы.`,
    );
  }

  if (actionItems.length === 0) {
    actionItems.push("Уточнить задачи и календарь перед началом дня.");
  }

  return actionItems.slice(0, larisaIvanovnaConfig.brief.maxActionItems);
}

function buildHighlights(input: {
  meetings: CalendarEvent[];
  tasksForToday: Array<{ title: string }>;
  overdueTasks: Array<{ title: string }>;
  freeWindows: FreeWindow[];
}): string[] {
  const highlights: string[] = [];

  if (input.meetings.length > 0) {
    highlights.push(
      `Первая встреча в ${extractClock(input.meetings[0].startAtMsk)}: ${input.meetings[0].title}.`,
    );
  } else {
    highlights.push("Подтвержденных встреч на день нет.");
  }

  if (input.overdueTasks.length > 0) {
    highlights.push(`Есть просроченная задача: ${input.overdueTasks[0].title}.`);
  } else if (input.tasksForToday.length > 0) {
    highlights.push(`Главная задача на сегодня: ${input.tasksForToday[0].title}.`);
  }

  if (input.freeWindows.length > 0) {
    highlights.push(
      `Ближайшее свободное окно: ${input.freeWindows[0].startAtMsk}-${input.freeWindows[0].endAtMsk}.`,
    );
  }

  return highlights.slice(0, larisaIvanovnaConfig.brief.maxHighlights);
}

function extractClock(value: string): string {
  return value.includes("T") ? value.slice(11, 16) : value.slice(0, 5);
}

function toMinutes(value: string): number {
  const [hours, minutes] = value.split(":").map((part) => Number(part));
  return hours * 60 + minutes;
}

function fromMinutes(value: number): string {
  const hours = Math.floor(value / 60)
    .toString()
    .padStart(2, "0");
  const minutes = (value % 60).toString().padStart(2, "0");
  return `${hours}:${minutes}`;
}
