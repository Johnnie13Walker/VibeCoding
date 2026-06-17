import { LARISA_IVANOVNA_TIMEZONE } from "../config";

export type CalendarEventStatus = "confirmed" | "tentative" | "cancelled";

export interface CalendarEvent {
  id: string;
  title: string;
  startAtMsk: string;
  endAtMsk: string;
  timezone: typeof LARISA_IVANOVNA_TIMEZONE;
  status: CalendarEventStatus;
  isAllDay?: boolean;
  description?: string;
  participants?: string[];
  location?: string;
  joinUrl?: string;
  sourceId?: string;
  source: "calendar";
}

export interface CreateCalendarEventInput {
  title: string;
  startAtMsk: string;
  endAtMsk?: string;
  timezone?: typeof LARISA_IVANOVNA_TIMEZONE;
  description?: string;
  participants?: string[];
  location?: string;
  joinUrl?: string;
}

export interface CalendarDaySnapshot {
  dateMsk: string;
  meetings: CalendarEvent[];
  sourceAvailable: boolean;
  limitation?: string;
}
