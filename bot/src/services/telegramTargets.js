function splitCsv(raw) {
  return String(raw || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

export function parseTelegramTargets(raw) {
  const targets = {};

  for (const entry of splitCsv(raw)) {
    const separatorIndex = entry.indexOf("=");
    if (separatorIndex <= 0 || separatorIndex >= entry.length - 1) continue;

    const alias = entry.slice(0, separatorIndex).trim().toLowerCase();
    const chatId = entry.slice(separatorIndex + 1).trim();
    if (!alias || !chatId) continue;

    targets[alias] = chatId;
  }

  return targets;
}

export function buildTelegramRoutingConfig(env = process.env) {
  const defaultChatId = String(env.TELEGRAM_CHAT_ID || "").trim();
  const targets = parseTelegramTargets(env.TELEGRAM_TARGETS);
  const allowedChatIds = new Set(splitCsv(env.TELEGRAM_ALLOWED_CHAT_IDS));

  if (defaultChatId) {
    allowedChatIds.add(defaultChatId);
  }

  for (const chatId of Object.values(targets)) {
    allowedChatIds.add(String(chatId).trim());
  }

  return {
    defaultChatId,
    targets,
    allowedChatIds
  };
}

export function resolveTelegramChatId({
  chatId,
  chatAlias,
  defaultChatId = "",
  targets = {},
  allowedChatIds = new Set()
} = {}) {
  const explicitChatId = String(chatId || "").trim();
  const normalizedAlias = String(chatAlias || "").trim().toLowerCase();

  if (normalizedAlias && !targets[normalizedAlias]) {
    throw new Error(`Неизвестный Telegram chat alias: ${normalizedAlias}`);
  }

  const resolvedChatId =
    explicitChatId ||
    (normalizedAlias ? String(targets[normalizedAlias] || "").trim() : "") ||
    String(defaultChatId || "").trim();

  if (!resolvedChatId) return "";

  if (allowedChatIds.size > 0 && !allowedChatIds.has(resolvedChatId)) {
    throw new Error(`Telegram chatId не разрешен: ${resolvedChatId}`);
  }

  return resolvedChatId;
}
