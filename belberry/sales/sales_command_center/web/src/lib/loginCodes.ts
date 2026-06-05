import { and, desc, eq, gte, lt, sql } from 'drizzle-orm';
import { db } from '@/db';
import { loginCodes } from '@/db/schema';
import { generateCode, hashCode, verifyCode } from './code';

export type ConsumeCodeResult =
  | { ok: true; email: string }
  | { ok: false; reason: 'expired' | 'mismatch' };

export interface LoginCodeRow {
  id: number;
  email: string;
  code: string;
  expiresAt: Date;
  used: boolean;
  attempts: number;
  createdAt: Date;
}

export interface InsertLoginCode {
  email: string;
  code: string;
  expiresAt: Date;
  used: boolean;
  attempts: number;
  createdAt: Date;
}

export interface LoginCodeRepo {
  invalidateUnused(email: string): Promise<void>;
  insert(row: InsertLoginCode): Promise<void>;
  newestUnused(email: string): Promise<LoginCodeRow | null>;
  markUsed(id: number): Promise<void>;
  incrementAttempts(id: number): Promise<void>;
  recentByEmail(email: string, windowStart: Date): Promise<LoginCodeRow[]>;
  purgeExpired(before: Date): Promise<void>;
}

function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

function mapRow(row: typeof loginCodes.$inferSelect): LoginCodeRow {
  // Drizzle/postgres.js может вернуть timestamptz строкой, а не Date — тогда
  // row.expiresAt.getTime() в consumeCode падал бы (→ 500, маскируется под
  // «код не подошёл»). Нормализуем к Date явно.
  return {
    id: row.id,
    email: row.email,
    code: row.code,
    expiresAt: new Date(row.expiresAt),
    used: row.used,
    attempts: row.attempts,
    createdAt: row.createdAt ? new Date(row.createdAt) : new Date(0),
  };
}

export const drizzleLoginCodeRepo: LoginCodeRepo = {
  async invalidateUnused(email) {
    await db
      .update(loginCodes)
      .set({ used: true })
      .where(and(eq(loginCodes.email, normalizeEmail(email)), eq(loginCodes.used, false)));
  },

  async insert(row) {
    await db.insert(loginCodes).values(row);
  },

  async newestUnused(email) {
    const rows = await db
      .select()
      .from(loginCodes)
      .where(and(eq(loginCodes.email, normalizeEmail(email)), eq(loginCodes.used, false)))
      .orderBy(desc(loginCodes.createdAt))
      .limit(1);

    return rows[0] ? mapRow(rows[0]) : null;
  },

  async markUsed(id) {
    await db.update(loginCodes).set({ used: true }).where(eq(loginCodes.id, id));
  },

  async incrementAttempts(id) {
    await db
      .update(loginCodes)
      .set({ attempts: sql`${loginCodes.attempts} + 1` })
      .where(eq(loginCodes.id, id));
  },

  async recentByEmail(email, windowStart) {
    const rows = await db
      .select()
      .from(loginCodes)
      .where(
        and(
          eq(loginCodes.email, normalizeEmail(email)),
          gte(loginCodes.createdAt, windowStart),
        ),
      );

    return rows.map(mapRow);
  },

  async purgeExpired(before) {
    await db.delete(loginCodes).where(lt(loginCodes.expiresAt, before));
  },
};

export async function issueCode(
  email: string,
  repo: LoginCodeRepo = drizzleLoginCodeRepo,
): Promise<string> {
  const normalizedEmail = normalizeEmail(email);
  const code = generateCode();
  const now = new Date();

  await repo.invalidateUnused(normalizedEmail);
  // Чистим протухшие коды (старше суток), чтобы таблица не росла бесконечно.
  await repo.purgeExpired(new Date(now.getTime() - 24 * 60 * 60 * 1000));
  await repo.insert({
    email: normalizedEmail,
    code: hashCode(code),
    expiresAt: new Date(now.getTime() + 10 * 60 * 1000),
    used: false,
    attempts: 0,
    createdAt: now,
  });

  return code;
}

export async function consumeCode(
  email: string,
  plain: string,
  repo: LoginCodeRepo = drizzleLoginCodeRepo,
): Promise<ConsumeCodeResult> {
  const normalizedEmail = normalizeEmail(email);
  const row = await repo.newestUnused(normalizedEmail);
  const now = new Date();

  if (!row || row.expiresAt.getTime() <= now.getTime()) {
    return { ok: false, reason: 'expired' };
  }

  if (!verifyCode(plain, row.code)) {
    await repo.incrementAttempts(row.id);
    return { ok: false, reason: 'mismatch' };
  }

  await repo.markUsed(row.id);
  return { ok: true, email: normalizedEmail };
}
