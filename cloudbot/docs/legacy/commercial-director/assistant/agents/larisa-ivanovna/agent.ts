import { larisaIvanovnaConfig } from "./config";
import { larisaIvanovnaPolicy } from "./policy";
import { createCreateEventCommand } from "./commands/create_event";
import {
  createGetDayBriefCommand,
  type DayBriefWorkflow,
} from "./commands/get_day_brief";
import { createGetNewsCommand } from "./commands/get_news";
import { createGetWeatherCommand } from "./commands/get_weather";
import { createPlanDayCommand } from "./commands/plan_day";
import { createSearchCommand } from "./commands/search";
import {
  NullCalendarProvider,
  type CalendarProvider,
} from "./providers/calendar.provider";
import { NullNewsProvider, type NewsProvider } from "./providers/news.provider";
import {
  NullSearchProvider,
  type SearchProvider,
} from "./providers/search.provider";
import {
  NullTasksProvider,
  type TasksProvider,
} from "./providers/tasks.provider";
import {
  NullTelegramProvider,
  type TelegramProvider,
  type TelegramSendResult,
} from "./providers/telegram.provider";
import {
  NullWeatherProvider,
  type WeatherProvider,
} from "./providers/weather.provider";

export interface LarisaIvanovnaCommandResult {
  text: string;
  payload?: unknown;
  delivery?: TelegramSendResult;
}

export interface LarisaIvanovnaCommand {
  name: string;
  aliases: readonly string[];
  execute(input: unknown): Promise<LarisaIvanovnaCommandResult>;
}

export interface LarisaIvanovnaDependencies {
  calendarProvider?: CalendarProvider;
  tasksProvider?: TasksProvider;
  weatherProvider?: WeatherProvider;
  newsProvider?: NewsProvider;
  searchProvider?: SearchProvider;
  telegramProvider?: TelegramProvider;
  workflows?: LarisaIvanovnaWorkflowBindings;
}

interface LarisaIvanovnaRuntimeDeps {
  calendarProvider: CalendarProvider;
  tasksProvider: TasksProvider;
  weatherProvider: WeatherProvider;
  newsProvider: NewsProvider;
  searchProvider: SearchProvider;
  telegramProvider: TelegramProvider;
}

export interface LarisaIvanovnaWorkflowBindings {
  dayBrief?: DayBriefWorkflow;
}

export function createLarisaIvanovnaCommandRegistry(
  runtimeDeps: LarisaIvanovnaRuntimeDeps,
  workflows: LarisaIvanovnaWorkflowBindings = {},
): Map<string, LarisaIvanovnaCommand> {
  const commands: LarisaIvanovnaCommand[] = [
    createGetDayBriefCommand({
      ...runtimeDeps,
      dayBriefWorkflow: workflows.dayBrief,
    }),
    createCreateEventCommand(runtimeDeps),
    createGetWeatherCommand(runtimeDeps),
    createGetNewsCommand(runtimeDeps),
    createSearchCommand(runtimeDeps),
    createPlanDayCommand(runtimeDeps),
  ];

  const registry = new Map<string, LarisaIvanovnaCommand>();

  for (const command of commands) {
    registry.set(command.name, command);

    for (const alias of command.aliases) {
      registry.set(alias, command);
    }
  }

  return registry;
}

export function createLarisaIvanovnaAgent(dependencies: LarisaIvanovnaDependencies = {}) {
  const runtimeDeps: LarisaIvanovnaRuntimeDeps = {
    calendarProvider: dependencies.calendarProvider ?? new NullCalendarProvider(),
    tasksProvider: dependencies.tasksProvider ?? new NullTasksProvider(),
    weatherProvider: dependencies.weatherProvider ?? new NullWeatherProvider(),
    newsProvider: dependencies.newsProvider ?? new NullNewsProvider(),
    searchProvider: dependencies.searchProvider ?? new NullSearchProvider(),
    telegramProvider: dependencies.telegramProvider ?? new NullTelegramProvider(),
  };

  const workflows = dependencies.workflows ?? {};
  const registry = createLarisaIvanovnaCommandRegistry(runtimeDeps, workflows);
  const executeCommand = async (
    commandName: string,
    input: unknown,
  ): Promise<LarisaIvanovnaCommandResult> => {
    const command = registry.get(commandName);

    if (command === undefined) {
      throw new Error(`Команда ${commandName} не зарегистрирована в агенте Ларисы Ивановны.`);
    }

    return command.execute(input);
  };

  return {
    id: larisaIvanovnaConfig.id,
    name: larisaIvanovnaConfig.displayName,
    role: larisaIvanovnaConfig.role,
    config: larisaIvanovnaConfig,
    policy: larisaIvanovnaPolicy,
    workflows,
    registry,
    execute: executeCommand,

    async dispatchToTelegram(
      commandName: string,
      input: unknown,
      chatId: string,
    ): Promise<LarisaIvanovnaCommandResult> {
      const result = await executeCommand(commandName, input);
      const delivery = await runtimeDeps.telegramProvider.send({
        chatId,
        text: result.text,
        disableWebPagePreview: larisaIvanovnaConfig.telegram.defaultDisableWebPagePreview,
        parseMode: larisaIvanovnaConfig.telegram.defaultParseMode,
      });

      return {
        ...result,
        delivery,
      };
    },
  };
}
