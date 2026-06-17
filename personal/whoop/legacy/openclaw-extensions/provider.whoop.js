const DEFAULT_WHOOP_API_BASE = 'https://api.prod.whoop.com/developer/v2';
const MOSCOW_TZ = 'Europe/Moscow';
const STEP_KEYS = new Set([
  'steps',
  'step_count',
  'steps_count',
  'total_steps',
  'daily_steps',
  'distance_walked_steps',
]);

function readConfig(ctx = {}) {
  const env = ctx.env || process.env;
  const accessToken = String(env.WHOOP_ACCESS_TOKEN || '').trim();
  const refreshToken = String(env.WHOOP_REFRESH_TOKEN || '').trim();
  const clientId = String(env.WHOOP_CLIENT_ID || '').trim();
  const base = String(env.WHOOP_API_BASE || DEFAULT_WHOOP_API_BASE).trim().replace(/\/+$/, '');
  const configured = Boolean(accessToken || refreshToken || clientId);
  const tokenReady = Boolean(accessToken);
  return { configured, tokenReady, accessToken, refreshToken, clientId, base };
}

function firstRecord(payload) {
  if (!payload) return null;
  if (Array.isArray(payload)) return payload.find((x) => x && typeof x === 'object') || null;
  if (typeof payload !== 'object') return null;
  for (const key of ['records', 'data', 'results', 'items']) {
    const list = payload[key];
    if (Array.isArray(list)) {
      const rec = list.find((x) => x && typeof x === 'object');
      if (rec) return rec;
    }
  }
  return payload;
}

function asNumber(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function recordsList(payload) {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload.filter((x) => x && typeof x === 'object');
  if (typeof payload !== 'object') return [];
  for (const key of ['records', 'data', 'results', 'items']) {
    const list = payload[key];
    if (Array.isArray(list)) return list.filter((x) => x && typeof x === 'object');
  }
  return [payload];
}

function formatMoscowDate(date) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: MOSCOW_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date);
  const map = Object.fromEntries(parts.map((p) => [p.type, p.value]));
  return `${map.year}-${map.month}-${map.day}`;
}

function addDaysToYmd(ymd, delta) {
  const [y, m, d] = String(ymd).split('-').map((x) => Number(x));
  if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) return null;
  const shifted = new Date(Date.UTC(y, m - 1, d + delta));
  return formatMoscowDate(shifted);
}

function moscowDateFromRecord(record) {
  if (!record || typeof record !== 'object') return null;
  for (const key of ['start', 'created_at', 'end', 'date']) {
    const raw = record[key];
    if (!raw) continue;
    const parsed = new Date(raw);
    if (!Number.isFinite(parsed.getTime())) continue;
    return formatMoscowDate(parsed);
  }
  return null;
}

function collectStepCandidates(node, out = []) {
  if (Array.isArray(node)) {
    for (const item of node) collectStepCandidates(item, out);
    return out;
  }
  if (!node || typeof node !== 'object') return out;

  for (const [key, value] of Object.entries(node)) {
    if (STEP_KEYS.has(String(key).toLowerCase())) {
      const v = asNumber(value);
      if (v !== null && v >= 0) out.push(Math.round(v));
    }
    if (value && typeof value === 'object') {
      collectStepCandidates(value, out);
    }
  }
  return out;
}

function extractStepsCount(node) {
  const candidates = collectStepCandidates(node, []);
  if (!candidates.length) return null;
  return Math.max(...candidates);
}

function buildWeeklyStepSummary(records, now = new Date()) {
  const todayMsk = formatMoscowDate(now);
  const endYmd = addDaysToYmd(todayMsk, -1);
  if (!endYmd) return { available: false, days: 7, message: 'не удалось определить дату' };

  const targetDays = [];
  for (let i = 6; i >= 0; i -= 1) {
    targetDays.push(addDaysToYmd(endYmd, -i));
  }
  const validDays = targetDays.filter(Boolean);
  if (validDays.length !== 7) return { available: false, days: 7, message: 'ошибка расчета диапазона дат' };

  const byDay = new Map();
  for (const record of records) {
    const day = moscowDateFromRecord(record);
    if (!day) continue;
    const steps = extractStepsCount(record);
    if (steps === null) continue;
    if (!byDay.has(day) || steps > byDay.get(day)) {
      byDay.set(day, steps);
    }
  }

  const points = validDays
    .map((day) => ({ day, steps: byDay.get(day) }))
    .filter((item) => Number.isFinite(item.steps));

  if (!points.length) {
    return {
      available: false,
      days: 7,
      periodStart: validDays[0],
      periodEnd: validDays[6],
      message: 'шаги за период недоступны',
    };
  }

  let minDay = points[0];
  let maxDay = points[0];
  let total = 0;
  for (const item of points) {
    total += item.steps;
    if (item.steps < minDay.steps) minDay = item;
    if (item.steps > maxDay.steps) maxDay = item;
  }

  return {
    available: true,
    days: 7,
    periodStart: validDays[0],
    periodEnd: validDays[6],
    daysWithData: points.length,
    totalSteps: total,
    avgStepsPerDay: Math.round(total / 7),
    minDay,
    maxDay,
  };
}

async function getWhoopWeeklySteps(ctx = {}) {
  const activityRes = await whoopGet('/activity', ctx, { query: { limit: 21 }, timeoutMs: 7000, retries: 1 });
  if (!activityRes.ok) {
    return {
      ok: false,
      available: false,
      message: activityRes.message || 'ошибка запроса activity',
    };
  }

  const records = recordsList(activityRes.payload);
  if (!records.length) {
    return { ok: true, available: false, message: 'activity вернул пустой ответ' };
  }

  return { ok: true, ...buildWeeklyStepSummary(records) };
}

function sleepMinutesFromRecord(sleep) {
  if (!sleep || typeof sleep !== 'object') return null;

  const keysMinutes = ['total_sleep_duration_minutes', 'total_sleep_time_minutes', 'total_in_bed_time_minutes'];
  for (const key of keysMinutes) {
    const n = asNumber(sleep[key]);
    if (n !== null) return Math.round(n);
  }

  const keysMillis = ['total_sleep_duration_ms', 'total_sleep_duration_milli'];
  for (const key of keysMillis) {
    const n = asNumber(sleep[key]);
    if (n !== null) return Math.round(n / 60000);
  }

  const stage = sleep.score?.stage_summary;
  if (stage && typeof stage === 'object') {
    const totalMs = Number(stage.total_light_sleep_time_milli || 0)
      + Number(stage.total_slow_wave_sleep_time_milli || 0)
      + Number(stage.total_rem_sleep_time_milli || 0);
    if (totalMs > 0) return Math.round(totalMs / 60000);
  }

  return null;
}

function recoveryScoreFromRecord(recovery) {
  if (!recovery || typeof recovery !== 'object') return null;
  return asNumber(recovery.recovery_score)
    ?? asNumber(recovery.score?.recovery_score)
    ?? asNumber(recovery.score);
}

function strainFromRecord(cycle) {
  if (!cycle || typeof cycle !== 'object') return null;
  return asNumber(cycle.strain)
    ?? asNumber(cycle.day_strain)
    ?? asNumber(cycle.score?.strain)
    ?? asNumber(cycle.score);
}

async function whoopGet(path, ctx = {}, { query = {}, timeoutMs = 5000, retries = 1 } = {}) {
  const conf = readConfig(ctx);
  if (!conf.tokenReady) {
    return { ok: false, status: null, message: 'нет WHOOP_ACCESS_TOKEN', payload: null };
  }

  const url = new URL(`${conf.base}${path}`);
  for (const [k, v] of Object.entries(query || {})) {
    if (v === undefined || v === null || v === '') continue;
    url.searchParams.set(k, String(v));
  }

  let lastError = null;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const res = await fetch(url, {
        method: 'GET',
        headers: { Authorization: `Bearer ${conf.accessToken}` },
        signal: controller.signal,
      });
      clearTimeout(timer);

      let payload = null;
      try {
        payload = await res.json();
      } catch {}

      if (!res.ok) {
        lastError = { ok: false, status: res.status, message: `HTTP ${res.status}`, payload };
        if (res.status === 429 || res.status >= 500) continue;
        return lastError;
      }

      return { ok: true, status: res.status, message: 'OK', payload };
    } catch (err) {
      clearTimeout(timer);
      lastError = { ok: false, status: null, message: String(err?.message || err || 'ошибка'), payload: null };
    }
  }

  return lastError || { ok: false, status: null, message: 'ошибка запроса', payload: null };
}

export function getWhoopStatus(ctx = {}) {
  const conf = readConfig(ctx);
  if (!conf.configured) return { configured: false, status: 'не настроен' };
  return { configured: true, status: conf.tokenReady ? 'настроен' : 'частично настроен (нет access token)' };
}

export async function pingWhoop(ctx = {}) {
  const conf = readConfig(ctx);
  if (!conf.configured) {
    return { configured: false, ok: null, message: 'не настроен' };
  }
  if (!conf.tokenReady) {
    return { configured: true, ok: false, message: 'нет WHOOP_ACCESS_TOKEN' };
  }

  const probe = await whoopGet('/user/profile/basic', ctx, { timeoutMs: 5000, retries: 1 });
  if (!probe.ok) {
    return { configured: true, ok: false, message: probe.message };
  }
  return { configured: true, ok: true, message: 'OK' };
}

export async function getWhoopDailySummary(dateQuery = 'сегодня', ctx = {}, options = {}) {
  const conf = readConfig(ctx);
  const includeWeeklySteps = Boolean(options.includeWeeklySteps);
  if (!conf.configured) {
    return {
      configured: false,
      ok: null,
      text: 'WHOOP: не настроен.',
      weeklySteps: includeWeeklySteps
        ? { ok: false, available: false, message: 'WHOOP не настроен' }
        : null,
    };
  }
  if (!conf.tokenReady) {
    return {
      configured: true,
      ok: false,
      text: 'WHOOP: нет WHOOP_ACCESS_TOKEN.',
      weeklySteps: includeWeeklySteps
        ? { ok: false, available: false, message: 'нет WHOOP_ACCESS_TOKEN' }
        : null,
    };
  }

  const requests = [
    whoopGet('/recovery', ctx, { query: { limit: 7 }, timeoutMs: 7000, retries: 1 }),
    whoopGet('/activity/sleep', ctx, { query: { limit: 7 }, timeoutMs: 7000, retries: 1 }),
    whoopGet('/cycle', ctx, { query: { limit: 7 }, timeoutMs: 7000, retries: 1 }),
  ];
  if (includeWeeklySteps) requests.push(getWhoopWeeklySteps(ctx));
  const [recRes, sleepRes, cycleRes, weeklySteps = null] = await Promise.all(requests);

  const recovery = recoveryScoreFromRecord(firstRecord(recRes.payload));
  const sleepMin = sleepMinutesFromRecord(firstRecord(sleepRes.payload));
  const strain = strainFromRecord(firstRecord(cycleRes.payload));

  const hasAnyMetric = recovery !== null || sleepMin !== null || strain !== null;
  const allOk = recRes.ok && sleepRes.ok && cycleRes.ok;

  if (!hasAnyMetric && !allOk) {
    const reason = recRes.message || sleepRes.message || cycleRes.message || 'ошибка';
    return {
      configured: true,
      ok: false,
      text: `WHOOP (${dateQuery}): ошибка (${reason}).`,
      weeklySteps,
    };
  }

  const parts = [];
  parts.push(`WHOOP (${dateQuery}): ${allOk ? 'ok' : 'частично доступен'}.`);
  parts.push(`Восстановление: ${recovery === null ? 'н/д' : `${Math.round(recovery)}%`}`);
  if (sleepMin === null) {
    parts.push('Сон: н/д');
  } else {
    const h = Math.floor(sleepMin / 60);
    const m = sleepMin % 60;
    parts.push(`Сон: ${h}ч ${m}м`);
  }
  parts.push(`Strain: ${strain === null ? 'н/д' : Number(strain).toFixed(1)}`);

  return {
    configured: true,
    ok: allOk || hasAnyMetric,
    text: parts.join('\n'),
    metrics: { recovery, sleepMin, strain },
    weeklySteps,
  };
}
