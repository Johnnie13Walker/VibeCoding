import { getAudit, markReturnedToWork, recordAuditTask, userKind } from '@/lib/audit';
import { canSeeAudit } from '@/lib/audit-access';
import { createDealTask, getDealResponsible, reopenDeal, transferToTelemarketing } from '@/lib/bitrix-write';
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
  const audit = await getAudit(parseInt(id, 10));
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
    const kind = await userKind(responsibleId); // sales | rop | tm
    let outcomeKind: 'current' | 'transferred' | 'telemarketing';
    let effectiveStage: string;
    if (kind === 'tm') {
      // Перевод в воронку Телемаркетинг на телемаркетолога (повторный обзвон).
      await transferToTelemarketing(audit.dealId, responsibleId);
      outcomeKind = 'telemarketing';
      effectiveStage = 'C50:NEW';
    } else {
      const current = await getDealResponsible(audit.dealId);
      await reopenDeal(audit.dealId, stageId, responsibleId); // стадия + переназначение
      outcomeKind = current === responsibleId ? 'current' : 'transferred';
      effectiveStage = stageId;
    }
    // В начало каждой задачи — ссылка на полный аудит сделки (открывается в командном
    // центре). Фронт обычно уже подставил её в текст; если нет (или вызвали API напрямую) —
    // добавляем здесь. Идемпотентно: не дублируем, если ссылка на /audit/<id> уже есть.
    const base = (process.env.SCC_BASE_URL || req.headers.get('origin') || '').replace(/\/$/, '');
    const auditUrl = `${base}/audit/${audit.id}`;
    const fullDescription = taskDescription.includes(`/audit/${audit.id}`)
      ? taskDescription
      : `🔍 Полный аудит сделки: ${auditUrl}\n\n${taskDescription}`;
    const taskId = await createDealTask({
      dealId: audit.dealId,
      title: taskTitle,
      description: fullDescription,
      responsibleId,
      deadline,
    });
    await markReturnedToWork(audit.id, taskId, outcomeKind, responsibleId, effectiveStage);
    await recordAuditTask({ dealId: audit.dealId, taskId, responsibleId, title: taskTitle, deadline }); // видна в Алертах
    return Response.json({ ok: true, taskId, outcomeKind });
  } catch (e) {
    return Response.json({ error: (e as Error).message }, { status: 502 });
  }
}
