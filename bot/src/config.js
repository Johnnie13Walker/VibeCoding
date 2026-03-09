import path from "node:path";

export function getConfig(env = process.env) {
  const cwd = process.cwd();
  return {
    bitrixBaseUrl: env.BITRIX_BASE_URL || "",
    bitrixToken: env.BITRIX_TOKEN || "",
    ownerUserId: String(env.TELEGRAM_OWNER_ID || ""),
    adminUserIds: String(env.TELEGRAM_ADMIN_IDS || "")
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean),
    usersCacheFile:
      env.USERS_CACHE_FILE || path.join(cwd, "data", "users-cache.json"),
    usersCacheTtlMs: Number(env.USERS_CACHE_TTL_MS || 24 * 60 * 60 * 1000),
    useFixtureUsers: env.USE_FIXTURE_USERS === "1",
    fixtureUsersFile:
      env.FIXTURE_USERS_FILE || path.join(cwd, "fixtures", "users.json"),
    settingsFile:
      env.SETTINGS_FILE || path.join(cwd, "data", "user-settings.json"),
    notificationLogFile:
      env.NOTIFICATION_LOG_FILE ||
      path.join(cwd, "data", "notification-log.json"),
    notificationLogTtlMs: Number(
      env.NOTIFICATION_LOG_TTL_MS || 7 * 24 * 60 * 60 * 1000
    ),
    useFixtureTasks: env.USE_FIXTURE_TASKS === "1",
    fixtureTasksFile:
      env.FIXTURE_TASKS_FILE || path.join(cwd, "fixtures", "tasks.json"),
    todoProvider: String(env.TODO_PROVIDER || "todoist").toLowerCase(),
    todoToken: env.TODO_TOKEN || ""
  };
}

export function isAdminUser(userId, config) {
  const uid = String(userId || "");
  if (!uid) return false;
  return uid === config.ownerUserId || config.adminUserIds.includes(uid);
}
