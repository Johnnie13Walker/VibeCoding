export type AgendaMeeting = {
  source: "google" | "bitrix";
  sources?: Array<"google" | "bitrix">;
  id: string;
  title: string;
  start: string;
  end: string;
  location?: string;
  link?: string;
  attendeeIds?: string[];
  attendees?: string[];
  isAllDay?: boolean;
};

export type AgendaTask = {
  id: string;
  content: string;
  dueDateTime?: string | null;
  dueDate?: string | null;
  url?: string | null;
  priority?: number;
};

export type FreeSlot = { start: string; end: string };

export type AgendaResult = {
  date: string;
  meetings: AgendaMeeting[];
  tasks: AgendaTask[];
  freeSlots: FreeSlot[];
  overdueCount?: number;
};
