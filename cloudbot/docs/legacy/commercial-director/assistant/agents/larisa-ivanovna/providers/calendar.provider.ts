import { LARISA_IVANOVNA_TIMEZONE } from "../config";
import type {
  CalendarDaySnapshot,
  CalendarEvent,
  CreateCalendarEventInput,
} from "../schemas/calendar.schema";

export interface CalendarDayQuery {
  dateMsk: string;
  timezone: typeof LARISA_IVANOVNA_TIMEZONE;
}

export interface CreateCalendarEventResult {
  created: boolean;
  event?: CalendarEvent;
  limitation?: string;
}

export interface CalendarProvider {
  readonly providerId?: string;
  getDaySnapshot(input: CalendarDayQuery): Promise<CalendarDaySnapshot>;
  createEvent(input: CreateCalendarEventInput): Promise<CreateCalendarEventResult>;
}

export class NullCalendarProvider implements CalendarProvider {
  readonly providerId = "null-calendar";

  async getDaySnapshot(input: CalendarDayQuery): Promise<CalendarDaySnapshot> {
    return {
      dateMsk: input.dateMsk,
      meetings: [],
      sourceAvailable: false,
      limitation: "Календарный provider еще не подключен к контуру Ларисы Ивановны.",
    };
  }

  async createEvent(): Promise<CreateCalendarEventResult> {
    return {
      created: false,
      limitation: "Создание встреч недоступно, пока календарный provider не подключен.",
    };
  }
}
