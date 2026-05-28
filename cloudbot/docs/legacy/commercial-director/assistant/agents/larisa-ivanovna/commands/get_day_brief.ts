import { LARISA_COMMAND_ALIASES, larisaIvanovnaConfig } from "../config";
import { formatTelegramBrief } from "../formatters/telegramBrief.formatter";
import type { DayBrief, DayBriefRequest, GetDayBriefInput } from "../schemas/brief.schema";
import { buildDayBrief, type DailyBriefWorkflowDeps } from "../workflows/daily_brief.workflow";

export interface DayBriefWorkflow {
  run(input: DayBriefRequest): Promise<DayBrief>;
}

export interface GetDayBriefCommandDeps extends DailyBriefWorkflowDeps {
  dayBriefWorkflow?: DayBriefWorkflow;
}

function resolveDayBriefWorkflow(deps: GetDayBriefCommandDeps): DayBriefWorkflow {
  if (deps.dayBriefWorkflow !== undefined) {
    return deps.dayBriefWorkflow;
  }

  return {
    async run(input: DayBriefRequest): Promise<DayBrief> {
      return buildDayBrief(input, deps);
    },
  };
}

function resolveCurrentDateMsk(): string {
  const formatter = new Intl.DateTimeFormat("ru-RU", {
    timeZone: larisaIvanovnaConfig.timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });

  const parts = formatter.formatToParts(new Date());
  const day = parts.find((part) => part.type === "day")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  const year = parts.find((part) => part.type === "year")?.value;

  if (day === undefined || month === undefined || year === undefined) {
    throw new Error("Не удалось определить текущую дату в московском часовом поясе.");
  }

  return `${year}-${month}-${day}`;
}

function resolveWeekdayMsk(dateMsk: string): string {
  const [year, month, day] = dateMsk.split("-").map((part) => Number(part));
  const utcDate = new Date(Date.UTC(year, month - 1, day));

  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: larisaIvanovnaConfig.timezone,
    weekday: "long",
  }).format(utcDate);
}

export function normalizeDayBriefRequest(input: GetDayBriefInput = {}): DayBriefRequest {
  const dateMsk = input.dateMsk ?? input.date_msk ?? input.date ?? resolveCurrentDateMsk();

  return {
    dateMsk,
    weekdayMsk: input.weekdayMsk ?? input.weekday_msk ?? input.weekday ?? resolveWeekdayMsk(dateMsk),
    newsTopics: input.newsTopics ?? input.news_topics ?? input.topics,
    city: input.city,
  };
}

export function createGetDayBriefCommand(deps: GetDayBriefCommandDeps) {
  const workflow = resolveDayBriefWorkflow(deps);

  return {
    name: "get_day_brief",
    aliases: [
      ...LARISA_COMMAND_ALIASES.getDayBrief,
      ...larisaIvanovnaConfig.legacyCommandAliases.getDayBrief,
    ],
    async execute(input: GetDayBriefInput = {}) {
      const request = normalizeDayBriefRequest(input);
      const brief = await workflow.run(request);

      return {
        text: formatTelegramBrief(brief),
        payload: brief,
      };
    },
  };
}
