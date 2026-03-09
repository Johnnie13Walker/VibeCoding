function resolveTelegramConfig(env = process.env) {
  return {
    botToken: String(env.TELEGRAM_BOT_TOKEN || "").trim(),
    apiBaseUrl: String(env.TELEGRAM_API_BASE_URL || "https://api.telegram.org").trim(),
    defaultChatId: String(env.TELEGRAM_CHAT_ID || "").trim(),
    dryRun: env.TELEGRAM_DRY_RUN === "1"
  };
}

function formatOutbound(message) {
  return String(message?.text || "").trim();
}

export function createTelegramTransport({ env = process.env, logger = console } = {}) {
  const cfg = resolveTelegramConfig(env);

  async function sendViaApi({ chatId, text }) {
    const url = `${cfg.apiBaseUrl}/bot${cfg.botToken}/sendMessage`;
    const response = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text,
        disable_web_page_preview: true
      })
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload?.ok === false) {
      const description = payload?.description || `HTTP ${response.status}`;
      throw new Error(`Telegram sendMessage failed: ${description}`);
    }

    return payload;
  }

  return {
    async send(message) {
      const text = formatOutbound(message);
      if (!text) return { status: "skipped_empty" };

      const chatId = String(message?.chatId || cfg.defaultChatId || "").trim();
      if (!chatId) throw new Error("Не задан chatId для отправки в Telegram");

      if (cfg.dryRun || !cfg.botToken) {
        logger.info?.(`[telegram dry-run] chat=${chatId} trigger=${message?.triggerType || "unknown"}`);
        logger.info?.(text);
        return { status: "dry_run", chatId, text };
      }

      const payload = await sendViaApi({ chatId, text });
      return { status: "sent", chatId, payload };
    }
  };
}
