import crypto from 'node:crypto';

export function nowIso() {
  return new Date().toISOString();
}

export function normalizeText(value) {
  return String(value || '').trim().toLowerCase();
}

export function normalizeUsername(value) {
  const clean = String(value || '').trim();
  if (!clean) return null;
  const fromLink = clean.match(/^https?:\/\/t\.me\/([A-Za-z0-9_]{5,32})\/?$/i);
  if (fromLink) return `@${fromLink[1].toLowerCase()}`;
  const noProto = clean.match(/^t\.me\/([A-Za-z0-9_]{5,32})\/?$/i);
  if (noProto) return `@${noProto[1].toLowerCase()}`;
  const direct = clean.match(/^@?([A-Za-z0-9_]{5,32})$/);
  if (direct) return `@${direct[1].toLowerCase()}`;
  return null;
}

export function usernameToLink(username) {
  if (!username) return null;
  return `https://t.me/${username.replace(/^@/, '')}`;
}

export function tokenize(value) {
  return normalizeText(value)
    .replace(/[.,;:!?()\[\]{}]/g, ' ')
    .split(/\s+/)
    .filter(Boolean);
}

export function scoreContact(contact, query) {
  const q = normalizeText(query);
  if (!q) return 0;

  const fields = [
    contact.display_name || '',
    contact.tg_username || '',
    contact.note || '',
    contact.tg_link || '',
  ];

  let score = 0;
  for (const field of fields) {
    const f = normalizeText(field);
    if (!f) continue;
    if (f === q) score = Math.max(score, 120);
    else if (f.startsWith(q)) score = Math.max(score, 95);
    else if (f.includes(q)) score = Math.max(score, 75);
  }

  if (!score) {
    const qTokens = tokenize(q);
    const bag = tokenize(fields.join(' '));
    if (qTokens.length && bag.length) {
      const matched = qTokens.filter((t) => bag.some((b) => b.startsWith(t))).length;
      if (matched > 0) {
        score = Math.round((matched / qTokens.length) * 65);
      }
    }
  }

  return score;
}

export function genToken() {
  return crypto.randomBytes(24).toString('base64url');
}

export function hashToken(token) {
  return crypto.createHash('sha256').update(String(token)).digest('hex');
}

export function maskToken(token) {
  const t = String(token || '');
  if (t.length <= 8) return '***';
  return `${t.slice(0, 4)}***${t.slice(-4)}`;
}

export function parseQuickAdd(text) {
  const raw = String(text || '').trim();
  const m = raw.match(/^добавь\s+контакт\s*:\s*(.+)$/i);
  if (!m) return null;

  const body = m[1].trim();
  const usernameMatch = body.match(/(@[A-Za-z0-9_]{5,32}|(?:https?:\/\/)?t\.me\/[A-Za-z0-9_]{5,32})/i);
  if (!usernameMatch) {
    return { confident: false, reason: 'username_missing', raw: body };
  }

  const usernameRaw = usernameMatch[1];
  const username = normalizeUsername(usernameRaw);
  if (!username) {
    return { confident: false, reason: 'username_invalid', raw: body };
  }

  const before = body.slice(0, usernameMatch.index).trim().replace(/[,\-]+$/, '').trim();
  const after = body.slice((usernameMatch.index || 0) + usernameRaw.length).trim().replace(/^[,\-]+/, '').trim();

  if (!before) {
    return { confident: false, reason: 'name_missing', raw: body };
  }

  return {
    confident: true,
    display_name: before,
    tg_username: username,
    tg_link: usernameToLink(username),
    note: after || null,
  };
}
