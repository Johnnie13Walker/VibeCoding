import { desc, eq, inArray } from 'drizzle-orm';
import { db } from '@/db';
import { dealAudits, meetingTasks, users } from '@/db/schema';
import { isSalesDept, isTelemarketing } from '@/lib/dashboard';

// Названия стадий воронки «Продажи» (CATEGORY_ID=10) для показа стадии на момент аудита.
const STAGE_NAMES: Record<string, string> = {
  'C10:NEW': 'Квалификация',
  'C10:PREPAYMENT_INVOIC': 'Подготовка БРИФа',
  'C10:EXECUTING': 'Подготовка КП',
  'C10:UC_4SJOE4': 'Защита КП',
  'C10:FINAL_INVOICE': 'Получить решение',
  'C10:UC_RJK0KE': 'Получить реквизиты',
  'C10:UC_KC7195': 'Согласование договора',
  'C10:UC_755Z64': 'Ожидаем оплату',
  'C10:WON': 'Успех',
  'C10:LOSE': 'Отвал',
  'C10:1': 'Отложено',
};
function stageLabelOf(result: AuditResult | null): string | null {
  const id = result?.signals?.stage_id as string | undefined;
  return id ? (STAGE_NAMES[id] ?? id) : null;
}

export type SalesUser = { id: number; name: string };

/** Активные менеджеры отдела продаж (МОП) + РОП — для выбора ответственного.
 * Телемаркетологов исключаем: они сделки в работу не берут. */
export async function listSalesUsers(): Promise<SalesUser[]> {
  const rows = await db
    .select({ id: users.bitrixId, name: users.name, dept: users.dept, role: users.role })
    .from(users)
    .where(eq(users.isActive, true));
  return rows
    .filter(
      (u) =>
        (isSalesDept(u.dept) && !isTelemarketing(u.dept)) ||
        u.role === 'rop' ||
        u.role === 'director',
    )
    .map((u) => ({ id: u.id, name: u.name }))
    .sort((a, b) => a.name.localeCompare(b.name, 'ru'));
}

/**
 * ID сделки из ввода: ссылка Bitrix или голый номер. Важно НЕ хватать «24» из
 * «bitrix24» — сначала ищем номер в пути /deal/details/<id>, затем голый номер.
 */
export function parseDealId(raw: string): number | null {
  const s = (raw ?? '').trim();
  const url = s.match(/details\/(\d+)/) || s.match(/\/deal\/(\d+)/);
  let id: number;
  if (url) id = Number(url[1]);
  else if (/^\d+$/.test(s)) id = Number(s);
  else {
    // запасной вариант: самое длинное число во вводе (≥3 цифр, мимо «bitrix24»)
    const nums = s.match(/\d{3,}/g);
    if (!nums?.length) return null;
    id = Number(nums.sort((a, b) => b.length - a.length || Number(b) - Number(a))[0]);
  }
  return Number.isInteger(id) && id > 0 ? id : null;
}

// Форма результата audit_engine.audit_deal (то, что лежит в result jsonb).
export type RecoveryFactor = { label: string; weight: number; kind: string };
export type AuditResult = {
  deal_id: number;
  title: string | null;
  company: string | null;
  recovery: {
    score: number;
    band: 'low' | 'mid' | 'hi';
    expected_value: number;
    factors: RecoveryFactor[];
    llm_adjustment?: number;
  };
  signals: Record<string, unknown>;
  failure_tags: { tag: string; label: string }[];
  call_recordings?: { date?: string; duration?: number; status?: string }[];
  narrative: {
    summary?: string;
    real_cause?: string;
    verdict_band_text?: string;
    chronology?: { date?: string; event?: string; who?: string }[];
    key_quotes?: { date?: string; speaker?: string; quote?: string; why?: string }[];
    call_analysis?: {
      date?: string; summary?: string; client_tone?: string;
      objections?: string[]; manager_quality?: string; commitment?: string;
    }[];
    failures?: { title?: string; detail?: string; pattern_id?: string; severity?: string }[];
    pattern_matches?: { pattern_id?: string; note?: string }[];
    what_went_well?: string[];
    what_would_save_it?: string[];
    next_steps?: string[];
    first_task?: { title?: string; description?: string };
    systemic_conclusions?: { broken?: string; fix?: string }[];
    recovery_rationale?: string;
  };
};

export type DealAudit = {
  id: number;
  dealId: number;
  title: string | null;
  company: string | null;
  status: string;
  stage: string | null;
  error: string | null;
  score: number | null;
  band: string | null;
  expectedValue: number | null;
  result: AuditResult | null;
  requestedBy: number | null;
  returnedToWork: boolean;
  taskId: number | null;
  createdAt: Date | string | null;
  updatedAt: Date | string | null;
  requestedByName?: string | null; // ФИО заказчика аудита (из users по requested_by)
  stageLabel?: string | null;      // стадия сделки на момент аудита
};

function map(r: typeof dealAudits.$inferSelect): DealAudit {
  return {
    id: r.id, dealId: r.dealId, title: r.title, company: r.company,
    status: r.status, stage: r.stage, error: r.error,
    score: r.score, band: r.band, expectedValue: r.expectedValue,
    result: (r.result as AuditResult | null) ?? null,
    requestedBy: r.requestedBy, returnedToWork: r.returnedToWork, taskId: r.taskId,
    createdAt: r.createdAt, updatedAt: r.updatedAt,
  };
}

export async function listAudits(limit = 50): Promise<DealAudit[]> {
  const rows = await db.select().from(dealAudits).orderBy(desc(dealAudits.createdAt)).limit(limit);
  const audits = rows.map(map);
  // резолвим ФИО заказчиков одним запросом
  const ids = [...new Set(audits.map((a) => a.requestedBy).filter((v): v is number => !!v))];
  const nameById = new Map<number, string>();
  if (ids.length) {
    const us = await db.select({ id: users.bitrixId, name: users.name }).from(users).where(inArray(users.bitrixId, ids));
    us.forEach((u) => nameById.set(u.id, u.name));
  }
  for (const a of audits) {
    a.requestedByName = a.requestedBy ? (nameById.get(a.requestedBy) ?? null) : null;
    a.stageLabel = stageLabelOf(a.result);
  }
  return audits;
}

export async function getAudit(id: number): Promise<DealAudit | null> {
  const rows = await db.select().from(dealAudits).where(eq(dealAudits.id, id)).limit(1);
  return rows[0] ? map(rows[0]) : null;
}

export async function createAudit(dealId: number, requestedBy: number | null): Promise<number> {
  const [row] = await db
    .insert(dealAudits)
    .values({ dealId, requestedBy })
    .returning({ id: dealAudits.id });
  return row.id;
}

export async function markReturnedToWork(id: number, taskId: number | null): Promise<void> {
  await db
    .update(dealAudits)
    .set({ returnedToWork: true, taskId, updatedAt: new Date() })
    .where(eq(dealAudits.id, id));
}

/** Зарегистрировать задачу из аудита в общей таблице задач, чтобы она была видна
 * в «Алертах» (тот же список и тот же sync статусов, что у задач из встреч).
 * meetingId=0 — маркер «задача из аудита, не из встречи». */
export async function recordAuditTask(args: {
  dealId: number;
  taskId: number;
  responsibleId: number;
  title: string;
  deadline?: string;
}): Promise<void> {
  const today = new Date().toISOString().slice(0, 10);
  await db
    .insert(meetingTasks)
    .values({
      reportDate: today,
      meetingId: 0,
      dealId: args.dealId,
      stepKey: `audit:${args.taskId}`,
      taskId: args.taskId,
      responsibleId: args.responsibleId,
      title: args.title,
      deadline: args.deadline ? new Date(args.deadline) : null,
      closed: false,
    })
    .onConflictDoNothing();
}
