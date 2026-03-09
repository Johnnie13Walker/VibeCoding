import { forceRefreshUsersCache } from "../storage/usersCache.js";
import { isAdminUser } from "../config.js";

function formatMsk(isoString) {
  const dt = new Date(isoString);
  const fmt = new Intl.DateTimeFormat("ru-RU", {
    timeZone: "Europe/Moscow",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
  return `${fmt.format(dt)} МСК`;
}

export async function handleSyncUsersCommand({ text, userId, config, provider }) {
  const command = String(text || "").trim().toLowerCase();
  const isSyncCommand = command === "/sync_users" || command === "обнови сотрудников";
  if (!isSyncCommand) return null;

  if (!isAdminUser(userId, config)) {
    return { text: "Команда доступна только владельцу/админу." };
  }

  const refreshed = await forceRefreshUsersCache({
    cacheFile: config.usersCacheFile,
    provider
  });

  if (refreshed.status === "not_configured") {
    return { text: "Bitrix доступ не настроен: кэш сотрудников не обновлен." };
  }

  if (refreshed.status !== "ok") {
    return { text: "Не удалось обновить кэш сотрудников. Проверь логи интеграции Bitrix." };
  }

  return {
    text: `Кэш сотрудников обновлен: ${refreshed.users.length} активных, метка ${formatMsk(
      refreshed.updatedAt
    )}.`
  };
}
