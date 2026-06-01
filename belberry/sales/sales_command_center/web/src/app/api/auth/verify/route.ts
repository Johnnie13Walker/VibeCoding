import { eq } from 'drizzle-orm';
import { NextResponse } from 'next/server';
import { z } from 'zod';
import { db } from '@/db';
import { users } from '@/db/schema';
import { findActiveUserByEmail } from '@/lib/bitrix';
import { consumeCode } from '@/lib/loginCodes';
import { checkRateLimit } from '@/lib/rateLimit';
import { getSession, type UserRole } from '@/lib/session';

export const runtime = 'nodejs';

const schema = z.object({
  email: z.string().email(),
  code: z.string().length(6),
});

function normalizeRole(role: string | null | undefined): UserRole {
  if (role === 'director' || role === 'rop' || role === 'manager') {
    return role;
  }

  return 'manager';
}

export async function POST(request: Request) {
  const parsed = schema.safeParse(await request.json().catch(() => null));

  if (!parsed.success) {
    return NextResponse.json({ error: 'invalid_request' }, { status: 400 });
  }

  const email = parsed.data.email.trim().toLowerCase();
  const rateLimit = await checkRateLimit(email);

  if (!rateLimit.ok) {
    return NextResponse.json({ error: 'rate_limited' }, { status: 429 });
  }

  const consumed = await consumeCode(email, parsed.data.code);

  if (!consumed.ok) {
    return NextResponse.json({ error: 'invalid_code' }, { status: 401 });
  }

  const activeUser = await findActiveUserByEmail(email);

  if (!activeUser) {
    return NextResponse.json({ error: 'inactive' }, { status: 403 });
  }

  const localUsers = await db
    .select({ role: users.role })
    .from(users)
    .where(eq(users.bitrixId, activeUser.bitrixId))
    .limit(1);
  const session = await getSession();

  session.bitrixId = activeUser.bitrixId;
  session.email = activeUser.email;
  session.role = normalizeRole(localUsers[0]?.role);
  await session.save();

  return NextResponse.json({ ok: true });
}
