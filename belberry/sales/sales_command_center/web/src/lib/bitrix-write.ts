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

export async function updateDealStage(dealId: number, stageId: string): Promise<void> {
  await bitrixWrite('crm.deal.update', { id: dealId, fields: { STAGE_ID: stageId } });
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
