import { createKpJob, listKpJobs } from '@/lib/kp';
import { canSeeKp } from '@/lib/kp-access';
import { isPreviewMode } from '@/lib/preview';
import { getSession } from '@/lib/session';

export const dynamic = 'force-dynamic';

/** Пилотный доступ: для остальных эндпоинт неотличим от несуществующего (404). */
async function guard(): Promise<Response | null> {
  const session = await getSession();
  if (isPreviewMode()) return null;
  if (!session.bitrixId) return new Response('Unauthorized', { status: 401 });
  if (!canSeeKp(session.email)) return new Response('Not Found', { status: 404 });
  return null;
}

export async function GET() {
  const denied = await guard();
  if (denied) return denied;
  const jobs = await listKpJobs();
  return Response.json({ jobs });
}

export async function POST(req: Request) {
  const denied = await guard();
  if (denied) return denied;
  const session = await getSession();
  const body = await req.json().catch(() => null);
  const dealId = Number(body?.dealId);
  if (!Number.isInteger(dealId) || dealId <= 0) {
    return Response.json({ error: 'Укажи корректный ID сделки' }, { status: 400 });
  }
  const id = await createKpJob(
    dealId,
    String(body?.brand ?? 'belberry'),
    String(body?.service ?? 'seo'),
    session.bitrixId ?? null,
  );
  return Response.json({ id }, { status: 201 });
}
