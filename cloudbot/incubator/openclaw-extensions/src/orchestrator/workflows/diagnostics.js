import { execSync } from 'node:child_process';
import pkg from '../../../package.json' with { type: 'json' };
import { pingBitrix } from '../../../provider.bitrix.js';
import { gcalConfigured } from '../../../provider.gcal.js';
import { pingTodo } from '../../../provider.todo.js';
import { pingWhoop } from '../../../provider.whoop.js';

function yesNo(v) {
  return v ? 'да' : 'нет';
}

function pingLabel(result) {
  if (!result.configured) return 'не настроен';
  if (result.ok) return 'ok';
  return `ошибка (${result.message})`;
}

function resolveAppVersion(ctx = {}) {
  if (ctx.appVersion) return String(ctx.appVersion);
  try {
    const hash = execSync('git rev-parse --short HEAD', {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
    if (hash) return hash;
  } catch {}
  return pkg.version || 'dev';
}

function resolveSchedulerStatus(ctx = {}) {
  if (typeof ctx.schedulerStatus === 'string') return ctx.schedulerStatus;
  const env = ctx.env || process.env;
  const asEnabled = (v) => ['1', 'true', 'yes', 'on'].includes(String(v || '').trim().toLowerCase());
  const hasMorning = asEnabled(env.MORNING_JOB_ENABLED);
  const hasEvening = asEnabled(env.EVENING_JOB_ENABLED);
  if (hasMorning || hasEvening) {
    return `утро=${hasMorning ? 'вкл' : 'выкл'}, вечер=${hasEvening ? 'вкл' : 'выкл'}`;
  }
  return 'не обнаружен';
}

export async function runDiagnosticsWorkflow(_input, ctx = {}) {
  const env = ctx.env || process.env;
  const bitrix = await pingBitrix(ctx);
  const todo = await pingTodo(ctx);
  const whoop = await pingWhoop(ctx);
  const timezone = 'Europe/Moscow';
  const storePath = String(env.CONTACTS_DB_PATH || './data/contacts.sqlite');

  const lines = [
    'Диагностика бота:',
    `TZ=${timezone}`,
    `Версия приложения: ${resolveAppVersion(ctx)}`,
    `TELEGRAM_BOT_TOKEN: ${yesNo(String(env.TELEGRAM_BOT_TOKEN || '').trim())}`,
    `TELEGRAM_OWNER_ID: ${yesNo(String(env.TELEGRAM_OWNER_ID || '').trim())}`,
    `TODO_API_TOKEN: ${yesNo(String(env.TODO_API_TOKEN || env.TODOIST_API_TOKEN || '').trim())}`,
    `BITRIX token/base: ${yesNo(String(env.BITRIX_WEBHOOK_BASE || env.BITRIX_API_BASE || '').trim())}`,
    `BITRIX ping: ${pingLabel(bitrix)}`,
    `TODO ping: ${pingLabel(todo)}`,
    `WHOOP ping: ${pingLabel(whoop)}`,
    `GCAL: ${gcalConfigured(ctx) ? 'настроен' : 'не настроен'}`,
    `Планировщик: ${resolveSchedulerStatus(ctx)}`,
    `Путь к хранилищу: ${storePath}`,
  ];

  return { handled: true, reply: lines.join('\n') };
}
