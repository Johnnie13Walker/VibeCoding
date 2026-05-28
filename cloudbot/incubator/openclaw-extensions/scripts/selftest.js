import process from 'node:process';
import { rm } from 'node:fs/promises';
import {
  bindByStartToken,
  createContact,
  getContact,
  prepareInvite,
  sendMessageToContacts,
} from '../contacts/index.js';

async function main() {
  const dbPath = `/tmp/contacts-selftest-${Date.now()}.json`;
  const sent = [];

  const ctx = {
    dbPath,
    ownerId: '111111',
    botUsername: process.env.BOT_USERNAME || 'test_bot',
    inviteTtlDays: Number(process.env.INVITE_TTL_DAYS || 7),
    safeMode: '1',
    sendTelegramMessage: async (chatId, text) => {
      sent.push({ chatId: String(chatId), text: String(text) });
      return { ok: true };
    },
  };

  console.log('=== Contacts selftest ===');
  console.log(`db: ${dbPath}`);

  const created = await createContact({
    display_name: 'Тестовый Контакт',
    tg_username: '@selftest_user',
    note: 'создан в selftest',
  }, ctx);

  console.log(`contact created: id=${created.id} name=${created.display_name}`);

  const invite = await prepareInvite(created.id, ctx);
  console.log(`invite link: ${invite.link}`);

  const bind = await bindByStartToken(
    invite.token,
    { id: 99887766, username: 'selftest_user' },
    '555000111',
    ctx,
  );

  if (!bind.ok) {
    console.log(`bind failed: ${bind.reason}`);
    process.exit(1);
  }
  console.log(`bind ok: chat_id=${bind.contact.chat_id}`);

  const updated = await getContact('@selftest_user', ctx);
  const bindOk = updated && String(updated.chat_id) === '555000111';
  console.log(`chat_id linked: ${bindOk ? 'yes' : 'no'}`);

  const send = await sendMessageToContacts([created.id], 'Привет из selftest', '111111', ctx);
  console.log(`send result: sent=${send.sent.length} skipped=${send.skipped.length} failed=${send.failed.length}`);

  const sendOk = send.sent.length === 1 && sent.length === 1 && sent[0].chatId === '555000111';

  const pass = Boolean(bindOk && sendOk);
  console.log(`SELFTEST RESULT: ${pass ? 'PASS' : 'FAIL'}`);

  await rm(dbPath, { force: true });
  process.exit(pass ? 0 : 1);
}

main().catch(async (err) => {
  console.error('selftest fatal:', err?.message || err);
  process.exit(1);
});
