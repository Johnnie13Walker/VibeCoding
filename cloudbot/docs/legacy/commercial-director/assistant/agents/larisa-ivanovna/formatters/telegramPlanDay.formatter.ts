import type { DayBrief, TasksBriefBlock } from "../schemas/brief.schema";
import type { CalendarEvent } from "../schemas/calendar.schema";

type PlanSectionId = "meetings" | "work" | "personal";

interface ClassifiedPlanSections {
  meetings: CalendarEvent[];
  work: CalendarEvent[];
  personal: CalendarEvent[];
}

const MEETING_TITLE_KEYWORDS = [
  "встреч",
  "созвон",
  "звонок",
  "синк",
  "совещ",
  "стендап",
  "обсужд",
  "бриф",
  "демо",
  "интервью",
  "review",
  "sync",
  "call",
  "kickoff",
  "1:1",
  "one on one",
] as const;

const PERSONAL_TITLE_KEYWORDS = [
  "обед",
  "ланч",
  "перерыв",
  "кофе",
  "прогул",
  "пауза",
  "спорт",
  "трениров",
  "врач",
  "здоров",
  "личн",
  "семь",
  "дом",
  "дорог",
  "коммьют",
] as const;

const HOUSEHOLD_TITLE_KEYWORDS = ["обед", "ланч", "перерыв", "кофе", "пауза"] as const;

const MONTH_NAMES = [
  "января",
  "февраля",
  "марта",
  "апреля",
  "мая",
  "июня",
  "июля",
  "августа",
  "сентября",
  "октября",
  "ноября",
  "декабря",
] as const;

export function formatTelegramPlanDay(brief: DayBrief): string {
  const planSections = classifyPlanSections(brief.calendar.meetings);
  const sections = [
    renderCalendarSection("Встречи", planSections.meetings),
    renderCalendarSection("Рабочие блоки", planSections.work),
    renderTasksSection(brief.tasks),
    renderCalendarSection("Личные блоки", planSections.personal),
    renderLimitationsSection(brief.limitations),
  ].filter((section): section is string => section !== undefined);

  const headerLines = [
    formatDisplayDate(brief.header.dateMsk, brief.header.weekdayMsk),
    buildStatusLine(brief, planSections),
    `Фокус: ${brief.focus}`,
  ];

  if (sections.length === 0) {
    sections.push("На день пока нет подтвержденных встреч, блоков и задач.");
  }

  return [headerLines.join("\n"), ...sections].join("\n\n");
}

function classifyPlanSections(events: CalendarEvent[]): ClassifiedPlanSections {
  const sections: ClassifiedPlanSections = {
    meetings: [],
    work: [],
    personal: [],
  };

  for (const event of events) {
    const sectionId = classifyEvent(event);
    sections[sectionId].push(event);
  }

  return sections;
}

function classifyEvent(event: CalendarEvent): PlanSectionId {
  const normalizedTitle = normalizeSearchValue(event.title);

  if (containsKeyword(normalizedTitle, PERSONAL_TITLE_KEYWORDS)) {
    return "personal";
  }

  if (containsKeyword(normalizedTitle, MEETING_TITLE_KEYWORDS)) {
    return "meetings";
  }

  if (getVisibleParticipants(event.participants).length > 0) {
    return "meetings";
  }

  return "work";
}

function buildStatusLine(brief: DayBrief, sections: ClassifiedPlanSections): string {
  if (!brief.calendar.sourceAvailable) {
    return "Календарь недоступен • план собран без подтвержденных встреч и блоков";
  }

  return [
    formatCountPhrase(sections.meetings.length, "встреча", "встречи", "встреч"),
    formatCountPhrase(sections.work.length, "блок работы", "блока работы", "блоков работы"),
    formatCountPhrase(sections.personal.length, "личный блок", "личных блока", "личных блоков"),
  ].join(" • ");
}

function renderCalendarSection(title: string, events: CalendarEvent[]): string | undefined {
  if (events.length === 0) {
    return undefined;
  }

  return [title, events.map(renderEventCard).join("\n\n")].join("\n");
}

function renderEventCard(event: CalendarEvent): string {
  const lines = [formatEventTimeRange(event), formatDisplayTitle(event)];
  const participantsSummary = summarizeParticipants(event.participants);

  if (participantsSummary !== undefined) {
    lines.push(`· ${participantsSummary}`);
  }

  return lines.join("\n");
}

function renderTasksSection(tasks: TasksBriefBlock): string | undefined {
  if (!tasks.sourceAvailable) {
    return undefined;
  }

  if (tasks.tasksForToday.length === 0 && tasks.overdueTasks.length === 0) {
    return undefined;
  }

  const lines = ["Задачи"];

  if (tasks.tasksForToday.length > 0) {
    lines.push("Сегодня");
    lines.push(...tasks.tasksForToday.map((task) => `• ${task.title}`));
  }

  if (tasks.overdueTasks.length > 0) {
    if (tasks.tasksForToday.length > 0) {
      lines.push("");
    }

    lines.push("Просрочено");
    lines.push(...tasks.overdueTasks.map((task) => `• ${task.title}`));
  }

  return lines.join("\n");
}

function renderLimitationsSection(limitations: string[]): string | undefined {
  if (limitations.length === 0) {
    return undefined;
  }

  return ["Ограничения", ...limitations.map((item) => `• ${item}`)].join("\n");
}

function summarizeParticipants(participants: string[] | undefined): string | undefined {
  if (participants === undefined || participants.length === 0) {
    return undefined;
  }

  const visibleParticipants = getVisibleParticipants(participants);

  if (visibleParticipants.length === 0) {
    return undefined;
  }

  const visiblePreview = visibleParticipants.slice(0, 3).join(", ");
  const hiddenCount = visibleParticipants.length - 3;

  return hiddenCount > 0 ? `${visiblePreview}, +${hiddenCount}` : visiblePreview;
}

function getVisibleParticipants(participants: string[] | undefined): string[] {
  if (participants === undefined) {
    return [];
  }

  const uniqueParticipants = new Set<string>();

  for (const participant of participants) {
    const normalized = normalizeParticipantName(participant);

    if (normalized !== undefined) {
      uniqueParticipants.add(normalized);
    }
  }

  return [...uniqueParticipants];
}

function normalizeParticipantName(participant: string): string | undefined {
  const trimmed = participant.trim();

  if (trimmed.length === 0) {
    return undefined;
  }

  const withoutServiceIds = trimmed
    .replace(/\(\s*U\d+\s*\)/gu, " ")
    .replace(/\[\s*U\d+\s*\]/gu, " ")
    .replace(/\bU\d+\b/gu, " ")
    .replace(/\b[A-ZА-Я]\d{3,}\b/gu, " ")
    .replace(/\(\s*\)/gu, " ")
    .replace(/\[\s*\]/gu, " ")
    .replace(/\s{2,}/gu, " ")
    .replace(/^[,.\-()\s]+|[,.\-()\s]+$/gu, "")
    .trim();

  if (withoutServiceIds.length === 0) {
    return undefined;
  }

  const normalizedKey = withoutServiceIds.replace(/[\s._-]+/gu, "");

  if (/^[A-ZА-Я]?\d{3,}$/u.test(normalizedKey)) {
    return undefined;
  }

  return withoutServiceIds;
}

function formatEventTimeRange(event: CalendarEvent): string {
  if (event.isAllDay === true) {
    return "Весь день";
  }

  return `${extractClock(event.startAtMsk)}-${extractClock(event.endAtMsk)}`;
}

function formatDisplayTitle(event: CalendarEvent): string {
  const title = event.title.trim();

  if (title.length === 0) {
    return "Без названия";
  }

  if (isHouseholdEvent(title)) {
    return toSentenceCase(title);
  }

  return title;
}

function isHouseholdEvent(title: string): boolean {
  return containsKeyword(normalizeSearchValue(title), HOUSEHOLD_TITLE_KEYWORDS);
}

function formatDisplayDate(dateMsk: string, weekdayMsk: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/u.exec(dateMsk);

  if (match === null) {
    return `${dateMsk}, ${weekdayMsk}`;
  }

  const [, , month, day] = match;
  const monthIndex = Number(month) - 1;
  const monthName = MONTH_NAMES[monthIndex];

  if (monthName === undefined) {
    return `${dateMsk}, ${weekdayMsk}`;
  }

  return `${Number(day)} ${monthName}, ${weekdayMsk}`;
}

function formatCountPhrase(
  count: number,
  singular: string,
  few: string,
  many: string,
): string {
  return `${count} ${resolvePluralForm(count, singular, few, many)}`;
}

function resolvePluralForm(count: number, singular: string, few: string, many: string): string {
  const normalizedCount = Math.abs(count) % 100;
  const lastDigit = normalizedCount % 10;

  if (normalizedCount >= 11 && normalizedCount <= 19) {
    return many;
  }

  if (lastDigit === 1) {
    return singular;
  }

  if (lastDigit >= 2 && lastDigit <= 4) {
    return few;
  }

  return many;
}

function extractClock(value: string): string {
  return value.includes("T") ? value.slice(11, 16) : value.slice(0, 5);
}

function containsKeyword(value: string, keywords: readonly string[]): boolean {
  return keywords.some((keyword) => value.includes(keyword));
}

function normalizeSearchValue(value: string): string {
  return value.trim().toLowerCase();
}

function toSentenceCase(value: string): string {
  const lowerCased = value.trim().toLowerCase();

  if (lowerCased.length === 0) {
    return value;
  }

  return `${lowerCased[0].toUpperCase()}${lowerCased.slice(1)}`;
}
