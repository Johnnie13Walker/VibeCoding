import { routeIncoming } from './router.js';

const DEFAULT_TIMEZONE = 'Europe/Moscow';

export function normalizeTelegramInput(update) {
  const message = update?.message || update?.edited_message;
  if (!message?.text || !message?.chat?.id) return null;

  const text = String(message.text || '').trim();
  if (!text) return null;

  return {
    text,
    userId: String(message?.from?.id || ''),
    chatId: String(message.chat.id),
    messageId: String(message.message_id || ''),
    timezone: DEFAULT_TIMEZONE,
    metadata: {
      channel: 'telegram',
      username: message?.from?.username ? String(message.from.username) : '',
      message,
      update,
    },
  };
}

export async function handleIncoming(input, ctx = {}) {
  if (!input?.text || !input?.chatId) {
    return { handled: false, reply: null, reason: 'invalid_input' };
  }

  const normalized = {
    ...input,
    timezone: String(input.timezone || DEFAULT_TIMEZONE),
    metadata: input.metadata || {},
  };

  return routeIncoming(normalized, ctx);
}

