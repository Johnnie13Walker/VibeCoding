import { describe, expect, it } from 'vitest';
import { checkRateLimit } from '../rateLimit';
import type { InsertLoginCode, LoginCodeRepo, LoginCodeRow } from '../loginCodes';

class MemoryLoginCodeRepo implements LoginCodeRepo {
  constructor(private readonly rows: LoginCodeRow[]) {}

  async invalidateUnused() {}
  async insert(row: InsertLoginCode) {
    void row;
  }
  async newestUnused() {
    return null;
  }
  async markUsed() {}
  async incrementAttempts() {}

  async recentByEmail(email: string, windowStart: Date) {
    return this.rows.filter(
      (row) => row.email === email && row.createdAt.getTime() >= windowStart.getTime(),
    );
  }

  async purgeExpired() {}
}

function row(attempts: number, createdAt = new Date()): LoginCodeRow {
  return {
    id: attempts + 1,
    email: 'manager@example.com',
    code: 'hash',
    expiresAt: new Date(Date.now() + 60_000),
    used: false,
    attempts,
    createdAt,
  };
}

describe('rate limit', () => {
  it('allows requests below the 15-minute limit', async () => {
    await expect(checkRateLimit('manager@example.com', new MemoryLoginCodeRepo([row(1)]))).resolves.toEqual({
      ok: true,
      remaining: 8,
    });
  });

  it('blocks when issued codes and attempts reach the limit', async () => {
    const repo = new MemoryLoginCodeRepo([row(4), row(4)]);

    await expect(checkRateLimit('manager@example.com', repo)).resolves.toEqual({
      ok: false,
      remaining: 0,
    });
  });

  it('ignores rows outside the window', async () => {
    const old = new Date(Date.now() - 16 * 60 * 1000);

    await expect(checkRateLimit('manager@example.com', new MemoryLoginCodeRepo([row(20, old)]))).resolves.toEqual({
      ok: true,
      remaining: 10,
    });
  });
});
