import 'server-only';
import { readFile } from 'node:fs/promises';

// Запись в Bitrix из веба (смена стадии + постановка задачи при «вернуть в работу»).
// Изолировано от read-only lib/bitrix.ts. Решение заказчика 23.06: веб пишет напрямую.
const STATE_PATH =
  process.env.BITRIX_STATE_PATH ??
  '/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json';

// Постановщик задач из аудита — Управляющий партнёр (как в task_planner раннера).
export const AUDIT_TASK_CREATOR = Number(process.env.AUDIT_TASK_CREATOR ?? 12);

async function loadAuth(): Promise<{ endpoint: string; token: string }> {
  const payload = JSON.parse(await readFile(STATE_PATH, 'utf8')).payload;
  return {
    endpoint: String(payload['auth[client_endpoint]']).replace(/\/$/, ''),
    token: payload['auth[access_token]'],
  };
}

function flatten(params: Record<string, unknown>, prefix = '', out: [string, string][] = []) {
  for (const [k, v] of Object.entries(params)) {
    const key = prefix ? `${prefix}[${k}]` : k;
    if (v === null || v === undefined) continue;
    if (Array.isArray(v)) {
      v.forEach((item, i) => flatten({ [i]: item }, key, out));
    } else if (typeof v === 'object') {
      flatten(v as Record<string, unknown>, key, out);
    } else {
      out.push([key, String(v)]);
    }
  }
  return out;
}

export async function bitrixWrite<T = unknown>(
  method: string,
  params: Record<string, unknown>,
): Promise<T> {
  const { endpoint, token } = await loadAuth();
  const body = new URLSearchParams([['auth', token], ...flatten(params)]).toString();
  const res = await fetch(`${endpoint}/${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  const json = await res.json();
  if (json?.error) throw new Error(`${method}: ${json.error_description ?? json.error}`);
  return json.result as T;
}

// Воронка Телемаркетинг и её стартовая стадия (для перевода сделки в ТМ).
export const TM_CATEGORY_ID = 50;
export const TM_START_STAGE = 'C50:NEW'; // «К обзвону»

/** Текущий ответственный сделки (ASSIGNED_BY_ID) — чтобы понять, вернули ли её
 * тому же менеджеру или передали другому. */
export async function getDealResponsible(dealId: number): Promise<number | null> {
  const deal = await bitrixWrite<{ ASSIGNED_BY_ID?: string }>('crm.deal.get', { id: dealId });
  const id = Number(deal?.ASSIGNED_BY_ID);
  return Number.isInteger(id) && id > 0 ? id : null;
}

/** Вернуть сделку в работу: сменить стадию и (если задан) переназначить ответственного. */
export async function reopenDeal(dealId: number, stageId: string, responsibleId?: number): Promise<void> {
  const fields: Record<string, unknown> = { STAGE_ID: stageId };
  if (responsibleId && responsibleId > 0) fields.ASSIGNED_BY_ID = responsibleId;
  await bitrixWrite('crm.deal.update', { id: dealId, fields });
}

/** Перевести сделку в воронку Телемаркетинг на телемаркетолога (для повторного обзвона). */
export async function transferToTelemarketing(dealId: number, responsibleId: number): Promise<void> {
  await bitrixWrite('crm.deal.update', {
    id: dealId,
    fields: { CATEGORY_ID: TM_CATEGORY_ID, STAGE_ID: TM_START_STAGE, ASSIGNED_BY_ID: responsibleId },
  });
}

export async function createDealTask(args: {
  dealId: number;
  title: string;
  description: string;
  responsibleId: number;
  deadline?: string; // ISO с таймзоной
}): Promise<number> {
  const fields: Record<string, unknown> = {
    TITLE: args.title,
    DESCRIPTION: args.description,
    RESPONSIBLE_ID: args.responsibleId,
    CREATED_BY: AUDIT_TASK_CREATOR,
    UF_CRM_TASK: [`D_${args.dealId}`],
  };
  if (args.deadline) fields.DEADLINE = args.deadline;
  const res = await bitrixWrite<{ task: { id: number } }>('tasks.task.add', { fields });
  return res.task.id;
}
