function trimBase(raw) {
  return String(raw || '').trim().replace(/\/+$/, '');
}

export function getBitrixConfig(ctx = {}) {
  const env = ctx.env || process.env;
  const base = trimBase(env.BITRIX_WEBHOOK_BASE || env.BITRIX_API_BASE);
  return { configured: Boolean(base), base };
}

export async function pingBitrix(ctx = {}) {
  const conf = getBitrixConfig(ctx);
  if (!conf.configured) return { configured: false, ok: null, message: 'не настроен' };

  const url = `${conf.base}/profile.json`;
  try {
    const res = await fetch(url, { method: 'GET', signal: ctx.signal });
    if (!res.ok) return { configured: true, ok: false, message: `HTTP ${res.status}` };
    return { configured: true, ok: true, message: 'OK' };
  } catch (err) {
    return { configured: true, ok: false, message: String(err?.message || err || 'ошибка') };
  }
}
