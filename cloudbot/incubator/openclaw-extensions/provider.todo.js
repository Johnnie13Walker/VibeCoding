function baseUrl(env) {
  const raw = String(env.TODO_API_BASE || env.TODOIST_API_BASE || 'https://api.todoist.com/rest/v2').trim();
  return raw.replace(/\/+$/, '');
}

export function getTodoConfig(ctx = {}) {
  const env = ctx.env || process.env;
  const token = String(env.TODO_API_TOKEN || env.TODOIST_API_TOKEN || '').trim();
  const configured = Boolean(token);
  return {
    configured,
    token,
    base: baseUrl(env),
  };
}

export async function pingTodo(ctx = {}) {
  const conf = getTodoConfig(ctx);
  if (!conf.configured) return { configured: false, ok: null, message: 'не настроен' };

  const url = `${conf.base}/projects`;
  try {
    const res = await fetch(url, {
      method: 'GET',
      headers: { Authorization: `Bearer ${conf.token}` },
      signal: ctx.signal,
    });
    if (!res.ok) return { configured: true, ok: false, message: `HTTP ${res.status}` };
    return { configured: true, ok: true, message: 'OK' };
  } catch (err) {
    return { configured: true, ok: false, message: String(err?.message || err || 'ошибка') };
  }
}
