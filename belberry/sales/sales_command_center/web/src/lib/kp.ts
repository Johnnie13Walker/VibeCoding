import { desc, eq } from 'drizzle-orm';
import { db } from '@/db';
import { kpJobs } from '@/db/schema';

export type KpFact = { key: string; value: unknown; source: string; status: string };
export type KpData = {
  deal_id: number | null;
  domain: string;
  brand: string;
  facts: KpFact[];
  hypotheses: { key: string; note: string; status: string }[];
  manual_checklist: string[];
};

export type KpJob = {
  id: number;
  dealId: number;
  brand: string;
  service: string;
  status: string;
  stage: string | null;
  error: string | null;
  kpData: KpData | null;
  createdAt: Date | string | null;
  updatedAt: Date | string | null;
};

export async function listKpJobs(limit = 50): Promise<KpJob[]> {
  const rows = await db
    .select()
    .from(kpJobs)
    .orderBy(desc(kpJobs.createdAt))
    .limit(limit);
  return rows.map((r) => ({
    id: r.id,
    dealId: r.dealId,
    brand: r.brand,
    service: r.service ?? 'seo',
    status: r.status,
    stage: r.stage,
    error: r.error,
    kpData: (r.kpData as KpData | null) ?? null,
    createdAt: r.createdAt,
    updatedAt: r.updatedAt,
  }));
}

export async function createKpJob(
  dealId: number,
  brand: string,
  service: string,
  requestedBy: number | null,
) {
  const safeBrand = brand === 'acoola' ? 'acoola' : 'belberry';
  const safeService = service === 'orm' ? 'orm' : 'seo';
  const [row] = await db
    .insert(kpJobs)
    .values({ dealId, brand: safeBrand, service: safeService, requestedBy })
    .returning({ id: kpJobs.id });
  return row.id;
}

/** Папка задания в движке kp/: воркер собирает туда артефакты (kp.html и json). */
export function jobDirName(jobId: number, dealId: number): string {
  return `_job_${jobId}_${dealId}`;
}

export async function getKpJob(id: number): Promise<KpJob | null> {
  const rows = await db.select().from(kpJobs).where(eq(kpJobs.id, id)).limit(1);
  if (!rows[0]) return null;
  const r = rows[0];
  return {
    id: r.id, dealId: r.dealId, brand: r.brand, service: r.service ?? 'seo',
    status: r.status, stage: r.stage,
    error: r.error, kpData: (r.kpData as KpData | null) ?? null,
    createdAt: r.createdAt, updatedAt: r.updatedAt,
  };
}
