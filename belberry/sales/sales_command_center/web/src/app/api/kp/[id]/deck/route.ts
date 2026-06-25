import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { getKpJob, jobDirName } from '@/lib/kp';
import { canSeeKp } from '@/lib/kp-access';
import { isPreviewMode } from '@/lib/preview';
import { getSession } from '@/lib/session';

export const dynamic = 'force-dynamic';

// где лежит движок КП: прод → /opt/scc/VibeCoding/…, локально → относительно web/
const ENGINE_CANDIDATES = [
  process.env.KP_ENGINE_DIR,
  '/opt/scc/VibeCoding/belberry/sales/kp',
  path.resolve(process.cwd(), '../kp'),
  path.resolve(process.cwd(), '../../kp'),
].filter(Boolean) as string[];

const DRAFT_BANNER = `
<div style="position:sticky;top:0;z-index:9999;background:#b5651d;color:#fff;
  font:600 13px/1.4 -apple-system,sans-serif;padding:10px 16px;text-align:center;">
  ЧЕРНОВИК — цены и часть текстов шаблонные. Перед отправкой клиенту: цены из сметы
  сметчика, титул, нумерация слайдов. Печать в PDF: Cmd/Ctrl+P → «Сохранить как PDF».
</div>`;

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const session = await getSession();
  if (!isPreviewMode()) {
    if (!session.bitrixId) return new Response('Unauthorized', { status: 401 });
    if (!canSeeKp(session.email)) return new Response('Not Found', { status: 404 });
  }
  const id = Number((await params).id);
  if (!Number.isInteger(id) || id <= 0) return new Response('Not Found', { status: 404 });
  const job = await getKpJob(id);
  if (!job || job.status !== 'ready') return new Response('Not Found', { status: 404 });

  for (const engine of ENGINE_CANDIDATES) {
    const file = path.join(engine, 'clients', jobDirName(job.id, job.dealId), 'kp.html');
    if (existsSync(file)) {
      const html = readFileSync(file, 'utf-8').replace(/<body([^>]*)>/i, `<body$1>${DRAFT_BANNER}`);
      return new Response(html, {
        headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' },
      });
    }
  }
  return new Response('Черновик не найден — задание собрано до обновления или папка очищена', { status: 404 });
}
