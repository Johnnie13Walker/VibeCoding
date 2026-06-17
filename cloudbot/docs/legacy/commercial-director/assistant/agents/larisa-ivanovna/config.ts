export const LARISA_IVANOVNA_TIMEZONE = "Europe/Moscow" as const;

export const LARISA_ALLOWED_SCOPES = [
  "calendar",
  "tasks",
  "weather",
  "news",
  "search",
  "telegram",
  "day_planning",
] as const;

export const LARISA_BLOCKED_SCOPES = [
  "crm",
  "deals",
  "sales",
  "sales_analytics",
  "finance",
  "commercial_reporting",
  "devops",
] as const;

export const LARISA_COMMAND_ALIASES = {
  getDayBrief: ["/brief", "/day"],
  createEvent: ["/add-meeting", "/create-event"],
  getWeather: ["/weather"],
  getNews: ["/news"],
  search: ["/search"],
  planDay: ["/plan-day", "/plan"],
} as const;

export const LARISA_LEGACY_COMMAND_ALIASES = {
  getDayBrief: ["day_briefing"],
  createEvent: ["add_calendar_event"],
  search: ["search_request"],
  planDay: ["organize_day"],
} as const;

export type LarisaAllowedScope = (typeof LARISA_ALLOWED_SCOPES)[number];
export type LarisaBlockedScope = (typeof LARISA_BLOCKED_SCOPES)[number];
export type LarisaWorkflowId =
  | "daily_brief"
  | "create_event"
  | "weather"
  | "news"
  | "search"
  | "plan_day";

export const LARISA_LEGACY_WORKFLOW_IDS = ["personal_assistant"] as const;

export const LARISA_LEGACY_SCENARIO_MAP = {
  day_briefing: "daily_brief",
  add_calendar_event: "create_event",
  search_request: "search",
  organize_day: "plan_day",
} as const satisfies Record<string, LarisaWorkflowId>;

export interface LarisaIvanovnaWorkingHours {
  startAtMsk: string;
  endAtMsk: string;
}

export interface LarisaIvanovnaTelegramConfig {
  primaryChannel: "telegram";
  routeKey: string;
  senderConfigKey: string;
  reuseExistingBot: boolean;
  defaultDisableWebPagePreview: boolean;
  defaultParseMode?: "Markdown" | "HTML";
}

export interface LarisaIvanovnaBriefConfig {
  workflowId: "daily_brief";
  maxNewsItems: number;
  maxActionItems: number;
  maxHighlights: number;
  includeLimitations: boolean;
  workingHours: LarisaIvanovnaWorkingHours;
  sections: readonly [
    "header",
    "meetings",
    "free_windows",
    "tasks",
    "weather",
    "news",
    "highlights",
  ];
}

export interface LarisaIvanovnaConfig {
  id: string;
  code: string;
  displayName: string;
  role: "personal_ops_assistant";
  summary: string;
  timezone: typeof LARISA_IVANOVNA_TIMEZONE;
  legacyAgentIds: readonly string[];
  legacyWorkflowIds: readonly string[];
  legacyScenarioMap: typeof LARISA_LEGACY_SCENARIO_MAP;
  legacyCommandAliases: typeof LARISA_LEGACY_COMMAND_ALIASES;
  sourceOfTruthPath: string;
  disableLegacyDirectTelegramDispatch: boolean;
  disableLegacySchedulers: boolean;
  workflowIds: readonly LarisaWorkflowId[];
  allowedScopes: readonly LarisaAllowedScope[];
  blockedScopes: readonly LarisaBlockedScope[];
  defaultCity: string;
  defaultNewsTopics: readonly string[];
  workingHours: LarisaIvanovnaWorkingHours;
  brief: LarisaIvanovnaBriefConfig;
  commandAliases: typeof LARISA_COMMAND_ALIASES;
  telegram: LarisaIvanovnaTelegramConfig;
}

export const larisaIvanovnaConfig: LarisaIvanovnaConfig = {
  id: "larisa-ivanovna",
  code: "larisa_ivanovna",
  displayName: "Лариса Ивановна",
  role: "personal_ops_assistant",
  summary:
    "Отдельный личный контур Cloudbot для календаря, задач, brief дня, погоды, новостей, поиска и планирования дня.",
  timezone: LARISA_IVANOVNA_TIMEZONE,
  legacyAgentIds: ["larisa_assistant", "personal_assistant"],
  legacyWorkflowIds: LARISA_LEGACY_WORKFLOW_IDS,
  legacyScenarioMap: LARISA_LEGACY_SCENARIO_MAP,
  legacyCommandAliases: LARISA_LEGACY_COMMAND_ALIASES,
  sourceOfTruthPath: "agents/larisa-ivanovna",
  disableLegacyDirectTelegramDispatch: true,
  disableLegacySchedulers: true,
  workflowIds: [
    "daily_brief",
    "create_event",
    "weather",
    "news",
    "search",
    "plan_day",
  ],
  allowedScopes: LARISA_ALLOWED_SCOPES,
  blockedScopes: LARISA_BLOCKED_SCOPES,
  defaultCity: "Москва",
  defaultNewsTopics: ["AI", "Технологии", "Москва"],
  workingHours: {
    startAtMsk: "08:30",
    endAtMsk: "18:30",
  },
  brief: {
    workflowId: "daily_brief",
    maxNewsItems: 3,
    maxActionItems: 3,
    maxHighlights: 3,
    includeLimitations: true,
    workingHours: {
      startAtMsk: "08:30",
      endAtMsk: "18:30",
    },
    sections: [
      "header",
      "meetings",
      "free_windows",
      "tasks",
      "weather",
      "news",
      "highlights",
    ],
  },
  commandAliases: LARISA_COMMAND_ALIASES,
  telegram: {
    primaryChannel: "telegram",
    routeKey: "larisa-ivanovna",
    senderConfigKey: "telegram.routes.larisa-ivanovna",
    reuseExistingBot: true,
    defaultDisableWebPagePreview: true,
  },
};
