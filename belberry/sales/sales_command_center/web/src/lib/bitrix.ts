import 'server-only';

import fs from 'node:fs/promises';

const DEFAULT_STATE_PATH =
  '/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json';
const LARISA_BITRIX_ID = 2812;

interface BitrixAuth {
  endpoint: string;
  token: string;
}

interface BitrixResponse<T> {
  result?: T;
  error?: string;
  error_description?: string;
}

export interface BitrixUser {
  bitrixId: number;
  email: string;
  name: string;
}

function flattenParams(
  value: unknown,
  prefix?: string,
  params = new URLSearchParams(),
): URLSearchParams {
  if (value === undefined || value === null) {
    return params;
  }

  if (Array.isArray(value)) {
    value.forEach((item, index) => flattenParams(item, `${prefix}[${index}]`, params));
    return params;
  }

  if (typeof value === 'object') {
    Object.entries(value as Record<string, unknown>).forEach(([key, nested]) => {
      const nextPrefix = prefix ? `${prefix}[${key}]` : key;
      flattenParams(nested, nextPrefix, params);
    });
    return params;
  }

  if (!prefix) {
    throw new Error('Cannot encode Bitrix parameter without a key');
  }

  params.append(prefix, String(value));
  return params;
}

function maskAuth(message: string): string {
  return message.replace(/auth=[^&\s]+/g, 'auth=***');
}

async function loadAuth(): Promise<BitrixAuth> {
  const statePath = process.env.BITRIX_STATE_PATH ?? DEFAULT_STATE_PATH;
  const raw = await fs.readFile(statePath, 'utf8');
  const state = JSON.parse(raw) as {
    auth?: {
      client_endpoint?: string;
      access_token?: string;
    };
  };

  const endpoint = state.auth?.client_endpoint;
  const token = state.auth?.access_token;

  if (!endpoint || !token) {
    throw new Error(`Bitrix auth state is incomplete: ${statePath}`);
  }

  return { endpoint, token };
}

const BITRIX_TIMEOUT_MS = Number(process.env.BITRIX_HTTP_TIMEOUT_MS ?? 6000);
const BITRIX_RETRIES = Math.max(1, Number(process.env.BITRIX_HTTP_RETRIES ?? 3));

async function callBitrix<T>(
  method: string,
  params: Record<string, unknown> = {},
): Promise<T> {
  const auth = await loadAuth();
  const url = new URL(`${auth.endpoint.replace(/\/$/, '')}/${method}.json`);
  const body = flattenParams({ ...params, auth: auth.token }).toString();

  let lastError: unknown;
  for (let attempt = 1; attempt <= BITRIX_RETRIES; attempt += 1) {
    let response: Response;
    try {
      response = await fetch(url, {
        method: 'POST',
        headers: {
          'content-type': 'application/x-www-form-urlencoded',
        },
        body,
        signal: AbortSignal.timeout(BITRIX_TIMEOUT_MS),
      });
    } catch (error) {
      // Сетевой сбой/таймаут к Bitrix частый: у портала ~13 A-записей, часть
      // недоступна с зарубежного сервера → fetch виснет на «мёртвом» IP.
      // Повторяем — новый запрос переподключается и может попасть на живой IP.
      lastError = error;
      continue;
    }

    const payload = (await response.json()) as BitrixResponse<T>;

    if (!response.ok || payload.error) {
      const reason = payload.error_description ?? payload.error ?? response.statusText;
      throw new Error(maskAuth(`Bitrix ${method} failed: ${reason}`));
    }

    return payload.result as T;
  }

  throw new Error(maskAuth(`Bitrix ${method} unreachable: ${String(lastError)}`));
}

export async function findActiveUserByEmail(email: string): Promise<BitrixUser | null> {
  // Адрес в Bitrix может лежать в EMAIL ИЛИ в LOGIN (часто входят по
  // корпоративной почте-логину, поле EMAIL пустое). Пробуем оба фильтра;
  // совпадение проверяем строго по обоим полям — иначе сессия привяжется к чужому.
  const cleaned = email.trim();
  const wanted = cleaned.toLowerCase();
  const matches = (candidate: Record<string, unknown>) =>
    [candidate.EMAIL, candidate.LOGIN].some(
      (value) => String(value ?? '').trim().toLowerCase() === wanted,
    );

  let user: Record<string, unknown> | undefined;
  // В фильтр Bitrix отдаём очищенный адрес: лишний пробел в EMAIL-фильтре
  // даёт 0 строк (проверено на проде) → ложное «Email не найден».
  for (const filter of [
    { EMAIL: cleaned, ACTIVE: 'Y' },
    { LOGIN: cleaned, ACTIVE: 'Y' },
  ]) {
    const result = await callBitrix<Array<Record<string, unknown>>>('user.get', { filter });
    user = result.find(matches);
    if (user) {
      break;
    }
  }

  if (!user) {
    return null;
  }

  const bitrixId = Number(user.ID);
  const resolvedEmail = String(user.EMAIL ?? email);
  const name = [user.NAME, user.LAST_NAME].filter(Boolean).join(' ').trim();

  return {
    bitrixId,
    email: resolvedEmail,
    name: name || resolvedEmail,
  };
}

export async function sendCodeMessage(recipientBitrixId: number, code: string): Promise<void> {
  // OAuth token owner must be Larisa (Bitrix user 2812): im.notify.personal.add sends FROM the token owner.
  await callBitrix('im.notify.personal.add', {
    USER_ID: recipientBitrixId,
    MESSAGE: `Код входа в Global Sales Dashboard: ${code}. Он действует 10 минут.`,
  });
}

/**
 * Текущий ответственный (ASSIGNED_BY_ID) по списку сделок — одним запросом.
 * Используется для фолбэка «менеджер на начало аудита» у старых аудитов, в чьих
 * сигналах не сохранён deal_responsible_id. Возвращает Map<dealId, responsibleId>.
 */
export async function getDealResponsibles(dealIds: number[]): Promise<Map<number, number>> {
  const out = new Map<number, number>();
  const ids = [...new Set(dealIds.filter((v) => Number.isFinite(v) && v > 0))];
  if (!ids.length) return out;
  const rows = await callBitrix<Array<Record<string, unknown>>>('crm.deal.list', {
    filter: { '@ID': ids },
    select: ['ID', 'ASSIGNED_BY_ID'],
  });
  for (const r of rows ?? []) {
    const id = Number(r.ID);
    const resp = Number(r.ASSIGNED_BY_ID);
    if (Number.isFinite(id) && Number.isFinite(resp) && resp > 0) out.set(id, resp);
  }
  return out;
}

export async function assertLarisaToken(): Promise<boolean> {
  const profile = await callBitrix<{ ID?: string | number }>('profile');
  const isLarisa = Number(profile.ID) === LARISA_BITRIX_ID;

  if (!isLarisa) {
    console.warn(
      `BITRIX_STATE_PATH should contain Larisa token (${LARISA_BITRIX_ID}), got ${profile.ID}`,
    );
  }

  return isLarisa;
}

// ── Просрочки сотрудника для detail-страницы /alerts/tasks/[id] (живьём из Bitrix) ──
// Полный scope (OAuth-токен Ларисы) позволяет вебу читать задачи и CRM-дела.
// «<DEADLINE: now» — сравнение по инстанту (UTC ISO ≡ тот же момент, что МСК).

export interface OverdueTaskItem {
  id: number;
  title: string;
  deadline: string | null;
  status: number | null;
  groupId: number | null;
}

export interface OverdueActivityItem {
  id: number;
  subject: string;
  providerTypeId: string | null;
  typeId: number | null;
  endTime: string | null;
  ownerId: number | null;
  ownerTypeId: number | null;
}

/** Просроченные задачи (RESPONSIBLE_ID, дедлайн в прошлом, не завершена). До 50. */
export async function getOverdueTasks(userId: number): Promise<OverdueTaskItem[]> {
  const now = new Date().toISOString();
  const res = await callBitrix<{ tasks?: Array<Record<string, unknown>> }>('tasks.task.list', {
    filter: { RESPONSIBLE_ID: userId, '<DEADLINE': now, '!STATUS': '5' },
    select: ['ID', 'TITLE', 'DEADLINE', 'STATUS', 'GROUP_ID'],
    order: { DEADLINE: 'asc' },
  });
  return (res?.tasks ?? []).map((t) => ({
    id: Number(t.id ?? t.ID),
    title: String(t.title ?? t.TITLE ?? ''),
    deadline: (t.deadline ?? t.DEADLINE ?? null) as string | null,
    status: t.status != null ? Number(t.status) : null,
    groupId: t.groupId ?? t.GROUP_ID ? Number(t.groupId ?? t.GROUP_ID) : null,
  }));
}

/** Просроченные CRM-дела (RESPONSIBLE_ID, COMPLETED=N, END_TIME в прошлом). До 50. */
export async function getOverdueActivities(userId: number): Promise<OverdueActivityItem[]> {
  const now = new Date().toISOString();
  const res = await callBitrix<Array<Record<string, unknown>>>('crm.activity.list', {
    filter: { RESPONSIBLE_ID: userId, COMPLETED: 'N', '<END_TIME': now },
    select: ['ID', 'SUBJECT', 'TYPE_ID', 'PROVIDER_TYPE_ID', 'END_TIME', 'DEADLINE', 'OWNER_ID', 'OWNER_TYPE_ID'],
    order: { END_TIME: 'asc' },
  });
  return (res ?? []).map((a) => ({
    id: Number(a.ID),
    subject: String(a.SUBJECT ?? ''),
    providerTypeId: (a.PROVIDER_TYPE_ID ?? null) as string | null,
    typeId: a.TYPE_ID != null ? Number(a.TYPE_ID) : null,
    endTime: (a.END_TIME ?? null) as string | null,
    ownerId: a.OWNER_ID != null ? Number(a.OWNER_ID) : null,
    ownerTypeId: a.OWNER_TYPE_ID != null ? Number(a.OWNER_TYPE_ID) : null,
  }));
}
