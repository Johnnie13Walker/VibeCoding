import { getAudit, markReturnedToWork } from '@/lib/audit';
import { canSeeAudit } from '@/lib/audit-access';
import { createDealTask, reopenDeal } from '@/lib/bitrix-write';
import { crossOriginResponse, isSameOrigin } from '@/lib/origin';
import { isPreviewMode } from '@/lib/preview';
import { getSession } from '@/lib/session';

export const dynamic = 'force-dynamic';

// Возврат сделки в работу: смена стадии + постановка первой задачи из аудита.
// Веб пишет в Bitrix напрямую (решение заказчика 23.06).
export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  if (!isSameOrigin(req)) return crossOriginResponse();
  const session = await getSession();
  if (!isPreviewMode()) {
    if (!session.bitrixId) return new Response('Unauthorized', { status: 401 });
    if (!canSeeAudit(session.email, session.role)) return new Response('Not Found', { status: 404 });
  }

  const { id } = await ctx.params;
  const audit = await getAudit(Number(id));
  if (!audit) return Response.json({ error: 'Аудит не найден' }, { status: 404 });
  if (audit.returnedToWork) return Response.json({ error: 'Сделка уже возвращена в работу' }, { status: 409 });

  const body = await req.json().catch(() => null);
  const stageId = String(body?.stageId ?? 'C10:EXECUTING');
  const responsibleId = Number(body?.responsibleId);
  const taskTitle = String(body?.taskTitle ?? '').trim();
  const taskDescription = String(body?.taskDescription ?? '').trim();
  const deadline = body?.deadline ? String(body.deadline) : undefined;

  if (!Number.isInteger(responsibleId) || responsibleId <= 0) {
    return Response.json({ error: 'Не указан ответственный' }, { status: 400 });
  }
  if (!taskTitle) {
    return Response.json({ error: 'Пустой заголовок задачи' }, { status: 400 });
  }

  try {
    await reopenDeal(audit.dealId, stageId, responsibleId); // стадия + переназначение сделки
    const taskId = await createDealTask({
      dealId: audit.dealId,
      title: taskTitle,
      description: taskDescription,
      responsibleId,
      deadline,
    });
    await markReturnedToWork(audit.id, taskId);
    return Response.json({ ok: true, taskId });
  } catch (e) {
    return Response.json({ error: (e as Error).message }, { status: 502 });
  }
}
