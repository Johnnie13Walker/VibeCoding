import { createAudit, listAudits, parseDealId } from '@/lib/audit';
import { canSeeAudit } from '@/lib/audit-access';
import { crossOriginResponse, isSameOrigin } from '@/lib/origin';
import { isPreviewMode } from '@/lib/preview';
import { getSession } from '@/lib/session';

export const dynamic = 'force-dynamic';

/** Доступ только РОП/руководителю + allowlist; иначе 404 (как у /kp). */
async function guard(): Promise<Response | null> {
  const session = await getSession();
  if (isPreviewMode()) return null;
  if (!session.bitrixId) return new Response('Unauthorized', { status: 401 });
  if (!canSeeAudit(session.email, session.role)) return new Response('Not Found', { status: 404 });
  return null;
}

export async function GET() {
  const denied = await guard();
  if (denied) return denied;
  const audits = await listAudits();
  return Response.json({ audits });
}

export async function POST(req: Request) {
  if (!isSameOrigin(req)) return crossOriginResponse();
  const denied = await guard();
  if (denied) return denied;
  const session = await getSession();
  const body = await req.json().catch(() => null);
  // Принимаем ID или ссылку на сделку Bitrix (не путаем «24» из «bitrix24» с ID).
  const dealId = parseDealId(String(body?.deal ?? body?.dealId ?? ''));
  if (!dealId) {
    return Response.json({ error: 'Укажи ID или ссылку на сделку' }, { status: 400 });
  }
  const id = await createAudit(dealId, session.bitrixId ?? null);
  return Response.json({ id }, { status: 201 });
}
