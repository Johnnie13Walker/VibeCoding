// CSRF-защита для мутирующих POST-маршрутов. Основной барьер — cookie сессии
// SameSite=Lax (блокирует cross-site POST), это дополнительный эшелон: отсекаем
// запросы с заведомо ЧУЖИМ Origin. nginx форвардит реальный Host ($host), поэтому
// сравнение Origin-host с Host работает для всех доменов (blbr-team.net/static.*/www).

/** Допустимые хосты: реальный Host из запроса + хост SCC_BASE_URL (запасной). */
function allowedHosts(request: Request): Set<string> {
  const hosts = new Set<string>();
  const host = request.headers.get('host');
  if (host) hosts.add(host.toLowerCase());
  const base = process.env.SCC_BASE_URL;
  if (base) {
    try {
      hosts.add(new URL(base).host.toLowerCase());
    } catch {
      // кривой SCC_BASE_URL игнорируем
    }
  }
  return hosts;
}

/**
 * true — запрос можно обрабатывать. Отсутствующий Origin ПРОПУСКАЕМ (fail-open):
 * браузер не всегда шлёт его на same-origin/form-навигации, и ломать вход из-за
 * этого нельзя; cross-site атака всегда несёт чужой Origin и будет отбита.
 */
export function isSameOrigin(request: Request): boolean {
  const origin = request.headers.get('origin');
  if (!origin) return true;
  let host: string;
  try {
    host = new URL(origin).host.toLowerCase();
  } catch {
    return false;
  }
  return allowedHosts(request).has(host);
}

/** Готовый 403-ответ для отказа по cross-origin. */
export function crossOriginResponse(): Response {
  return new Response('Forbidden', { status: 403 });
}
