import fs from "node:fs";
import path from "node:path";

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function fp(stateDir, name) {
  ensureDir(stateDir);
  return path.join(stateDir, name);
}

function readJson(file, fallback) {
  try {
    if (!fs.existsSync(file)) return fallback;
    const data = JSON.parse(fs.readFileSync(file, "utf8"));
    return data ?? fallback;
  } catch {
    return fallback;
  }
}

function writeJson(file, data) {
  ensureDir(path.dirname(file));
  fs.writeFileSync(file, JSON.stringify(data, null, 2));
}

export function loadOAuthStore(stateDir) {
  return readJson(fp(stateDir, "agenda_oauth.json"), { google: null, bitrix: null, states: [] });
}

export function saveOAuthStore(stateDir, data) {
  writeJson(fp(stateDir, "agenda_oauth.json"), data);
}

export function saveProviderTokens(stateDir, provider, tokenData) {
  const st = loadOAuthStore(stateDir);
  st[provider] = {
    ...tokenData,
    saved_at: new Date().toISOString()
  };
  if (Array.isArray(st.states)) st.states = st.states.slice(-50);
  saveOAuthStore(stateDir, st);
}

export function getProviderTokens(stateDir, provider) {
  const st = loadOAuthStore(stateDir);
  return st[provider] || null;
}

export function saveOAuthState(stateDir, provider, stateValue, expiresMinutes = 20) {
  const st = loadOAuthStore(stateDir);
  const expiresAt = Date.now() + expiresMinutes * 60 * 1000;
  st.states = (st.states || []).filter((x) => Number(x.expiresAt || 0) > Date.now());
  st.states.push({ provider, state: stateValue, expiresAt, createdAt: new Date().toISOString() });
  saveOAuthStore(stateDir, st);
}

export function consumeOAuthState(stateDir, provider, stateValue) {
  const st = loadOAuthStore(stateDir);
  const now = Date.now();
  st.states = (st.states || []).filter((x) => Number(x.expiresAt || 0) > now);
  const found = st.states.find((x) => x.provider === provider && x.state === stateValue);
  st.states = st.states.filter((x) => !(x.provider === provider && x.state === stateValue));
  saveOAuthStore(stateDir, st);
  return !!found;
}

export function loadAgendaSyncStatus(stateDir) {
  return readJson(fp(stateDir, "agenda_sync_status.json"), {
    google: { connected: false, last_success_at: null, last_error: null },
    bitrix: { connected: false, last_success_at: null, last_error: null },
    todo: { connected: false, last_success_at: null, last_error: null }
  });
}

export function markAgendaSync(stateDir, provider, ok, errorMessage = null) {
  const st = loadAgendaSyncStatus(stateDir);
  if (!st[provider]) st[provider] = { connected: false, last_success_at: null, last_error: null };
  st[provider].connected = !!ok;
  if (ok) {
    st[provider].last_success_at = new Date().toISOString();
    st[provider].last_error = null;
  } else if (errorMessage) {
    st[provider].last_error = String(errorMessage).slice(0, 500);
  }
  writeJson(fp(stateDir, "agenda_sync_status.json"), st);
}

export function loadBitrixUsersCache(stateDir) {
  return readJson(fp(stateDir, "bitrix_users_cache.json"), { saved_at: null, users: {} });
}

export function saveBitrixUsersCache(stateDir, data) {
  const payload = {
    saved_at: new Date().toISOString(),
    users: data?.users || {}
  };
  writeJson(fp(stateDir, "bitrix_users_cache.json"), payload);
}
