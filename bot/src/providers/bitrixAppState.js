import path from "node:path";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";

export class BitrixAppError extends Error {
  constructor(message, { code = "", category = "error", httpStatus = undefined } = {}) {
    super(String(message || "Bitrix app error"));
    this.name = "BitrixAppError";
    this.code = String(code || "");
    this.category = String(category || "error");
    this.httpStatus = httpStatus;
  }
}

export function isBitrixAppNotConfiguredError(error) {
  return error instanceof BitrixAppError && error.category === "not_configured";
}

function pick(payload, ...keys) {
  for (const key of keys) {
    const value = payload?.[key];
    if (value !== undefined && value !== null && value !== "") {
      return String(value).trim();
    }
  }
  return "";
}

function payloadHasAuth(payload) {
  return Boolean(
    pick(payload, "AUTH_ID", "auth_id", "access_token", "auth[access_token]") &&
      pick(payload, "client_endpoint", "CLIENT_ENDPOINT", "auth[client_endpoint]")
  );
}

function parseSavedAt(value) {
  const ts = Date.parse(String(value || "").trim());
  return Number.isFinite(ts) ? ts : 0;
}

function toStateView(record, filePath) {
  const payload = record.payload || {};
  return {
    path: filePath,
    record,
    payload,
    savedAtTs: parseSavedAt(record.saved_at),
    accessToken: pick(payload, "AUTH_ID", "auth_id", "access_token", "auth[access_token]"),
    refreshToken: pick(payload, "REFRESH_ID", "refresh_id", "refresh_token", "auth[refresh_token]"),
    clientEndpoint: pick(payload, "client_endpoint", "CLIENT_ENDPOINT", "auth[client_endpoint]").replace(/\/$/, ""),
    serverEndpoint: pick(payload, "server_endpoint", "SERVER_ENDPOINT", "auth[server_endpoint]").replace(/\/$/, ""),
    domain: pick(payload, "DOMAIN", "domain", "auth[domain]")
  };
}

async function readStateRecord(filePath) {
  try {
    const raw = JSON.parse(await readFile(filePath, "utf-8"));
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      return null;
    }
    if (!payloadHasAuth(raw.payload || {})) {
      return null;
    }
    return toStateView(raw, filePath);
  } catch {
    return null;
  }
}

export async function loadBitrixAppState({ config }) {
  const explicitPath = String(config.bitrixAppInstallStateFile || "").trim();
  const stateDir = String(config.bitrixAppStateDir || "").trim();
  const candidates = [];

  if (explicitPath) {
    candidates.push(explicitPath);
  } else if (stateDir) {
    candidates.push(path.join(stateDir, "handler.latest.json"));
    candidates.push(path.join(stateDir, "install.latest.json"));
  } else {
    throw new BitrixAppError("App OAuth state Bitrix не задан", {
      code: "APP_STATE_NOT_CONFIGURED",
      category: "not_configured"
    });
  }

  const states = [];
  for (const candidate of candidates) {
    const record = await readStateRecord(candidate);
    if (record) states.push(record);
  }

  if (states.length === 0) {
    throw new BitrixAppError("App OAuth state Bitrix не найден", {
      code: "APP_STATE_NOT_FOUND",
      category: "not_configured"
    });
  }

  states.sort((left, right) => right.savedAtTs - left.savedAtTs);
  return states[0];
}

async function persistState(state) {
  await mkdir(path.dirname(state.path), { recursive: true });
  const targetRecord = {
    ...state.record,
    payload: state.payload
  };
  const tmpPath = `${state.path}.tmp`;
  await writeFile(tmpPath, JSON.stringify(targetRecord, null, 2), "utf-8");
  await rename(tmpPath, state.path);
}

function buildRefreshUrls(state, config) {
  const candidates = [];
  const fromConfig = String(config.bitrixOauthTokenUrl || "").trim();
  if (fromConfig) candidates.push(fromConfig);

  if (state.serverEndpoint) {
    try {
      const url = new URL(state.serverEndpoint);
      candidates.push(`${url.protocol}//${url.host}/oauth/token/`);
    } catch {}
  }

  if (state.domain) {
    candidates.push(`https://${state.domain}/oauth/token/`);
  }

  candidates.push("https://oauth.bitrix.info/oauth/token/");
  candidates.push("https://oauth.bitrix24.tech/oauth/token/");

  return [...new Set(candidates.map((item) => String(item).replace(/\/?$/, "/")).filter(Boolean))];
}

function flattenParams(params, prefix = "", entries = []) {
  if (params === null || params === undefined) return entries;

  if (Array.isArray(params)) {
    for (const value of params) {
      flattenParams(value, `${prefix}[]`, entries);
    }
    return entries;
  }

  if (typeof params === "object") {
    for (const [key, value] of Object.entries(params)) {
      const nextPrefix = prefix ? `${prefix}[${key}]` : key;
      flattenParams(value, nextPrefix, entries);
    }
    return entries;
  }

  entries.push([prefix, String(params)]);
  return entries;
}

async function parseBitrixResponse(response, endpoint) {
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    throw new BitrixAppError("Bitrix вернул невалидный JSON", {
      code: "INVALID_JSON",
      httpStatus: response.status
    });
  }

  const errorCode = String(payload?.error || "").trim();
  if (!response.ok || errorCode) {
    const errorDescription = String(payload?.error_description || payload?.error || `Bitrix HTTP ${response.status}`).trim();
    let category = "error";
    const upperCode = errorCode.toUpperCase();
    if (upperCode === "EXPIRED_TOKEN") category = "access_denied";
    if (upperCode.includes("DENIED") || upperCode.includes("SCOPE")) category = "access_denied";
    if (upperCode.includes("METHOD_NOT_FOUND")) category = "method_not_found";
    throw new BitrixAppError(errorDescription.replace(endpoint, "bitrix-endpoint"), {
      code: errorCode || `HTTP_${response.status}`,
      category,
      httpStatus: response.status
    });
  }

  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new BitrixAppError("Bitrix вернул неожиданный формат ответа", {
      code: "INVALID_PAYLOAD",
      httpStatus: response.status
    });
  }
  return payload;
}

async function postForm(url, params, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const body = new URLSearchParams();
    for (const [key, value] of flattenParams(params)) {
      body.append(key, value);
    }
    return await fetch(url, {
      method: "POST",
      body,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      signal: controller.signal
    });
  } catch (error) {
    throw new BitrixAppError(String(error?.message || error), { code: "REQUEST_FAILED" });
  } finally {
    clearTimeout(timer);
  }
}

async function callPayloadWithState({ state, method, params = {}, timeoutMs }) {
  if (!state.clientEndpoint || !state.accessToken) {
    throw new BitrixAppError("В app OAuth state Bitrix нет access token", {
      code: "APP_STATE_INVALID",
      category: "not_configured"
    });
  }

  const endpoint = `${state.clientEndpoint}/${method}.json`;
  const response = await postForm(
    endpoint,
    {
      auth: state.accessToken,
      ...params
    },
    timeoutMs
  );
  return parseBitrixResponse(response, state.clientEndpoint);
}

async function refreshAccessToken({ state, config }) {
  const clientId = String(config.bitrixClientId || "").trim();
  const clientSecret = String(config.bitrixClientSecret || "").trim();
  if (!clientId || !clientSecret) {
    throw new BitrixAppError("Для app OAuth Bitrix не заданы client_id/client_secret", {
      code: "APP_CLIENT_NOT_CONFIGURED",
      category: "not_configured"
    });
  }
  if (!state.refreshToken) {
    throw new BitrixAppError("В app OAuth state Bitrix нет refresh token", {
      code: "APP_REFRESH_NOT_FOUND",
      category: "not_configured"
    });
  }

  let lastError = null;
  for (const refreshUrl of buildRefreshUrls(state, config)) {
    try {
      const response = await postForm(
        refreshUrl,
        {
          grant_type: "refresh_token",
          client_id: clientId,
          client_secret: clientSecret,
          refresh_token: state.refreshToken
        },
        config.bitrixTimeoutMs
      );
      const payload = await parseBitrixResponse(response, refreshUrl);
      const accessToken = String(payload.access_token || "").trim();
      const refreshToken = String(payload.refresh_token || "").trim();
      const clientEndpoint = String(payload.client_endpoint || state.clientEndpoint).trim().replace(/\/$/, "");

      if (!accessToken || !refreshToken || !clientEndpoint) {
        throw new BitrixAppError("Bitrix OAuth refresh вернул неполный payload", {
          code: "REFRESH_INVALID_PAYLOAD"
        });
      }

      state.payload["auth[access_token]"] = accessToken;
      state.payload["auth[refresh_token]"] = refreshToken;
      state.payload["auth[client_endpoint]"] = clientEndpoint;
      if (payload.server_endpoint) {
        state.payload["auth[server_endpoint]"] = String(payload.server_endpoint).replace(/\/$/, "");
      }
      if (payload.domain) {
        state.payload["auth[domain]"] = String(payload.domain).trim();
      }
      state.record.saved_at = new Date().toISOString();
      state.record.auth_refreshed_at = state.record.saved_at;
      await persistState(state);
      return toStateView(state.record, state.path);
    } catch (error) {
      lastError = error;
    }
  }

  throw new BitrixAppError(`Bitrix OAuth refresh не удался: ${String(lastError?.message || "unknown error")}`, {
    code: String(lastError?.code || "REFRESH_FAILED"),
    category: String(lastError?.category || "error"),
    httpStatus: lastError?.httpStatus
  });
}

async function callBitrixPayload({ config, method, params = {} }) {
  let state = await loadBitrixAppState({ config });
  try {
    return await callPayloadWithState({
      state,
      method,
      params,
      timeoutMs: config.bitrixTimeoutMs
    });
  } catch (error) {
    const upperCode = String(error?.code || "").toUpperCase();
    const shouldRefresh = error?.httpStatus === 401 || upperCode === "EXPIRED_TOKEN";
    if (!shouldRefresh) throw error;
    state = await refreshAccessToken({ state, config });
    return await callPayloadWithState({
      state,
      method,
      params,
      timeoutMs: config.bitrixTimeoutMs
    });
  }
}

export async function callBitrixMethod({ config, method, params = {} }) {
  const payload = await callBitrixPayload({ config, method, params });
  return payload?.result;
}

function extractResultList(result) {
  if (Array.isArray(result)) {
    return result.filter((item) => item && typeof item === "object");
  }
  if (result && typeof result === "object") {
    for (const key of ["items", "tasks", "events"]) {
      if (Array.isArray(result[key])) {
        return result[key].filter((item) => item && typeof item === "object");
      }
    }
  }
  return [];
}

export async function listBitrixMethod({ config, method, params = {}, limit = undefined }) {
  const items = [];
  let start = 0;

  while (true) {
    const payload = await callBitrixPayload({
      config,
      method,
      params: { ...params, start }
    });
    const chunk = extractResultList(payload?.result);
    items.push(...chunk);
    if (limit && items.length >= limit) {
      return items.slice(0, limit);
    }

    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      break;
    }
    const nextValue = payload.next;
    const nextStart = Number(nextValue);
    if (!chunk.length || !Number.isFinite(nextStart) || nextStart <= start) {
      break;
    }
    start = nextStart;
  }

  return limit ? items.slice(0, limit) : items;
}
