import { promisify } from 'node:util';
import { execFile } from 'node:child_process';

const execFileAsync = promisify(execFile);

export async function getMeetings(dateQuery = 'сегодня') {
  try {
    const mod = await import('./gcal-query.mjs');
    const queryScheduleByText = mod?.queryScheduleByText;
    if (typeof queryScheduleByText !== 'function') {
      return { ok: false, text: 'Ошибка календаря: queryScheduleByText не найден' };
    }
    const text = await queryScheduleByText(dateQuery, { sendTelegram: false });
    return { ok: true, text: String(text || '').trim() || 'Пусто.' };
  } catch (err) {
    return { ok: false, text: `Ошибка календаря: ${String(err?.message || err || 'unknown')}` };
  }
}

function hasCalendarCredentials(env = process.env) {
  return Boolean(
    String(env.BITRIX_WEBHOOK_BASE || '').trim()
    || String(env.BITRIX_API_BASE || '').trim()
    || String(env.BITRIX_PORTAL_URL || '').trim()
    || String(env.GOOGLE_SERVICE_ACCOUNT_JSON || '').trim(),
  );
}

function allowCalendarMock(env = process.env) {
  return String(env.ALLOW_CALENDAR_MOCK || '0').trim() === '1';
}

function toDateLabel(date) {
  const m = String(date || '').match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return String(date || '');
  return `${m[3]}.${m[2]}.${m[1]}`;
}

function buildCreateText(payload) {
  const title = String(payload.title || 'Встреча').trim();
  const date = toDateLabel(payload.date);
  const time = String(payload.time || '').trim();
  const duration = Number(payload.duration || 30);
  const attendees = Array.isArray(payload.attendees) ? payload.attendees.filter(Boolean).join(', ') : '';

  const who = attendees ? ` с ${attendees}` : '';
  return `создай встречу ${title}${who} на ${date} в ${time} на ${duration} минут`;
}

export async function createMeeting(payload, ctx = {}) {
  const env = ctx.env || process.env;

  const title = String(payload?.title || 'Встреча').trim();
  const date = String(payload?.date || '').trim();
  const time = String(payload?.time || '').trim();
  const duration = Number(payload?.duration || 30);
  const attendees = Array.isArray(payload?.attendees) ? payload.attendees : [];

  if (!date || !time) {
    return { ok: false, text: 'Недостаточно данных: дата или время не заполнены.' };
  }

  if (!hasCalendarCredentials(env)) {
    if (!allowCalendarMock(env)) {
      return {
        ok: false,
        text: 'Календарь не настроен: встреча не создана. Настройте BITRIX_WEBHOOK_BASE/BITRIX_API_BASE/BITRIX_PORTAL_URL или включите ALLOW_CALENDAR_MOCK=1 для теста.',
      };
    }
    const summary = [
      '✅ Встреча создана (mock-режим, провайдер календаря не настроен)',
      `${title}`,
      `${toDateLabel(date)} ${time} (${duration} мин)`,
      attendees.length ? `Участники: ${attendees.join(', ')}` : 'Участники: не указаны',
    ].join('\n');
    return { ok: true, text: summary, mocked: true };
  }

  try {
    const requestText = buildCreateText({ title, date, time, duration, attendees });
    const { stdout } = await execFileAsync('node', ['bitrix-add-event.mjs', requestText], {
      cwd: ctx.cwd || process.cwd(),
      env: { ...process.env, ...env, TZ: 'Europe/Moscow' },
      timeout: 30_000,
      maxBuffer: 1024 * 1024,
    });

    const out = String(stdout || '').trim();
    if (!out) return { ok: false, text: 'Провайдер календаря вернул пустой ответ.' };
    return { ok: true, text: out };
  } catch (err) {
    return { ok: false, text: String(err?.message || err || 'unknown') };
  }
}

export function gcalConfigured(ctx = {}) {
  const env = ctx.env || process.env;
  return Boolean(
    String(env.BITRIX_WEBHOOK_BASE || '').trim()
    || String(env.GCAL_ID || '').trim()
    || String(env.GOOGLE_SERVICE_ACCOUNT_EMAIL || '').trim(),
  );
}

export async function pingGcal(ctx = {}) {
  if (!gcalConfigured(ctx)) {
    return { configured: false, ok: null, message: 'не настроено' };
  }

  const env = ctx.env || process.env;
  const probeUrl = String(env.GCAL_HEALTHCHECK_URL || '').trim();
  if (!probeUrl) {
    return { configured: true, ok: true, message: 'базовая проверка конфигурации' };
  }

  try {
    const res = await fetch(probeUrl, {
      method: 'GET',
      signal: ctx.signal,
    });
    if (!res.ok) return { configured: true, ok: false, message: `HTTP ${res.status}` };
    return { configured: true, ok: true, message: 'OK' };
  } catch (err) {
    return { configured: true, ok: false, message: String(err?.message || err || 'ошибка') };
  }
}
