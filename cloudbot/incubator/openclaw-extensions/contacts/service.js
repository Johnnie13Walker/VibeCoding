import { withDb } from './storage.js';
import {
  genToken,
  hashToken,
  maskToken,
  normalizeText,
  normalizeUsername,
  nowIso,
  parseQuickAdd,
  scoreContact,
  usernameToLink,
} from './utils.js';

const MAX_PAGE_SIZE = 10;

function parseOwnerId(value) {
  const id = String(value || '').trim();
  if (!/^\d+$/.test(id)) return null;
  return id;
}

function getOwnerId(ctx) {
  return parseOwnerId(ctx.ownerId || process.env.TELEGRAM_OWNER_ID);
}

function isOwner(userId, ctx) {
  const ownerId = getOwnerId(ctx);
  return ownerId && String(userId) === ownerId;
}

function auditPush(db, event, details = {}) {
  const row = { at: nowIso(), event, ...details };
  db.audit.push(row);
  if (db.audit.length > 1000) db.audit.splice(0, db.audit.length - 1000);
  try {
    // Без утечки токенов: в аудит уже кладутся только hash/masked значения.
    console.log(`[contacts:audit] ${event}`, JSON.stringify(row));
  } catch {
    // ignore logging failures
  }
}

function findContactById(db, id) {
  return db.contacts.find((c) => c.id === id) || null;
}

function contactCard(contact) {
  return [
    `id: ${contact.id}`,
    `имя: ${contact.display_name}`,
    `username: ${contact.tg_username || '-'}`,
    `ссылка: ${contact.tg_link || '-'}`,
    `chat_id: ${contact.chat_id || '-'}`,
    `заметка: ${contact.note || '-'}`,
    `обновлён: ${contact.updated_at}`,
  ].join('\n');
}

function searchContactsInternal(db, query) {
  const q = normalizeText(query);
  const withScore = db.contacts
    .map((c) => ({ contact: c, score: scoreContact(c, q) }))
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score || a.contact.id - b.contact.id);
  return withScore;
}

function exactLookup(db, key) {
  const q = normalizeText(key);
  const qNoAt = q.replace(/^@/, '');
  if (!q) return null;
  return db.contacts.find((c) => {
    if (normalizeText(c.display_name) === q) return true;
    const u = normalizeText(c.tg_username);
    if (u === q || u.replace(/^@/, '') === qNoAt) return true;
    return false;
  }) || null;
}

function ensureInvite(db, contactId, ttlDays) {
  const token = genToken();
  const tokenHash = hashToken(token);
  const now = Date.now();
  const expiresAt = new Date(now + ttlDays * 24 * 60 * 60 * 1000).toISOString();
  db.invites.push({
    token_hash: tokenHash,
    contact_id: contactId,
    expires_at: expiresAt,
    used_at: null,
    created_at: nowIso(),
  });
  return { token, tokenHash, expiresAt };
}

function getInviteTtlDays(ctx) {
  const raw = Number(ctx.inviteTtlDays || process.env.INVITE_TTL_DAYS || 7);
  if (!Number.isFinite(raw) || raw <= 0) return 7;
  return Math.round(raw);
}

function getBotUsername(ctx) {
  const user = String(ctx.botUsername || process.env.BOT_USERNAME || '').trim().replace(/^@/, '');
  return user || 'your_bot';
}

function buildInviteLink(ctx, token) {
  return `https://t.me/${getBotUsername(ctx)}?start=${token}`;
}

async function sendOneMessage(targetChatId, text, ctx) {
  if (typeof ctx.sendTelegramMessage === 'function') {
    return ctx.sendTelegramMessage(targetChatId, text);
  }

  const botToken = String(ctx.botToken || process.env.TELEGRAM_BOT_TOKEN || '').trim();
  if (!botToken) {
    throw new Error('TELEGRAM_BOT_TOKEN не задан');
  }

  const url = `https://api.telegram.org/bot${botToken}/sendMessage`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: targetChatId, text }),
  });
  const body = await res.text();
  if (!res.ok) {
    throw new Error(`Telegram API ${res.status}: ${body.slice(0, 200)}`);
  }
  return body;
}

export async function createContact(input, ctx) {
  return withDb(ctx.dbPath, async (db) => {
    const displayName = String(input.display_name || '').trim();
    if (!displayName) throw new Error('display_name обязателен');

    const tgUsername = normalizeUsername(input.tg_username || input.tg_link || null);
    const tgLink = input.tg_link ? String(input.tg_link).trim() : usernameToLink(tgUsername);

    const now = nowIso();
    const contact = {
      id: db.seq.contactId++,
      display_name: displayName,
      tg_username: tgUsername,
      tg_link: tgLink || null,
      chat_id: input.chat_id || null,
      note: input.note ? String(input.note).trim() : null,
      created_at: now,
      updated_at: now,
    };

    db.contacts.push(contact);
    auditPush(db, 'contact_added', {
      contact_id: contact.id,
      display_name: contact.display_name,
      tg_username: contact.tg_username,
    });
    return contact;
  });
}

export async function listContacts(page, ctx) {
  return withDb(ctx.dbPath, async (db) => {
    const p = Number(page) > 0 ? Number(page) : 1;
    const pageSize = MAX_PAGE_SIZE;
    const offset = (p - 1) * pageSize;
    const items = [...db.contacts].sort((a, b) => a.id - b.id).slice(offset, offset + pageSize);
    return { page: p, pageSize, total: db.contacts.length, items };
  });
}

export async function findContacts(query, ctx) {
  return withDb(ctx.dbPath, async (db) => searchContactsInternal(db, query));
}

export async function getContact(query, ctx) {
  return withDb(ctx.dbPath, async (db) => exactLookup(db, query));
}

export async function deleteContact(query, ctx) {
  return withDb(ctx.dbPath, async (db) => {
    const matched = exactLookup(db, query);
    if (!matched) return null;
    db.contacts = db.contacts.filter((x) => x.id !== matched.id);
    auditPush(db, 'contact_deleted', { contact_id: matched.id, display_name: matched.display_name });
    return matched;
  });
}

export async function updateContact(query, patch, ctx) {
  return withDb(ctx.dbPath, async (db) => {
    const matched = exactLookup(db, query);
    if (!matched) return null;

    if (patch.display_name !== undefined) matched.display_name = String(patch.display_name || '').trim() || matched.display_name;
    if (patch.tg_username !== undefined || patch.tg_link !== undefined) {
      const username = normalizeUsername(patch.tg_username || patch.tg_link || matched.tg_username);
      matched.tg_username = username;
      matched.tg_link = patch.tg_link !== undefined
        ? (String(patch.tg_link || '').trim() || usernameToLink(username))
        : (matched.tg_link || usernameToLink(username));
    }
    if (patch.note !== undefined) matched.note = patch.note ? String(patch.note).trim() : null;
    if (patch.chat_id !== undefined) matched.chat_id = patch.chat_id || null;

    matched.updated_at = nowIso();
    auditPush(db, 'contact_updated', {
      contact_id: matched.id,
      display_name: matched.display_name,
    });

    return matched;
  });
}

function resolveRecipientsInDb(db, recipientsText) {
  const rawParts = String(recipientsText || '').split(',').map((x) => x.trim()).filter(Boolean);
  if (!rawParts.length) return { ok: false, reason: 'empty_recipients' };

  const found = [];
  const missing = [];
  const ambiguous = [];

  for (const part of rawParts) {
    const exact = exactLookup(db, part);
    if (exact) {
      found.push({ query: part, contact: exact, score: 150 });
      continue;
    }

    const fuzzy = searchContactsInternal(db, part);
    if (!fuzzy.length) {
      missing.push(part);
      continue;
    }
    if (fuzzy.length > 1 && fuzzy[0].score - fuzzy[1].score < 8) {
      ambiguous.push({ query: part, options: fuzzy.slice(0, 3).map((x) => x.contact) });
      continue;
    }
    found.push({ query: part, contact: fuzzy[0].contact, score: fuzzy[0].score });
  }

  if (missing.length || ambiguous.length) {
    return { ok: false, missing, ambiguous };
  }

  const uniq = [];
  const seen = new Set();
  for (const item of found) {
    if (seen.has(item.contact.id)) continue;
    seen.add(item.contact.id);
    uniq.push(item.contact);
  }
  return { ok: true, contacts: uniq };
}

function parseMsgInputInDb(db, rawInput) {
  const text = String(rawInput || '').trim();
  if (!text) return { ok: false, reason: 'empty' };

  const words = text.split(/\s+/).filter(Boolean);
  if (words.length < 2) return { ok: false, reason: 'too_short' };

  const candidates = [];
  const maxSplit = Math.min(words.length - 1, 10);
  for (let i = 1; i <= maxSplit; i += 1) {
    const left = words.slice(0, i).join(' ').trim();
    const right = words.slice(i).join(' ').trim();
    if (!left || !right) continue;
    const resolved = resolveRecipientsInDb(db, left);
    if (!resolved.ok) continue;
    candidates.push({ recipients: resolved.contacts, message: right, split: i });
  }

  if (!candidates.length) {
    const one = resolveRecipientsInDb(db, words[0]);
    if (one.ok) {
      return {
        ok: true,
        contacts: one.contacts,
        message: words.slice(1).join(' '),
      };
    }

    if (Array.isArray(one.ambiguous) && one.ambiguous.length) {
      return {
        ok: false,
        reason: 'ambiguous',
        ambiguous: one.ambiguous.map((x) => ({
          query: x.query,
          options: x.options.map((c) => renderContactShort(c)),
        })),
      };
    }

    const miss = one.missing?.[0] || words[0];
    const hints = searchContactsInternal(db, miss).slice(0, 5).map((x) => renderContactShort(x.contact));
    return { ok: false, reason: 'recipients_not_found', missing: one.missing || [miss], hints };
  }

  candidates.sort((a, b) => b.recipients.length - a.recipients.length || a.split - b.split);
  return {
    ok: true,
    contacts: candidates[0].recipients,
    message: candidates[0].message,
  };
}

export async function parseMsgInput(rawInput, ctx) {
  return withDb(ctx.dbPath, async (db) => parseMsgInputInDb(db, rawInput));
}

export async function prepareInvite(contactId, ctx) {
  return withDb(ctx.dbPath, async (db) => {
    const contact = findContactById(db, contactId);
    if (!contact) throw new Error('Контакт не найден');

    const ttlDays = getInviteTtlDays(ctx);
    const { token, tokenHash, expiresAt } = ensureInvite(db, contact.id, ttlDays);
    auditPush(db, 'invite_generated', {
      contact_id: contact.id,
      token_hash_prefix: tokenHash.slice(0, 8),
      expires_at: expiresAt,
      token_masked: maskToken(token),
    });

    return {
      token,
      link: buildInviteLink(ctx, token),
      expires_at: expiresAt,
      contact,
    };
  });
}

export async function bindByStartToken(token, telegramUser, chatId, ctx) {
  return withDb(ctx.dbPath, async (db) => {
    const tokenHash = hashToken(token);
    const invite = db.invites.find((x) => x.token_hash === tokenHash);
    if (!invite) return { ok: false, reason: 'not_found' };
    if (invite.used_at) return { ok: false, reason: 'already_used' };
    if (new Date(invite.expires_at).getTime() < Date.now()) return { ok: false, reason: 'expired' };

    const contact = findContactById(db, invite.contact_id);
    if (!contact) return { ok: false, reason: 'contact_missing' };

    contact.chat_id = String(chatId);
    if (!contact.tg_username && telegramUser?.username) {
      contact.tg_username = `@${String(telegramUser.username).toLowerCase()}`;
      contact.tg_link = usernameToLink(contact.tg_username);
    }
    contact.updated_at = nowIso();
    invite.used_at = nowIso();

    auditPush(db, 'invite_used', {
      contact_id: contact.id,
      token_hash_prefix: tokenHash.slice(0, 8),
      chat_id: String(chatId),
    });

    return { ok: true, contact };
  });
}

async function sendMessageToContactsWithDb(db, contactIds, messageText, actor, ctx) {
  const safeMode = String(ctx.safeMode ?? process.env.SAFE_MODE ?? '1') === '1';
  const sent = [];
  const skipped = [];
  const failed = [];

  for (const id of contactIds) {
    const contact = findContactById(db, id);
    if (!contact) {
      failed.push({ id, reason: 'contact_not_found' });
      continue;
    }

    if (!contact.chat_id) {
      const ttlDays = getInviteTtlDays(ctx);
      const { token, expiresAt } = ensureInvite(db, contact.id, ttlDays);
      skipped.push({
        contact,
        reason: 'no_chat_id',
        invite_link: buildInviteLink(ctx, token),
        expires_at: expiresAt,
      });
      auditPush(db, 'message_skipped_no_chat', {
        contact_id: contact.id,
        actor_id: String(actor || ''),
        token_masked: maskToken(token),
      });
      continue;
    }

    if (safeMode && ctx.disableRealSendInSafeMode) {
      skipped.push({ contact, reason: 'safe_mode_send_blocked' });
      auditPush(db, 'message_skipped_safe_mode', {
        contact_id: contact.id,
        actor_id: String(actor || ''),
      });
      continue;
    }

    try {
      await sendOneMessage(contact.chat_id, messageText, ctx);
      sent.push({ contact });
      auditPush(db, 'message_sent', {
        contact_id: contact.id,
        actor_id: String(actor || ''),
        chat_id: contact.chat_id,
      });
    } catch (err) {
      failed.push({ contact, reason: err?.message || 'send_failed' });
      auditPush(db, 'message_failed', {
        contact_id: contact.id,
        actor_id: String(actor || ''),
        error: String(err?.message || err || 'unknown'),
      });
    }
  }

  return { sent, skipped, failed };
}

export async function sendMessageToContacts(contactIds, messageText, actor, ctx) {
  if (!Array.isArray(contactIds) || !contactIds.length) {
    return { sent: [], skipped: [], failed: [] };
  }
  return withDb(ctx.dbPath, async (db) => sendMessageToContactsWithDb(db, contactIds, messageText, actor, ctx));
}

function setSession(db, chatId, session) {
  db.sessions[String(chatId)] = session;
}

function getSession(db, chatId) {
  return db.sessions[String(chatId)] || null;
}

function clearSession(db, chatId) {
  delete db.sessions[String(chatId)];
}

function renderContactShort(contact) {
  return `${contact.display_name} ${contact.tg_username || ''}`.trim();
}

async function handleAddFlow(db, chatId, text, ctx) {
  const s = getSession(db, chatId) || { flow: 'contact_add', step: 'name', draft: {} };

  if (s.step === 'name') {
    s.draft.display_name = String(text).trim();
    s.step = 'username';
    setSession(db, chatId, s);
    return 'Укажи telegram username (например @vasya) или ссылку t.me/...';
  }

  if (s.step === 'username') {
    const username = normalizeUsername(text);
    if (!username) return 'Не понял username/ссылку. Пример: @vasya или https://t.me/vasya';
    s.draft.tg_username = username;
    s.draft.tg_link = usernameToLink(username);
    s.step = 'note';
    setSession(db, chatId, s);
    return 'Добавить заметку/контекст? (или напиши "-" чтобы пропустить)';
  }

  if (s.step === 'note') {
    const note = String(text || '').trim();
    const contact = {
      id: db.seq.contactId++,
      display_name: s.draft.display_name,
      tg_username: s.draft.tg_username || null,
      tg_link: s.draft.tg_link || null,
      chat_id: null,
      note: note === '-' ? null : note,
      created_at: nowIso(),
      updated_at: nowIso(),
    };
    db.contacts.push(contact);
    clearSession(db, chatId);
    auditPush(db, 'contact_added', {
      contact_id: contact.id,
      display_name: contact.display_name,
      tg_username: contact.tg_username,
    });
    return `Добавил контакт: ${renderContactShort(contact)}`;
  }

  clearSession(db, chatId);
  return 'Сбросил диалог добавления. Запусти /contact_add снова.';
}

async function handleUpdateFlow(db, chatId, text) {
  const s = getSession(db, chatId);
  if (!s || s.flow !== 'contact_update') return null;

  const contact = findContactById(db, s.contact_id);
  if (!contact) {
    clearSession(db, chatId);
    return 'Контакт не найден, диалог остановлен.';
  }

  if (s.step === 'field') {
    const field = normalizeText(text);
    if (!['имя', 'username', 'ссылка', 'заметка', 'chat_id'].includes(field)) {
      return 'Выбери поле: имя | username | ссылка | заметка | chat_id';
    }
    s.field = field;
    s.step = 'value';
    setSession(db, chatId, s);
    return `Новое значение для поля "${field}":`;
  }

  if (s.step === 'value') {
    const value = String(text || '').trim();
    if (s.field === 'имя') contact.display_name = value || contact.display_name;
    if (s.field === 'username') {
      const username = normalizeUsername(value);
      if (!username) return 'Некорректный username.';
      contact.tg_username = username;
      contact.tg_link = usernameToLink(username);
    }
    if (s.field === 'ссылка') contact.tg_link = value || null;
    if (s.field === 'заметка') contact.note = value === '-' ? null : value;
    if (s.field === 'chat_id') contact.chat_id = value === '-' ? null : value;

    contact.updated_at = nowIso();
    clearSession(db, chatId);
    auditPush(db, 'contact_updated', {
      contact_id: contact.id,
      field: s.field,
    });
    return `Обновил контакт:\n${contactCard(contact)}`;
  }

  clearSession(db, chatId);
  return 'Диалог обновления остановлен.';
}

async function handleMsgConfirm(db, chatId, text, userId, ctx) {
  const s = getSession(db, chatId);
  if (!s || s.flow !== 'msg_confirm') return null;

  const ans = normalizeText(text);
  if (ans !== 'да' && ans !== 'нет') {
    return 'Подтверди отправку: "да" или "нет"';
  }

  if (ans === 'нет') {
    clearSession(db, chatId);
    return 'Отменил отправку.';
  }

  clearSession(db, chatId);
  const sendResult = await sendMessageToContactsWithDb(db, s.contact_ids, s.message_text, userId, ctx);

  const lines = [];
  lines.push('Результат отправки:');
  lines.push(`- отправлено: ${sendResult.sent.length}`);
  lines.push(`- без chat_id: ${sendResult.skipped.filter((x) => x.reason === 'no_chat_id').length}`);
  lines.push(`- ошибки: ${sendResult.failed.length}`);

  for (const sk of sendResult.skipped) {
    if (sk.reason !== 'no_chat_id') continue;
    lines.push('');
    lines.push(`Не могу написать первым контакту ${renderContactShort(sk.contact)}.`);
    lines.push('Попроси человека нажать Start:');
    lines.push(sk.invite_link);
    lines.push('Текст для пересылки:');
    lines.push(s.message_text);
  }

  for (const f of sendResult.failed) {
    if (!f.contact) continue;
    lines.push(`Ошибка отправки ${renderContactShort(f.contact)}: ${f.reason}`);
  }

  return lines.join('\n');
}

function formatList(items, page, total) {
  const lines = [`Контакты (стр. ${page}, всего ${total}):`];
  if (!items.length) {
    lines.push('Список пуст.');
    return lines.join('\n');
  }
  for (const c of items) {
    lines.push(`- ${c.display_name} | ${c.tg_username || '-'} | chat_id=${c.chat_id || '-'}`);
  }
  return lines.join('\n');
}

function parseCommand(text) {
  const m = String(text || '').trim().match(/^\/(\w+)(?:\s+([\s\S]+))?$/);
  if (!m) return null;
  return { name: m[1], arg: (m[2] || '').trim() };
}

export async function handleTelegramText(message, ctx) {
  const text = String(message?.text || '').trim();
  const chatId = String(message?.chat?.id || '');
  const userId = String(message?.from?.id || '');

  if (!text || !chatId) return { handled: false, reply: null };

  const owner = isOwner(userId, ctx);

  if (!owner) {
    // MIXED-LOGIC: handler одновременно делает ACL, handshake /start и формирование пользовательского ответа.
    const cmd = parseCommand(text);
    if (cmd?.name === 'start') {
      const token = cmd.arg;
      if (!token) {
        return { handled: true, reply: 'Привет. Для привязки контакта открой ссылку-приглашение от владельца бота.' };
      }
      const bound = await bindByStartToken(token, message.from, chatId, ctx);
      if (!bound.ok) {
        if (bound.reason === 'expired') return { handled: true, reply: 'Ссылка истекла. Попросите новую у владельца.' };
        if (bound.reason === 'already_used') return { handled: true, reply: 'Эта ссылка уже использована.' };
        return { handled: true, reply: 'Неверная ссылка приглашения.' };
      }
      return { handled: true, reply: `Ок, вы в контактах как ${bound.contact.display_name}.` };
    }
    return { handled: true, reply: 'Доступ ограничен. Обратитесь к владельцу бота.' };
  }

  return withDb(ctx.dbPath, async (db) => {
    // MIXED-LOGIC: в одном месте совмещены parsing intent, управление state-machine и прямые CRUD-операции.
    const pendingAdd = getSession(db, chatId)?.flow === 'contact_add';
    const pendingUpd = getSession(db, chatId)?.flow === 'contact_update';
    const pendingMsg = getSession(db, chatId)?.flow === 'msg_confirm';

    if (pendingMsg) {
      return { handled: true, reply: await handleMsgConfirm(db, chatId, text, userId, ctx) };
    }
    if (pendingAdd && !text.startsWith('/')) {
      return { handled: true, reply: await handleAddFlow(db, chatId, text, ctx) };
    }
    if (pendingUpd && !text.startsWith('/')) {
      return { handled: true, reply: await handleUpdateFlow(db, chatId, text) };
    }

    const quick = parseQuickAdd(text);
    if (quick) {
      if (!quick.confident) {
        return {
          handled: true,
          reply: 'Не до конца понял быстрый формат. Пример: добавь контакт: Вася @vasya маркетолог, знакомый Димы',
        };
      }
      const now = nowIso();
      const contact = {
        id: db.seq.contactId++,
        display_name: quick.display_name,
        tg_username: quick.tg_username,
        tg_link: quick.tg_link,
        chat_id: null,
        note: quick.note,
        created_at: now,
        updated_at: now,
      };
      db.contacts.push(contact);
      auditPush(db, 'contact_added_quick', {
        contact_id: contact.id,
        display_name: contact.display_name,
      });
      return { handled: true, reply: `Добавил контакт: ${renderContactShort(contact)}` };
    }

    const cmd = parseCommand(text);
    if (!cmd) return { handled: false, reply: null };

    if (cmd.name === 'contact_add') {
      setSession(db, chatId, { flow: 'contact_add', step: 'name', draft: {} });
      return { handled: true, reply: 'Как зовут / как записать контакт?' };
    }

    if (cmd.name === 'contact_list') {
      const page = Number(cmd.arg || '1') || 1;
      const p = page > 0 ? page : 1;
      const offset = (p - 1) * MAX_PAGE_SIZE;
      const items = [...db.contacts].sort((a, b) => a.id - b.id).slice(offset, offset + MAX_PAGE_SIZE);
      return { handled: true, reply: formatList(items, p, db.contacts.length) };
    }

    if (cmd.name === 'contact_find') {
      if (!cmd.arg) return { handled: true, reply: 'Использование: /contact_find <запрос>' };
      const found = searchContactsInternal(db, cmd.arg).slice(0, 10);
      if (!found.length) return { handled: true, reply: 'Ничего не найдено.' };
      return {
        handled: true,
        reply: `Найдено:\n${found.map((x) => `- ${x.contact.display_name} (${x.contact.tg_username || '-'}) [score=${x.score}]`).join('\n')}`,
      };
    }

    if (cmd.name === 'contact_show') {
      if (!cmd.arg) return { handled: true, reply: 'Использование: /contact_show <имя или @username>' };
      const one = exactLookup(db, cmd.arg);
      if (!one) return { handled: true, reply: 'Контакт не найден.' };
      return { handled: true, reply: contactCard(one) };
    }

    if (cmd.name === 'contact_delete') {
      if (!cmd.arg) return { handled: true, reply: 'Использование: /contact_delete <имя или @username>' };
      const one = exactLookup(db, cmd.arg);
      if (!one) return { handled: true, reply: 'Контакт не найден.' };
      db.contacts = db.contacts.filter((x) => x.id !== one.id);
      auditPush(db, 'contact_deleted', { contact_id: one.id, display_name: one.display_name });
      return { handled: true, reply: `Удалил контакт: ${renderContactShort(one)}` };
    }

    if (cmd.name === 'contact_update') {
      if (!cmd.arg) return { handled: true, reply: 'Использование: /contact_update <имя или @username>' };
      const one = exactLookup(db, cmd.arg);
      if (!one) return { handled: true, reply: 'Контакт не найден.' };
      setSession(db, chatId, { flow: 'contact_update', step: 'field', contact_id: one.id });
      return { handled: true, reply: 'Какое поле изменить? имя | username | ссылка | заметка | chat_id' };
    }

    if (cmd.name === 'msg') {
      if (!cmd.arg) return { handled: true, reply: 'Использование: /msg <кому> <текст>' };
      const parsed = parseMsgInputInDb(db, cmd.arg);
      if (!parsed.ok) {
        if (parsed.reason === 'ambiguous') {
          const block = parsed.ambiguous
            .map((a) => `Для "${a.query}" найдено несколько: ${a.options.join(', ')}`)
            .join('\n');
          return { handled: true, reply: `${block}\nУточни имя/username в /msg.` };
        }
        if (parsed.reason === 'recipients_not_found') {
          if (parsed.hints?.length) {
            return { handled: true, reply: `Не нашёл получателя. Возможно, имелось в виду:\n- ${parsed.hints.join('\n- ')}` };
          }
          return { handled: true, reply: 'Не нашёл получателя. Используй /contact_find <запрос>.' };
        }
        return { handled: true, reply: 'Не смог разобрать команду. Пример: /msg Вася привет' };
      }

      const preview = [
        'Превью отправки:',
        `Кому: ${parsed.contacts.map((c) => renderContactShort(c)).join(', ')}`,
        `Текст: ${parsed.message}`,
        'Отправить? да/нет',
      ].join('\n');

      setSession(db, chatId, {
        flow: 'msg_confirm',
        contact_ids: parsed.contacts.map((c) => c.id),
        message_text: parsed.message,
      });

      auditPush(db, 'message_prepare', {
        actor_id: userId,
        contact_ids: parsed.contacts.map((c) => c.id),
      });

      return { handled: true, reply: preview };
    }

    return { handled: false, reply: null };
  });
}

export async function runContactBookCommand(command, payload = {}, ctx = {}) {
  if (command === 'contact_handle_update') {
    return handleTelegramText(payload.message, ctx);
  }
  if (command === 'contact_add') {
    return createContact(payload, ctx);
  }
  if (command === 'contact_list') {
    return listContacts(payload.page || 1, ctx);
  }
  if (command === 'contact_find') {
    return findContacts(payload.query || '', ctx);
  }
  if (command === 'contact_show') {
    return getContact(payload.query || '', ctx);
  }
  if (command === 'contact_delete') {
    return deleteContact(payload.query || '', ctx);
  }
  if (command === 'contact_update') {
    return updateContact(payload.query || '', payload.patch || {}, ctx);
  }
  if (command === 'invite_generate') {
    return prepareInvite(payload.contactId, ctx);
  }
  if (command === 'invite_bind') {
    return bindByStartToken(payload.token, payload.telegramUser, payload.chatId, ctx);
  }
  if (command === 'contact_send') {
    return sendMessageToContacts(payload.contactIds || [], payload.text || '', payload.actorId, ctx);
  }
  throw new Error(`Unknown contact command: ${command}`);
}
