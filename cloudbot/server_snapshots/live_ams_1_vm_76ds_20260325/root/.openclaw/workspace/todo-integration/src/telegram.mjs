export async function sendTelegramMessage(botToken, chatId, text, options = {}) {
  const url = `https://api.telegram.org/bot${botToken}/sendMessage`;
  const payload = new URLSearchParams({
    chat_id: String(chatId),
    text,
    parse_mode: options.parseMode || "HTML",
    disable_web_page_preview: String(options.disableWebPagePreview ?? true)
  });

  if (options.replyMarkup) {
    payload.set("reply_markup", JSON.stringify(options.replyMarkup));
  }

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: payload.toString()
  });
  const data = await res.json();
  if (!res.ok || !data?.ok) {
    throw new Error(`Telegram sendMessage failed: ${JSON.stringify(data).slice(0, 400)}`);
  }
  return data;
}
