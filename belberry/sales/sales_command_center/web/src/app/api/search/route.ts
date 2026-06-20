import { and, eq, ilike, sql } from 'drizzle-orm';
import { db } from '@/db';
import { dealsSnapshot, users } from '@/db/schema';
import { availableReportDates } from '@/lib/reports';
import { isPreviewMode } from '@/lib/preview';
import { getSession } from '@/lib/session';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  const session = await getSession();
  if (!session.bitrixId && !isPreviewMode()) {
    return new Response('Unauthorized', { status: 401 });
  }

  // Ограничиваем длину запроса: q уходит bind-параметром (инъекции нет), но без
  // лимита гигантская строка = тяжёлый ILIKE-скан по таблицам.
  const q = (new URL(request.url).searchParams.get('q') ?? '').trim().slice(0, 64).toLowerCase();

  // Дни с отчётами.
  const allDates = await availableReportDates();
  const days = (q ? allDates.filter((d) => d.includes(q)) : allDates).slice(0, 6);

  // Менеджеры по имени.
  const managerRows = await db
    .select({ id: users.bitrixId, name: users.name, role: users.role })
    .from(users)
    .where(q ? ilike(users.name, `%${q}%`) : sql`true`)
    .limit(6);
  const managers = managerRows.map((m) => ({ id: m.id, name: m.name, role: m.role ?? '' }));

  // Сделки по названию (с последнего снимка).
  let deals: { id: number; title: string }[] = [];
  if (q) {
    const latest = await db.select({ d: sql<string>`max(${dealsSnapshot.reportDate})` }).from(dealsSnapshot);
    const snapDate = latest[0]?.d ?? null;
    if (snapDate) {
      const dealRows = await db
        .select({ id: dealsSnapshot.dealId, title: dealsSnapshot.title })
        .from(dealsSnapshot)
        .where(and(eq(dealsSnapshot.reportDate, snapDate), ilike(dealsSnapshot.title, `%${q}%`)))
        .limit(6);
      deals = dealRows.map((d) => ({ id: d.id, title: d.title ?? `Сделка #${d.id}` }));
    }
  }

  return Response.json({ days, managers, deals });
}
