import { beforeEach, describe, expect, it } from 'vitest';
import { hashCode } from '../code';
import {
  consumeCode,
  issueCode,
  type InsertLoginCode,
  type LoginCodeRepo,
  type LoginCodeRow,
} from '../loginCodes';

class MemoryLoginCodeRepo implements LoginCodeRepo {
  rows: LoginCodeRow[] = [];

  async invalidateUnused(email: string) {
    this.rows
      .filter((row) => row.email === email && !row.used)
      .forEach((row) => {
        row.used = true;
      });
  }

  async insert(row: InsertLoginCode) {
    this.rows.push({ id: this.rows.length + 1, ...row });
  }

  async newestUnused(email: string) {
    return (
      [...this.rows]
        .filter((row) => row.email === email && !row.used)
        .sort((left, right) => right.createdAt.getTime() - left.createdAt.getTime())[0] ??
      null
    );
  }

  async markUsed(id: number) {
    const row = this.rows.find((item) => item.id === id);
    if (row) {
      row.used = true;
    }
  }

  async incrementAttempts(id: number) {
    const row = this.rows.find((item) => item.id === id);
    if (row) {
      row.attempts += 1;
    }
  }

  async recentByEmail(email: string, windowStart: Date) {
    return this.rows.filter(
      (row) => row.email === email && row.createdAt.getTime() >= windowStart.getTime(),
    );
  }
}

describe('login code lifecycle', () => {
  let repo: MemoryLoginCodeRepo;

  beforeEach(() => {
    repo = new MemoryLoginCodeRepo();
  });

  it('issues hashed one-time code and invalidates previous unused codes', async () => {
    repo.rows.push({
      id: 1,
      email: 'manager@example.com',
      code: hashCode('111111'),
      expiresAt: new Date(Date.now() + 60_000),
      used: false,
      attempts: 0,
      createdAt: new Date(),
    });

    const code = await issueCode('Manager@Example.com', repo);

    expect(code).toMatch(/^\d{6}$/);
    expect(repo.rows[0].used).toBe(true);
    expect(repo.rows[1].email).toBe('manager@example.com');
    expect(repo.rows[1].code).not.toBe(code);
    expect(repo.rows[1].code).toMatch(/^[a-f0-9]{64}$/);
  });

  it('consumes a valid code once', async () => {
    const code = await issueCode('manager@example.com', repo);

    await expect(consumeCode('manager@example.com', code, repo)).resolves.toEqual({
      ok: true,
      email: 'manager@example.com',
    });
    await expect(consumeCode('manager@example.com', code, repo)).resolves.toEqual({
      ok: false,
      reason: 'expired',
    });
  });

  it('increments attempts on mismatch', async () => {
    await issueCode('manager@example.com', repo);

    await expect(consumeCode('manager@example.com', '000000', repo)).resolves.toEqual({
      ok: false,
      reason: 'mismatch',
    });
    expect(repo.rows[0].attempts).toBe(1);
  });

  it('rejects expired codes', async () => {
    repo.rows.push({
      id: 1,
      email: 'manager@example.com',
      code: hashCode('123456'),
      expiresAt: new Date(Date.now() - 1),
      used: false,
      attempts: 0,
      createdAt: new Date(),
    });

    await expect(consumeCode('manager@example.com', '123456', repo)).resolves.toEqual({
      ok: false,
      reason: 'expired',
    });
  });
});
