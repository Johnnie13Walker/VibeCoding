import { getConfig } from "./config.js";
import { createBitrixUsersProvider } from "./providers/bitrixUsersProvider.js";
import { createTodoProvider } from "./providers/todoProviderFactory.js";
import { createPeopleResolver } from "./services/peopleResolver.js";
import { createNotificationLogStore } from "./storage/notificationLogStore.js";
import { createSettingsStore } from "./storage/settingsStore.js";
import { handleSyncUsersCommand } from "./commands/syncUsersCommand.js";
import { handleNotificationSettingsCommand } from "./commands/notificationSettingsCommand.js";
import {
  handleMeetCreateAttendee,
  handlePickAttendee
} from "./workflows/meetCreateWorkflow.js";
import { createTaskTimeNotificationsJob } from "./workflows/taskNotificationsWorkflow.js";
import { createEveningReminderJob } from "./workflows/eveningReminderWorkflow.js";
import { buildSchedulerJobs } from "./scheduler/jobs.js";

export function createBotModules(env = process.env, logger = console, overrides = {}) {
  const config = getConfig(env);
  const provider = createBitrixUsersProvider({ config, logger });
  const todoProvider = overrides.todoProvider || createTodoProvider({ config, logger });
  const settingsStore =
    overrides.settingsStore || createSettingsStore({ filePath: config.settingsFile });
  const notificationLogStore =
    overrides.notificationLogStore ||
    createNotificationLogStore({
      filePath: config.notificationLogFile,
      ttlMs: config.notificationLogTtlMs
    });

  const resolver = createPeopleResolver({
    provider,
    cacheFile: config.usersCacheFile,
    ttlMs: config.usersCacheTtlMs,
    logger
  });

  const taskTimeNotificationsJob = createTaskTimeNotificationsJob({
    todoProvider,
    settingsStore,
    notificationLogStore,
    logger,
    now: overrides.now || (() => Date.now())
  });

  const eveningReminderJob = createEveningReminderJob({
    todoProvider,
    logger,
    now: overrides.now || (() => Date.now())
  });

  const schedulerJobs = buildSchedulerJobs({
    taskTimeNotificationsJob,
    eveningReminderJob
  });

  return {
    config,
    provider,
    todoProvider,
    settingsStore,
    notificationLogStore,
    schedulerJobs,
    taskTimeNotificationsJob,
    eveningReminderJob,
    resolver,
    handleSyncUsersCommand: (args) =>
      handleSyncUsersCommand({ ...args, config, provider }),
    handleNotificationSettingsCommand: (args) =>
      handleNotificationSettingsCommand({ ...args, settingsStore }),
    handleMeetCreateAttendee: (args) => handleMeetCreateAttendee({ ...args, resolver }),
    handlePickAttendee
  };
}
