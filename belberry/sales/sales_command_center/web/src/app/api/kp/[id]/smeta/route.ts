import { existsSync, readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { getKpJob, jobDirName } from '@/lib/kp';
import { canSeeKp } from '@/lib/kp-access';
import { isPreviewMode } from '@/lib/preview';
import { getSession } from '@/lib/session';

export const dynamic = 'force-dynamic';

const ENGINE_CANDIDATES = [
  process.env.KP_ENGINE_DIR,
  '/opt/scc/VibeCoding/belberry/sales/kp',
  path.resolve(process.cwd(), '../kp'),
  path.resolve(process.cwd(), '../../kp'),
].filter(Boolean) as string[];

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
    const dir = path.join(engine, 'clients', jobDirName(job.id, job.dealId));
    if (!existsSync(dir)) continue;
    const xlsx = readdirSync(dir).find((f) => f.startsWith('Смета_') && f.endsWith('.xlsx'));
    if (xlsx) {
      return new Response(readFileSync(path.join(dir, xlsx)), {
        headers: {
          'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          'Content-Disposition': `attachment; filename="${encodeURIComponent(xlsx)}"`,
          'Cache-Control': 'no-store',
        },
      });
    }
  }
  return new Response('Смета не найдена — задание собрано до обновления', { status: 404 });
}
