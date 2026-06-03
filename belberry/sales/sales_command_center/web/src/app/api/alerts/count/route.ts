import { getAlerts } from '@/lib/alerts';
import { isPreviewMode } from '@/lib/preview';
import { getSession } from '@/lib/session';

export const dynamic = 'force-dynamic';

export async function GET() {
  const session = await getSession();
  if (!session.bitrixId && !isPreviewMode()) {
    return new Response('Unauthorized', { status: 401 });
  }
  const { count } = await getAlerts();
  return Response.json({ count });
}
