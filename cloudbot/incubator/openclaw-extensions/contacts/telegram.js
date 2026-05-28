import { handleIncoming } from '../orchestrator.js';

function normalizeTelegramInput(update) {
  const message = update?.message || update?.edited_message;
  if (!message?.text || !message?.chat?.id) return null;

  const text = String(message.text || '').trim();
  if (!text) return null;

  return {
    text,
    userId: String(message?.from?.id || ''),
    chatId: String(message.chat.id),
    messageId: String(message.message_id || ''),
    timezone: 'Europe/Moscow',
    metadata: {
      channel: 'telegram',
      username: message?.from?.username ? String(message.from.username) : '',
      message,
      update,
    },
  };
}

export async function handleTelegramUpdate(update, ctx = {}) {
  const incoming = normalizeTelegramInput(update);
  if (!incoming) return { handled: false };

  const result = await handleIncoming(incoming, ctx);
  if (!result?.handled || !result.reply) return result;

  if (typeof ctx.sendReply === 'function') {
    await ctx.sendReply(incoming.chatId, result.reply);
  }

  return result;
}
