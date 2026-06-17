import { execSync } from 'node:child_process';
import pkg from '../../package.json' with { type: 'json' };
import { getBitrixConfig, pingBitrix } from '../../provider.bitrix.js';
import { gcalConfigured, pingGcal } from '../../provider.gcal.js';
import { getTodoConfig, pingTodo } from '../../provider.todo.js';
import { getWhoopStatus, pingWhoop } from '../../provider.whoop.js';

const MOSCOW_TZ = 'Europe/Moscow';
const PING_TIMEOUT_MS = 4000;

function hasValue(v) {
  return Boolean(String(v || '').trim());
}

function yesNo(v) {
  return v ? 'есть' : 'нет';
}

function formatMsk(date) {
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone: MOSCOW_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).format(date);
}

function moscowParts(date) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: MOSCOW_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date);
  const map = Object.fromEntries(parts.map((p) => [p.type, p.value]));
  return {
    year: Number(map.year),
    month: Number(map.month),
    day: Number(map.day),
    hour: Number(map.hour),
    minute: Number(map.minute),
  };
}

function nextRunLabel(now, hhmm) {
  const m = String(hhmm || '').match(/^(\d{1,2}):(\d{2})$/);
  if (!m) return 'неизвестно';

  const hh = Number(m[1]);
  const mm = Number(m[2]);
  if (Number.isNaN(hh) || Number.isNaN(mm) || hh < 0 || hh > 23 || mm < 0 || mm > 59) {
    return 'неизвестно';
  }

  const msk = moscowParts(now);
  const nowMinutes = (msk.hour * 60) + msk.minute;
  const targetMinutes = (hh * 60) + mm;
  const dayMark = targetMinutes > nowMinutes ? 'сегодня' : 'завтра';
  return `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')} МСК (${dayMark})`;
}

function asEnabled(v) {
  return ['1', 'true', 'yes', 'on'].includes(String(v || '').trim().toLowerCase());
}

function resolveScheduler(context = {}, now = new Date()) {
  if (typeof context.schedulerStatus === 'string' && context.schedulerStatus.trim()) {
    return {
      source: 'override',
      summary: context.schedulerStatus.trim(),
      morning: { active: null, nextRun: 'неизвестно' },
      evening: { active: null, nextRun: 'неизвестно' },
    };
  }

  const env = context.env || process.env;
  const morningActive = asEnabled(env.MORNING_JOB_ENABLED);
  const eveningActive = asEnabled(env.EVENING_JOB_ENABLED);
  const morningTime = String(env.MORNING_JOB_TIME || '09:30').trim();
  const eveningTime = String(env.EVENING_JOB_TIME || '20:30').trim();

  return {
    source: 'env',
    summary: null,
    morning: {
      active: morningActive,
      nextRun: morningActive ? nextRunLabel(now, morningTime) : 'отключено',
    },
    evening: {
      active: eveningActive,
      nextRun: eveningActive ? nextRunLabel(now, eveningTime) : 'отключено',
    },
  };
}

function resolveAppVersion(context = {}) {
  if (context.appVersion) return String(context.appVersion);
  let hash = '';

  try {
    hash = execSync('git rev-parse --short HEAD', {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch {
    hash = '';
  }

  const version = String(pkg.version || 'dev');
  return hash ? `${version} (${hash})` : version;
}

async function withTimeout(fn, ms) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort('timeout'), ms);

  try {
    return await fn(controller.signal);
  } finally {
    clearTimeout(timeout);
  }
}

function normalizeProviderStatus(result) {
  if (!result || result.configured === false) {
    return 'не настроено';
  }
  if (result.ok) return 'ok';

  const msg = String(result.message || 'ошибка').replace(/\s+/g, ' ').trim();
  return `ошибка (${msg.slice(0, 80)})`;
}

async function providerHealth(context = {}) {
  const providers = [
    {
      name: 'Bitrix',
      isConfigured: () => getBitrixConfig(context).configured,
      healthcheck: (signal) => pingBitrix({ ...context, signal }),
    },
    {
      name: 'ToDo',
      isConfigured: () => getTodoConfig(context).configured,
      healthcheck: (signal) => pingTodo({ ...context, signal }),
    },
    {
      name: 'Google Calendar',
      isConfigured: () => gcalConfigured(context),
      healthcheck: (signal) => pingGcal({ ...context, signal }),
    },
    {
      name: 'WHOOP',
      isConfigured: () => getWhoopStatus(context).configured,
      healthcheck: (signal) => pingWhoop({ ...context, signal }),
    },
  ];

  const rows = [];

  for (const provider of providers) {
    if (!provider.isConfigured()) {
      rows.push({ name: provider.name, status: 'не настроено' });
      continue;
    }

    try {
      const result = await withTimeout((signal) => provider.healthcheck(signal), PING_TIMEOUT_MS);
      rows.push({ name: provider.name, status: normalizeProviderStatus(result) });
    } catch (err) {
      const msg = String(err?.message || err || 'timeout').replace(/\s+/g, ' ').trim();
      rows.push({ name: provider.name, status: `ошибка (${msg.slice(0, 80)})` });
    }
  }

  return rows;
}

function resolveConfig(context = {}) {
  const env = context.env || process.env;

  return [
    ['TELEGRAM_BOT_TOKEN', hasValue(env.TELEGRAM_BOT_TOKEN)],
    ['TELEGRAM_OWNER_ID', hasValue(env.TELEGRAM_OWNER_ID)],
    ['TODO_API_TOKEN', hasValue(env.TODO_API_TOKEN || env.TODOIST_API_TOKEN)],
    ['BITRIX_WEBHOOK_BASE', hasValue(env.BITRIX_WEBHOOK_BASE || env.BITRIX_API_BASE)],
    ['GOOGLE_SERVICE_ACCOUNT_EMAIL', hasValue(env.GOOGLE_SERVICE_ACCOUNT_EMAIL)],
    ['GCAL_ID', hasValue(env.GCAL_ID)],
    ['WHOOP_ACCESS_TOKEN', hasValue(env.WHOOP_ACCESS_TOKEN)],
  ].map(([name, present]) => ({ name, present }));
}

export async function collectDiagnostics(context = {}) {
  const now = context.now instanceof Date ? context.now : new Date();
  const env = context.env || process.env;
  const scheduler = resolveScheduler(context, now);

  return {
    now,
    timezone: MOSCOW_TZ,
    processTz: String(env.TZ || '').trim() || 'не задан',
    appVersion: resolveAppVersion(context),
    config: resolveConfig(context),
    scheduler,
    providers: await providerHealth(context),
  };
}

export function formatDiagnosticsMessage(diag) {
  const lines = [
    '🩺 Самодиагностика',
    '',
    '🕒 Время и TZ',
    `☑️ Сервер (МСК): ${formatMsk(diag.now)}`,
    `☑️ TZ процесса: ${diag.processTz}`,
    `☑️ TZ целевая: ${diag.timezone}`,
    '',
    '🏷️ Версия',
    `☑️ Приложение: ${diag.appVersion}`,
    '',
    '⚙️ Конфигурация',
    ...diag.config.map((item) => `☑️ ${item.name}: ${yesNo(item.present)}`),
    '',
    '⏰ Планировщик',
  ];

  if (diag.scheduler.source === 'override') {
    lines.push(`☑️ Статус: ${diag.scheduler.summary}`);
  } else {
    lines.push(`☑️ Утро: ${diag.scheduler.morning.active ? 'активно' : 'выключено'}; следующий запуск: ${diag.scheduler.morning.nextRun}`);
    lines.push(`☑️ Вечер: ${diag.scheduler.evening.active ? 'активно' : 'выключено'}; следующий запуск: ${diag.scheduler.evening.nextRun}`);
  }

  lines.push('');
  lines.push('🌐 Пинг провайдеров');
  for (const row of diag.providers) {
    lines.push(`☑️ ${row.name}: ${row.status}`);
  }

  return lines.join('\n');
}
