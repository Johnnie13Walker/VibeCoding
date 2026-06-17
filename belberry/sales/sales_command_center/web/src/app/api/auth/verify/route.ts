import { eq } from 'drizzle-orm';
import { NextResponse } from 'next/server';
import { z } from 'zod';
import { db } from '@/db';
import { users } from '@/db/schema';
import { findActiveUserByEmail } from '@/lib/bitrix';
import { markCodeUsed, verifyLoginCode } from '@/lib/loginCodes';
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

  let check;
  try {
    check = await verifyLoginCode(email, parsed.data.code);
  } catch (err) {
    // Раньше исключение здесь (напр. expires_at пришёл строкой → .getTime())
    // отдавалось как общий сбой и в UI выглядело как «код не подошёл».
    console.error('[auth] verifyLoginCode threw:', (err as Error)?.name, (err as Error)?.message);
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }

  if (!check.ok) {
    console.warn('[auth] verify rejected:', { email, reason: check.reason });
    return NextResponse.json({ error: 'invalid_code' }, { status: 401 });
  }

  // Активность сотрудника проверяем и сессию сохраняем ДО списания кода. Любой
  // транзиентный сбой Bitrix/БД здесь возвращает 503 и НЕ сжигает код — человек
  // повторит ввод того же кода, как только сервис ответит. Списание (markCodeUsed)
  // — самый последний шаг, после которого вход гарантированно состоялся.
  try {
    const activeUser = await findActiveUserByEmail(email);

    if (!activeUser) {
      console.warn('[auth] verify inactive:', { email });
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

    await markCodeUsed(check.id);
  } catch (err) {
    console.error('[auth] post-verify failed:', (err as Error)?.name, (err as Error)?.message);
    return NextResponse.json({ error: 'temporary_error' }, { status: 503 });
  }

  return NextResponse.json({ ok: true });
}
