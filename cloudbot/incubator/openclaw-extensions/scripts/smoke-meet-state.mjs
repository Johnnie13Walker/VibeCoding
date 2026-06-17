import { readFile, rm } from 'node:fs/promises';
import { handleIncoming } from '../orchestrator.js';

const USER_ID = '100500';
const CHAT_ID = '700700';

function hasStateForUser(rawDb, userId) {
  const db = JSON.parse(rawDb);
  return db?.states?.[`u:${userId}`] || null;
}

async function call(text, ctx) {
  return handleIncoming(
    {
      text,
      userId: USER_ID,
      chatId: CHAT_ID,
      timezone: 'Europe/Moscow',
      metadata: { channel: 'telegram' },
    },
    ctx,
  );
}

async function main() {
  const stamp = Date.now();
  const statePath = `/tmp/smoke-state-${stamp}.json`;
  const dbPath = `/tmp/smoke-contacts-${stamp}.json`;

  const ctx = {
    statePath,
    dbPath,
    env: {
      TZ: 'Europe/Moscow',
      TELEGRAM_BOT_TOKEN: 'set',
      TELEGRAM_OWNER_ID: USER_ID,
      ALLOW_CALENDAR_MOCK: '1',
    },
  };

  const r1 = await call('создай встречу с Петром', ctx);
  if (!r1?.handled || !String(r1.reply || '').toLowerCase().includes('дат')) {
    throw new Error(`input1 failed: ${r1?.reply || 'empty reply'}`);
  }

  const stateAfter1 = hasStateForUser(await readFile(statePath, 'utf8'), USER_ID);
  if (!stateAfter1 || stateAfter1.activeFlow !== 'meeting_create' || stateAfter1.step !== 'ask_date') {
    throw new Error('state after input1 is invalid');
  }

  const r2 = await call('завтра', ctx);
  if (!r2?.handled || !String(r2.reply || '').toLowerCase().includes('восколько') && !String(r2.reply || '').toLowerCase().includes('во сколько')) {
    throw new Error(`input2 failed: ${r2?.reply || 'empty reply'}`);
  }

  const stateAfter2 = hasStateForUser(await readFile(statePath, 'utf8'), USER_ID);
  if (!stateAfter2 || stateAfter2.activeFlow !== 'meeting_create' || stateAfter2.step !== 'ask_time') {
    throw new Error('state after input2 is invalid');
  }

  const r3 = await call('16:00', ctx);
  if (!r3?.handled || !String(r3.reply || '').toLowerCase().includes('встреча создана')) {
    throw new Error(`input3 failed: ${r3?.reply || 'empty reply'}`);
  }

  const finalStateRaw = await readFile(statePath, 'utf8');
  const finalState = hasStateForUser(finalStateRaw, USER_ID);
  if (finalState) {
    throw new Error('state not cleared after final step');
  }

  console.log('SMOKE MEET STATE: PASS');

  await rm(statePath, { force: true });
  await rm(dbPath, { force: true });
}

main().catch((err) => {
  console.error('SMOKE MEET STATE: FAIL');
  console.error(err?.message || err);
  process.exit(1);
});
