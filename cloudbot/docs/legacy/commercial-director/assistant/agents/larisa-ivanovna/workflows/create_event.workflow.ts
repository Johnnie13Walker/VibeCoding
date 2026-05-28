import { LARISA_IVANOVNA_TIMEZONE } from "../config";
import type {
  CalendarEvent,
  CreateCalendarEventInput,
} from "../schemas/calendar.schema";
import type { CalendarProvider } from "../providers/calendar.provider";

export interface CreateEventWorkflowDeps {
  calendarProvider: CalendarProvider;
}

export interface CreateEventWorkflowResult {
  text: string;
  created: boolean;
  event?: CalendarEvent;
  limitation?: string;
}

export async function runCreateEventWorkflow(
  input: Omit<CreateCalendarEventInput, "timezone"> & {
    timezone?: CreateCalendarEventInput["timezone"];
  },
  deps: CreateEventWorkflowDeps,
): Promise<CreateEventWorkflowResult> {
  if (input.title === undefined || input.title.trim().length === 0) {
    return {
      text: "Нельзя создать встречу без названия.",
      created: false,
      limitation: "Отсутствует обязательное поле title.",
    };
  }

  if (input.startAtMsk === undefined || input.startAtMsk.trim().length === 0) {
    return {
      text: "Нельзя создать встречу без времени начала.",
      created: false,
      limitation: "Отсутствует обязательное поле startAtMsk.",
    };
  }

  const result = await deps.calendarProvider.createEvent({
    ...input,
    timezone: input.timezone ?? LARISA_IVANOVNA_TIMEZONE,
  });

  if (!result.created || result.event === undefined) {
    return {
      text: result.limitation ?? "Не удалось создать встречу.",
      created: false,
      limitation: result.limitation,
    };
  }

  return {
    text: `Встреча создана: ${formatTime(result.event.startAtMsk)} ${result.event.title}.`,
    created: true,
    event: result.event,
  };
}

function formatTime(value: string): string {
  return value.includes("T") ? value.slice(11, 16) : value.slice(0, 5);
}
