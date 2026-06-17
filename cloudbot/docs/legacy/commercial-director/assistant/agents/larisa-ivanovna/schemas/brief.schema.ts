import { LARISA_IVANOVNA_TIMEZONE } from "../config";
import type { CalendarDaySnapshot } from "./calendar.schema";
import type { NewsDigest } from "./news.schema";
import type { TaskDaySnapshot } from "./task.schema";

export interface GetDayBriefInput {
  dateMsk?: string;
  date?: string;
  date_msk?: string;
  weekdayMsk?: string;
  weekday?: string;
  weekday_msk?: string;
  newsTopics?: string[];
  topics?: string[];
  news_topics?: string[];
  city?: string;
}

export interface DayBriefRequest {
  dateMsk: string;
  weekdayMsk: string;
  newsTopics?: string[];
  city?: string;
}

export interface FreeWindow {
  startAtMsk: string;
  endAtMsk: string;
  source: "calendar";
}

export interface DayBriefHeader {
  dateMsk: string;
  weekdayMsk: string;
  timezone: typeof LARISA_IVANOVNA_TIMEZONE;
  city: string;
}

export interface CalendarBriefBlock
  extends Pick<CalendarDaySnapshot, "meetings" | "sourceAvailable" | "limitation"> {
  freeWindows: FreeWindow[];
}

export interface TasksBriefBlock
  extends Pick<TaskDaySnapshot, "tasksForToday" | "overdueTasks" | "sourceAvailable" | "limitation"> {}

export interface WeatherSnapshot {
  city: string;
  summary: string;
  temperatureC?: {
    min: number;
    max: number;
  };
  alerts?: string[];
  sourceAvailable: boolean;
  limitation?: string;
  source: "weather";
}

export interface DayBrief {
  header: DayBriefHeader;
  calendar: CalendarBriefBlock;
  tasks: TasksBriefBlock;
  weather: WeatherSnapshot;
  news: NewsDigest;
  focus: string;
  highlights: string[];
  actionItems: string[];
  limitations: string[];
}

export interface DayBriefWorkflowResult {
  brief: DayBrief;
  text?: string;
}
