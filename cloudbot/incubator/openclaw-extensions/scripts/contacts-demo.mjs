import { rm } from 'node:fs/promises';
import { handleTelegramText } from '../contacts/index.js';

const OWNER_ID = '100500';
const OWNER_CHAT = '777';

async function main() {
  const dbPath = `/tmp/contacts-demo-${Date.now()}.json`;
  const sent = [];
  const ctx = {
    dbPath,
    ownerId: OWNER_ID,
    botUsername: process.env.BOT_USERNAME || 'demo_bot',
    safeMode: '1',
    sendTelegramMessage: async (chatId, text) => {
      sent.push({ chatId: String(chatId), text: String(text) });
      return { ok: true };
    },
  };

  async function say(fromId, chatId, text, username = 'owner') {
    const res = await handleTelegramText({
      text,
      chat: { id: chatId },
      from: { id: fromId, username },
    }, ctx);
    if (res?.reply) {
      console.log(`> ${text}`);
      console.log(res.reply);
      console.log('');
    }
    return res;
  }

  await say(OWNER_ID, OWNER_CHAT, '/contact_add');
  await say(OWNER_ID, OWNER_CHAT, 'Вася');
  await say(OWNER_ID, OWNER_CHAT, '@vasya_demo');
  await say(OWNER_ID, OWNER_CHAT, 'маркетолог, знакомый Димы');

  await say(OWNER_ID, OWNER_CHAT, '/msg Вася привет, давай созвон завтра в 12');
  await say(OWNER_ID, OWNER_CHAT, 'да');

  console.log('sent_count=', sent.length);

  await rm(dbPath, { force: true });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
