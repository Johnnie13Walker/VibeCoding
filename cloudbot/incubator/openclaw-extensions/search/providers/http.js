const DEFAULT_TIMEOUT_MS = 10_000;
const RETRYABLE_STATUSES = new Set([500, 502, 503, 504]);

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function normalizeError(err) {
  const message = err?.message || String(err);
  if (err?.name === 'AbortError') return { code: 'timeout', message };
  return { code: 'network_error', message };
}

export async function requestJson(url, {
  method = 'GET',
  headers,
  body,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  retries = 2,
  retryBaseDelayMs = 300,
} = {}) {
  let lastError;

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const res = await fetch(url, {
        method,
        headers,
        body,
        signal: controller.signal,
      });

      const text = await res.text();
      let data = null;
      try {
        data = text ? JSON.parse(text) : null;
      } catch {
        data = { rawText: text };
      }

      if (!res.ok) {
        const retryable = RETRYABLE_STATUSES.has(res.status);
        const err = {
          code: `http_${res.status}`,
          status: res.status,
          message: `HTTP ${res.status}`,
          response: data,
          retryable,
        };

        if (!retryable || attempt === retries) throw err;
        await sleep(retryBaseDelayMs * (2 ** attempt));
        continue;
      }

      return { ok: true, status: res.status, data };
    } catch (err) {
      const normalized = err?.status ? err : normalizeError(err);
      const retryable = normalized.retryable ?? normalized.code === 'timeout';
      lastError = normalized;
      if (!retryable || attempt === retries) throw normalized;
      await sleep(retryBaseDelayMs * (2 ** attempt));
    } finally {
      clearTimeout(timer);
    }
  }

  throw lastError || { code: 'unknown_error', message: 'Unknown request failure' };
}
