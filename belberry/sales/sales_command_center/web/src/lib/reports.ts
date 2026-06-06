import 'server-only';

import { desc, eq, inArray } from 'drizzle-orm';
import { db } from '@/db';
import { reports } from '@/db/schema';

const READY_STATUSES = ['done', 'partial_llm_failure'] as const;
const readyStatusSet = new Set<string>(READY_STATUSES);

export async function availableReportDates(): Promise<string[]> {
  const rows = await db
    .select({ d: reports.reportDate, status: reports.status })
    .from(reports)
    .where(inArray(reports.status, READY_STATUSES))
    .orderBy(desc(reports.reportDate));

  return rows
    .filter((row) => readyStatusSet.has(row.status))
    .map((row) => row.d)
    .filter(Boolean);
}

export async function getReportHtml(date: string): Promise<string | null> {
  const rows = await db
    .select({ html: reports.html, status: reports.status })
    .from(reports)
    .where(eq(reports.reportDate, date))
    .limit(1);
  const report = rows[0];

  if (!report || !readyStatusSet.has(report.status) || !report.html?.trim()) {
    return null;
  }

  return report.html;
}
