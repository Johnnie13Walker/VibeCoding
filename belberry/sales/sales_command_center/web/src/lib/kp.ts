import { desc } from 'drizzle-orm';
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
    status: r.status,
    stage: r.stage,
    error: r.error,
    kpData: (r.kpData as KpData | null) ?? null,
    createdAt: r.createdAt,
    updatedAt: r.updatedAt,
  }));
}

export async function createKpJob(dealId: number, brand: string, requestedBy: number | null) {
  const safeBrand = brand === 'acoola' ? 'acoola' : 'belberry';
  const [row] = await db
    .insert(kpJobs)
    .values({ dealId, brand: safeBrand, requestedBy })
    .returning({ id: kpJobs.id });
  return row.id;
}
