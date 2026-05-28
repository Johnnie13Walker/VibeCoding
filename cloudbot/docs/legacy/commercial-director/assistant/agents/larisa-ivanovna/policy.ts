import {
  LARISA_ALLOWED_SCOPES,
  LARISA_BLOCKED_SCOPES,
  type LarisaAllowedScope,
  type LarisaBlockedScope,
  larisaIvanovnaConfig,
} from "./config";

export interface PolicyCheck {
  allowed: boolean;
  domain?: LarisaAllowedScope | LarisaBlockedScope;
  matchedKeywords?: string[];
  reason?: string;
}

export interface LarisaDomainRule {
  domain: LarisaAllowedScope | LarisaBlockedScope;
  access: "allowed" | "blocked";
  description: string;
  keywords: readonly string[];
  commands: readonly string[];
}

const LARISA_DOMAIN_RULES: readonly LarisaDomainRule[] = [
  {
    domain: "calendar",
    access: "allowed",
    description: "Личный календарь, встречи и свободные окна.",
    keywords: ["календар", "встреч", "созвон", "слот", "окно", "расписан"],
    commands: ["create_event"],
  },
  {
    domain: "tasks",
    access: "allowed",
    description: "Личные задачи и todo-контур.",
    keywords: ["задач", "todo", "таск", "дедлайн", "приоритет"],
    commands: [],
  },
  {
    domain: "weather",
    access: "allowed",
    description: "Погодный блок по Москве и другим подтвержденным городам.",
    keywords: ["погод", "температур", "дожд", "снег", "ветер"],
    commands: ["get_weather"],
  },
  {
    domain: "news",
    access: "allowed",
    description: "Короткий новостной блок по заданным темам.",
    keywords: ["новост", "headline", "тема", "дайджест"],
    commands: ["get_news"],
  },
  {
    domain: "search",
    access: "allowed",
    description: "Пользовательский поиск по конкретному запросу.",
    keywords: ["найди", "поиск", "поищи", "search", "узнай"],
    commands: ["search"],
  },
  {
    domain: "telegram",
    access: "allowed",
    description: "Telegram-доставка в существующий контур Ларисы Ивановны.",
    keywords: ["telegram", "телеграм", "бот", "чат"],
    commands: [],
  },
  {
    domain: "day_planning",
    access: "allowed",
    description: "Brief дня и помощь в планировании.",
    keywords: ["бриф", "план", "день", "утро", "свободные окна"],
    commands: ["get_day_brief", "plan_day"],
  },
  {
    domain: "crm",
    access: "blocked",
    description: "CRM и клиентский контур не относятся к Ларисе Ивановне.",
    keywords: ["crm", "лид", "клиентск", "контрагент"],
    commands: [],
  },
  {
    domain: "deals",
    access: "blocked",
    description: "Сделки и воронка продаж вынесены в отдельный контур.",
    keywords: ["сделк", "воронк", "pipeline"],
    commands: [],
  },
  {
    domain: "sales",
    access: "blocked",
    description: "Продажи и коммерческие запросы запрещены.",
    keywords: ["продаж", "sales", "выручк", "коммерческ"],
    commands: [],
  },
  {
    domain: "sales_analytics",
    access: "blocked",
    description: "Sales analytics не входит в personal assistant слой.",
    keywords: ["конверси", "средний чек", "аналитик", "kpi"],
    commands: [],
  },
  {
    domain: "finance",
    access: "blocked",
    description: "Финансовая аналитика вынесена за пределы роли.",
    keywords: ["финанс", "p&l", "бюджет", "cashflow", "денеж"],
    commands: [],
  },
  {
    domain: "commercial_reporting",
    access: "blocked",
    description: "Коммерческая отчетность не маршрутизируется в этот агент.",
    keywords: ["отчет по продаж", "план-факт", "коммерческий отчет"],
    commands: [],
  },
  {
    domain: "devops",
    access: "blocked",
    description: "DevOps и серверная инфраструктура не входят в контур Ларисы Ивановны.",
    keywords: ["сервер", "деплой", "docker", "cron", "infra", "devops"],
    commands: [],
  },
] as const;

const LARISA_COMMAND_DOMAIN_MAP = new Map<string, LarisaAllowedScope>([
  ["get_day_brief", "day_planning"],
  ["day_briefing", "day_planning"],
  ["plan_day", "day_planning"],
  ["organize_day", "day_planning"],
  ["create_event", "calendar"],
  ["add_calendar_event", "calendar"],
  ["get_weather", "weather"],
  ["get_news", "news"],
  ["search", "search"],
  ["search_request", "search"],
]);

function findRuleByDomain(
  domain: string,
): LarisaDomainRule | undefined {
  return LARISA_DOMAIN_RULES.find((rule) => rule.domain === domain);
}

function findRuleByText(text: string): {
  rule: LarisaDomainRule;
  matchedKeywords: string[];
} | undefined {
  const normalized = text.trim().toLowerCase();

  if (normalized.length === 0) {
    return undefined;
  }

  const orderedRules = [
    ...LARISA_DOMAIN_RULES.filter((rule) => rule.access === "blocked"),
    ...LARISA_DOMAIN_RULES.filter((rule) => rule.access === "allowed"),
  ];

  for (const rule of orderedRules) {
    const matchedKeywords = rule.keywords.filter((keyword) => normalized.includes(keyword));

    if (matchedKeywords.length > 0) {
      return {
        rule,
        matchedKeywords,
      };
    }
  }

  return undefined;
}

export const larisaIvanovnaPolicy = {
  agentId: larisaIvanovnaConfig.id,
  timezone: larisaIvanovnaConfig.timezone,
  allowedScopes: new Set<LarisaAllowedScope>(LARISA_ALLOWED_SCOPES),
  blockedScopes: new Set<LarisaBlockedScope>(LARISA_BLOCKED_SCOPES),
  domainRules: LARISA_DOMAIN_RULES,
  commandDomainMap: LARISA_COMMAND_DOMAIN_MAP,

  canAccess(scope: string): PolicyCheck {
    if (this.blockedScopes.has(scope as LarisaBlockedScope)) {
      return {
        allowed: false,
        domain: scope as LarisaBlockedScope,
        reason: `Контур ${larisaIvanovnaConfig.displayName} не имеет доступа к домену ${scope}.`,
      };
    }

    if (!this.allowedScopes.has(scope as LarisaAllowedScope)) {
      return {
        allowed: false,
        reason: `Домен ${scope} не входит в подтвержденную зону ответственности агента.`,
      };
    }

    return {
      allowed: true,
      domain: scope as LarisaAllowedScope,
    };
  },

  assertAllowed(scope: string): void {
    const result = this.canAccess(scope);

    if (!result.allowed) {
      throw new Error(result.reason);
    }
  },

  resolveCommandDomain(commandName: string): LarisaAllowedScope | undefined {
    return this.commandDomainMap.get(commandName);
  },

  canRunCommand(commandName: string): PolicyCheck {
    const domain = this.resolveCommandDomain(commandName);

    if (domain === undefined) {
      return {
        allowed: false,
        reason: `Команда ${commandName} не сопоставлена с доменом Ларисы Ивановны.`,
      };
    }

    return this.canAccess(domain);
  },

  matchInput(text: string): PolicyCheck {
    const matched = findRuleByText(text);

    if (matched === undefined) {
      return {
        allowed: false,
        reason: "Не удалось уверенно сопоставить запрос с доменом Ларисы Ивановны.",
      };
    }

    const access = this.canAccess(matched.rule.domain);

    return {
      ...access,
      domain: matched.rule.domain,
      matchedKeywords: matched.matchedKeywords,
      reason: access.reason ?? matched.rule.description,
    };
  },

  explainDomain(domain: string): string | undefined {
    return findRuleByDomain(domain)?.description;
  },

  isPrimaryTelegramRoute(routeKey: string): boolean {
    return routeKey === larisaIvanovnaConfig.telegram.routeKey;
  },
};
