import crypto from "node:crypto";
import { consumeOAuthState, getProviderTokens, markAgendaSync, saveOAuthState, saveProviderTokens } from "../state.mjs";

const AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth";
const TOKEN_URL = "https://oauth2.googleapis.com/token";
const API_BASE = "https://www.googleapis.com/calendar/v3";

function b64url(buf) {
  return Buffer.from(buf).toString("base64url");
}

function makeState() {
  return b64url(crypto.randomBytes(18));
}

function dayBoundsIso(dateISO, tz = "Europe/Moscow") {
  const start = `${dateISO}T00:00:00+03:00`;
  const end = `${dateISO}T23:59:59+03:00`;
  return { start, end };
}

async function postForm(url, bodyObj) {
  const body = new URLSearchParams(bodyObj);
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString()
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`google_token_${res.status}`);
  return data;
}

async function refreshIfNeeded(cfg, tokens) {
  if (!tokens) return null;
  const exp = Number(tokens.expires_at || 0);
  if (exp && Date.now() < exp - 60 * 1000) return tokens;
  if (!tokens.refresh_token) return tokens;

  const refreshed = await postForm(TOKEN_URL, {
    grant_type: "refresh_token",
    refresh_token: tokens.refresh_token,
    client_id: cfg.googleClientId,
    client_secret: cfg.googleClientSecret
  });

  const next = {
    ...tokens,
    access_token: refreshed.access_token,
    token_type: refreshed.token_type || tokens.token_type || "Bearer",
    expires_in: refreshed.expires_in || 3600,
    expires_at: Date.now() + Number(refreshed.expires_in || 3600) * 1000,
    scope: refreshed.scope || tokens.scope || "",
    refresh_token: refreshed.refresh_token || tokens.refresh_token
  };
  saveProviderTokens(cfg.stateDir, "google", next);
  return next;
}

function normalizeEvent(evt) {
  const start = evt?.start?.dateTime || (evt?.start?.date ? `${evt.start.date}T00:00:00+03:00` : null);
  const end = evt?.end?.dateTime || (evt?.end?.date ? `${evt.end.date}T23:59:59+03:00` : null);
  if (!start || !end) return null;
  return {
    source: "google",
    id: String(evt.id || ""),
    title: String(evt.summary || "Без названия"),
    start,
    end,
    location: evt.location || undefined,
    link: evt.htmlLink || undefined,
    attendees: Array.isArray(evt.attendees) ? evt.attendees.map((a) => a.email).filter(Boolean) : undefined,
    isAllDay: !!evt?.start?.date && !evt?.start?.dateTime
  };
}

export function buildGoogleConnectUrl(cfg) {
  if (!cfg.googleClientId || !cfg.googleRedirectUri) {
    return { ok: false, error: "Google OAuth не настроен в ENV." };
  }
  const state = makeState();
  saveOAuthState(cfg.stateDir, "google", state, 30);

  const qp = new URLSearchParams({
    client_id: cfg.googleClientId,
    redirect_uri: cfg.googleRedirectUri,
    response_type: "code",
    access_type: "offline",
    prompt: "consent",
    scope: "https://www.googleapis.com/auth/calendar.readonly",
    state
  });

  return { ok: true, url: `${AUTH_URL}?${qp.toString()}` };
}

function extractCodeAndState(input) {
  const raw = String(input || "").trim();
  try {
    const u = new URL(raw);
    return {
      code: u.searchParams.get("code") || "",
      state: u.searchParams.get("state") || ""
    };
  } catch {
    const parts = raw.split(/\s+/);
    return { code: parts[0] || "", state: parts[1] || "" };
  }
}

export async function completeGoogleConnect(cfg, callbackInput) {
  const { code, state } = extractCodeAndState(callbackInput);
  if (!code) return { ok: false, error: "Не найден code в callback." };
  if (!state || !consumeOAuthState(cfg.stateDir, "google", state)) {
    return { ok: false, error: "OAuth state невалиден или просрочен." };
  }

  const tokenData = await postForm(TOKEN_URL, {
    grant_type: "authorization_code",
    code,
    redirect_uri: cfg.googleRedirectUri,
    client_id: cfg.googleClientId,
    client_secret: cfg.googleClientSecret
  });

  const saved = {
    access_token: tokenData.access_token,
    refresh_token: tokenData.refresh_token || null,
    token_type: tokenData.token_type || "Bearer",
    scope: tokenData.scope || "",
    expires_in: Number(tokenData.expires_in || 3600),
    expires_at: Date.now() + Number(tokenData.expires_in || 3600) * 1000
  };
  saveProviderTokens(cfg.stateDir, "google", saved);
  return { ok: true };
}

export async function googleConnected(cfg) {
  const t = getProviderTokens(cfg.stateDir, "google");
  return !!(t && (t.access_token || t.refresh_token));
}

export async function fetchGoogleAgendaForDate(cfg, dateISO) {
  if (!cfg.googleClientId || !cfg.googleClientSecret || !cfg.googleRedirectUri) {
    markAgendaSync(cfg.stateDir, "google", false, "google_env_missing");
    return [];
  }
  const tokens = await refreshIfNeeded(cfg, getProviderTokens(cfg.stateDir, "google"));
  if (!tokens?.access_token) {
    markAgendaSync(cfg.stateDir, "google", false, "google_not_connected");
    return [];
  }

  const { start, end } = dayBoundsIso(dateISO, cfg.tz);
  const calIds = cfg.googleCalendarIds.length ? cfg.googleCalendarIds : ["primary"];

  const events = [];
  for (const cal of calIds) {
    const qp = new URLSearchParams({
      timeMin: start,
      timeMax: end,
      singleEvents: "true",
      orderBy: "startTime",
      maxResults: "250"
    });
    const url = `${API_BASE}/calendars/${encodeURIComponent(cal)}/events?${qp.toString()}`;
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${tokens.access_token}`, Accept: "application/json" }
    });
    if (!res.ok) {
      markAgendaSync(cfg.stateDir, "google", false, `google_events_${res.status}`);
      continue;
    }
    const data = await res.json();
    (data.items || []).forEach((it) => {
      const n = normalizeEvent(it);
      if (n) events.push(n);
    });
  }

  markAgendaSync(cfg.stateDir, "google", true);
  return events;
}
