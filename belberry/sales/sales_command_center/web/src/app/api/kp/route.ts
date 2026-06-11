import { createKpJob, listKpJobs } from '@/lib/kp';
import { isPreviewMode } from '@/lib/preview';
import { getSession } from '@/lib/session';

export const dynamic = 'force-dynamic';

export async function GET() {
  const session = await getSession();
  if (!session.bitrixId && !isPreviewMode()) {
    return new Response('Unauthorized', { status: 401 });
  }
  const jobs = await listKpJobs();
  return Response.json({ jobs });
}

export async function POST(req: Request) {
  const session = await getSession();
  if (!session.bitrixId && !isPreviewMode()) {
    return new Response('Unauthorized', { status: 401 });
  }
  const body = await req.json().catch(() => null);
  const dealId = Number(body?.dealId);
  if (!Number.isInteger(dealId) || dealId <= 0) {
    return Response.json({ error: 'Укажи корректный ID сделки' }, { status: 400 });
  }
  const id = await createKpJob(dealId, String(body?.brand ?? 'belberry'), session.bitrixId ?? null);
  return Response.json({ id }, { status: 201 });
}
