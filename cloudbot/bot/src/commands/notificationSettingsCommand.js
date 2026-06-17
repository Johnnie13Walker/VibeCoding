function normalizeText(text) {
  return String(text || "").trim().toLowerCase();
}

export async function handleNotificationSettingsCommand({
  text,
  userId,
  settingsStore
}) {
  const normalized = normalizeText(text);

  if (normalized === "уведомления") {
    const settings = await settingsStore.getUserSettings(userId);
    return {
      handled: true,
      response: {
        text: settings.quietMode
          ? "Уведомления по времени: выключены (тихий режим включен)."
          : "Уведомления по времени: включены."
      }
    };
  }

  if (normalized === "тест уведомления") {
    return {
      handled: true,
      response: {
        text: "⏰ Через 10 минут: Пример задачи (Демо)\n🔥 Сейчас: Пример задачи (Демо)\nКоротко: делай."
      }
    };
  }

  const quietMatch = normalized.match(/^(?:\/quiet|тихий режим)\s+(on|off)$/);
  if (quietMatch) {
    const enabled = quietMatch[1] === "on";
    const updated = await settingsStore.setQuietMode(userId, enabled);
    return {
      handled: true,
      response: {
        text: updated.quietMode
          ? "Тихий режим включен: уведомления по времени отключены."
          : "Тихий режим выключен: уведомления по времени включены."
      }
    };
  }

  if (normalized === "/quiet" || normalized === "тихий режим") {
    return {
      handled: true,
      response: {
        text: "Используй: /quiet on или /quiet off"
      }
    };
  }

  return { handled: false };
}
