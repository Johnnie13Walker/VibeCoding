import { getAudit } from '@/lib/audit';
import { canSeeAudit } from '@/lib/audit-access';
import { isPreviewMode } from '@/lib/preview';
import { getSession } from '@/lib/session';

export const dynamic = 'force-dynamic';

// Один аудит — для опроса статуса на странице отчёта /audit/[id].
export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const session = await getSession();
  if (!isPreviewMode()) {
    if (!session.bitrixId) return new Response('Unauthorized', { status: 401 });
    if (!canSeeAudit(session.email, session.role)) return new Response('Not Found', { status: 404 });
  }
  const { id } = await ctx.params;
  const audit = await getAudit(parseInt(id, 10));
  if (!audit) return Response.json({ error: 'Аудит не найден' }, { status: 404 });
  return Response.json({ audit });
}
