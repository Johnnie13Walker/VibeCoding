import { NextResponse } from 'next/server';
import { z } from 'zod';
import { findActiveUserByEmail, sendCodeMessage } from '@/lib/bitrix';
import { issueCode } from '@/lib/loginCodes';
import { checkRateLimit } from '@/lib/rateLimit';

export const runtime = 'nodejs';

const schema = z.object({
  email: z.string().email(),
});

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

  const user = await findActiveUserByEmail(email);

  if (!user) {
    return NextResponse.json({ error: 'email_not_found' }, { status: 404 });
  }

  const code = await issueCode(email);
  await sendCodeMessage(user.bitrixId, code);

  return NextResponse.json({ ok: true });
}
