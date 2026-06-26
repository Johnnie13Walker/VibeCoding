import { execFile } from 'node:child_process';
import { getAudit } from '@/lib/audit';
import { canSeeAudit } from '@/lib/audit-access';
import { crossOriginResponse, isSameOrigin } from '@/lib/origin';
import { isPreviewMode } from '@/lib/preview';
import { getSession } from '@/lib/session';

export const dynamic = 'force-dynamic';

// Команда раннера для умной постановки задачи. Берём из AUDIT_DRAFT_CMD, иначе выводим
// из AUDIT_WORKER_CMD (тот же каталог scripts) — чтобы не плодить env на проде.
function draftCmd(): string | null {
  const direct = process.env.AUDIT_DRAFT_CMD;
  if (direct) return direct;
  const worker = process.env.AUDIT_WORKER_CMD;
  if (worker) return worker.replace(/run_audit_worker\.sh.*$/, 'run_audit_task_draft.sh');
  return null;
}

function runDraft(cmd: string, auditId: number, responsibleId: number): Promise<{ title?: string; description?: string; error?: string }> {
  return new Promise((resolve) => {
    execFile('sh', ['-c', `${cmd} ${auditId} ${responsibleId}`], { timeout: 60_000, maxBuffer: 1 << 20 }, (err, stdout) => {
      if (err && !stdout) { resolve({ error: 'ИИ недоступен' }); return; }
      const line = (stdout || '').trim().split('\n').filter(Boolean).pop() || '';
      try { resolve(JSON.parse(line)); } catch { resolve({ error: 'ИИ недоступен' }); }
    });
  });
}

/** Умная задача под выбранного менеджера (пол/имя/легенда перехвата). Если ИИ
 * недоступен (квота/ошибка) — возвращаем {error}, фронт оставляет базовый план. */
export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  if (!isSameOrigin(req)) return crossOriginResponse();
  const session = await getSession();
  if (!isPreviewMode()) {
    if (!session.bitrixId) return new Response('Unauthorized', { status: 401 });
    if (!canSeeAudit(session.email, session.role)) return new Response('Not Found', { status: 404 });
  }
  const { id } = await ctx.params;
  const auditId = parseInt(id, 10);
  const audit = await getAudit(auditId);
  if (!audit) return Response.json({ error: 'Аудит не найден' }, { status: 404 });

  const body = await req.json().catch(() => null);
  const responsibleId = Number(body?.responsibleId);
  if (!Number.isInteger(responsibleId) || responsibleId <= 0) {
    return Response.json({ error: 'Не указан менеджер' }, { status: 400 });
  }
  const cmd = draftCmd();
  if (!cmd) return Response.json({ error: 'ИИ недоступен' }, { status: 200 });

  const res = await runDraft(cmd, auditId, responsibleId);
  if (res.error || !res.title) return Response.json({ error: res.error || 'ИИ недоступен' }, { status: 200 });
  return Response.json({ title: res.title, description: res.description ?? '' }, { status: 200 });
}
