import { drizzleLoginCodeRepo, type LoginCodeRepo } from './loginCodes';

const WINDOW_MS = 15 * 60 * 1000;
// Поднято с 5: счётчик складывает запросы кода + неверные вводы (1 + attempts),
// и при 5 легитимный пользователь лочился после нескольких опечаток. 10 даёт
// запас на опечатки, оставаясь анти-брутфорс барьером (6-значный код).
const MAX_EVENTS = 10;

export interface RateLimitResult {
  ok: boolean;
  remaining: number;
}

export async function checkRateLimit(
  email: string,
  repo: LoginCodeRepo = drizzleLoginCodeRepo,
): Promise<RateLimitResult> {
  const normalizedEmail = email.trim().toLowerCase();
  const windowStart = new Date(Date.now() - WINDOW_MS);
  const rows = await repo.recentByEmail(normalizedEmail, windowStart);
  const events = rows.reduce((total, row) => total + 1 + row.attempts, 0);
  const remaining = Math.max(0, MAX_EVENTS - events);

  return {
    ok: events < MAX_EVENTS,
    remaining,
  };
}
