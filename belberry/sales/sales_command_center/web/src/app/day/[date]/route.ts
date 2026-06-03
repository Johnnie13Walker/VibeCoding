import DOMPurify from 'isomorphic-dompurify';
import { parseReportDate } from '@/lib/dates';
import { isPreviewMode } from '@/lib/preview';
import { getReportHtml } from '@/lib/reports';
import { getSession } from '@/lib/session';

export const dynamic = 'force-dynamic';

interface DayRouteContext {
  params: Promise<{
    date: string;
  }>;
}

function notFoundHtml(date: string) {
  return `<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><title>Нет отчёта</title></head><body style="font-family:sans-serif;padding:2rem"><h1>Нет отчёта за эту дату</h1><p>За ${date} отчёт ещё не сформирован.</p></body></html>`;
}

export async function GET(_request: Request, { params }: DayRouteContext) {
  const session = await getSession();

  if (!session.bitrixId && !isPreviewMode()) {
    return new Response('Unauthorized', { status: 401 });
  }

  const { date } = await params;
  const reportDate = parseReportDate(date);

  if (!reportDate) {
    return new Response('Not found', { status: 404 });
  }

  const html = await getReportHtml(reportDate);

  if (!html) {
    return new Response(notFoundHtml(reportDate), {
      status: 404,
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        'X-Robots-Tag': 'noindex, nofollow',
      },
    });
  }

  const clean = DOMPurify.sanitize(html, {
    WHOLE_DOCUMENT: true,
    ADD_TAGS: ['style'],
    FORCE_BODY: false,
  });

  return new Response(clean, {
    status: 200,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'X-Robots-Tag': 'noindex, nofollow',
    },
  });
}
