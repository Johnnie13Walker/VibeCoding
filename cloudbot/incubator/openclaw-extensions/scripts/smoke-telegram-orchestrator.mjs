import { rm } from 'node:fs/promises';
import { handleIncoming } from '../orchestrator.js';
import { handleTelegramUpdate } from '../contacts/telegram.js';

const OWNER_ID = '100500';
const OWNER_CHAT = '700700';

function update(text, fromId = OWNER_ID, chatId = OWNER_CHAT, username = 'owner') {
  return {
    update_id: Date.now(),
    message: {
      message_id: Math.floor(Math.random() * 100000),
      date: Math.floor(Date.now() / 1000),
      text,
      chat: { id: Number(chatId), type: 'private' },
      from: { id: Number(fromId), username },
    },
  };
}

async function main() {
  const dbPath = `/tmp/orchestrator-smoke-${Date.now()}.json`;
  const replies = [];

  const ctx = {
    dbPath,
    ownerId: OWNER_ID,
    botUsername: 'smoke_bot',
    appVersion: 'smoke',
    env: {
      TELEGRAM_BOT_TOKEN: 'set',
      TELEGRAM_OWNER_ID: OWNER_ID,
      TZ: 'Europe/Moscow',
      MORNING_JOB_ENABLED: '1',
      EVENING_JOB_ENABLED: '1',
    },
    sendReply: async (_chatId, text) => {
      replies.push(String(text || ''));
    },
    sendTelegramMessage: async () => ({ ok: true }),
  };

  const diag = await handleIncoming(
    {
      text: '/diag',
      userId: OWNER_ID,
      chatId: OWNER_CHAT,
      timezone: 'Europe/Moscow',
      metadata: { channel: 'telegram' },
    },
    ctx,
  );

  if (!diag?.handled || !String(diag.reply || '').trim()) {
    throw new Error('diag smoke failed: empty reply');
  }
  console.log('diag ok');

  await handleTelegramUpdate(update('/contact_add'), ctx);
  await handleTelegramUpdate(update('Тест Smoke'), ctx);
  await handleTelegramUpdate(update('@smoke_user'), ctx);
  const added = await handleTelegramUpdate(update('заметка smoke'), ctx);

  if (!added?.handled || !String(added.reply || '').includes('Добавил контакт')) {
    throw new Error('legacy contacts flow failed');
  }

  const list = await handleTelegramUpdate(update('/contact_list'), ctx);
  if (!list?.handled || !String(list.reply || '').includes('Тест Smoke')) {
    throw new Error('contact list failed');
  }

  console.log('SMOKE RESULT: PASS');
  console.log(`replies_total=${replies.length}`);

  await rm(dbPath, { force: true });
}

main().catch((err) => {
  console.error('SMOKE RESULT: FAIL');
  console.error(err?.message || err);
  process.exit(1);
});
