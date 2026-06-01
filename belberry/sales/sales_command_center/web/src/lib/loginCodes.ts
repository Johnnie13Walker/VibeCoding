import { and, desc, eq, gte, sql } from 'drizzle-orm';
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
}

function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

function mapRow(row: typeof loginCodes.$inferSelect): LoginCodeRow {
  return {
    id: row.id,
    email: row.email,
    code: row.code,
    expiresAt: row.expiresAt,
    used: row.used,
    attempts: row.attempts,
    createdAt: row.createdAt ?? new Date(0),
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
};

export async function issueCode(
  email: string,
  repo: LoginCodeRepo = drizzleLoginCodeRepo,
): Promise<string> {
  const normalizedEmail = normalizeEmail(email);
  const code = generateCode();
  const now = new Date();

  await repo.invalidateUnused(normalizedEmail);
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
