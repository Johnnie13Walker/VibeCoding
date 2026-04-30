import crypto from "node:crypto";
import {
  consumeOAuthState,
  getProviderTokens,
  loadBitrixUsersCache,
  markAgendaSync,
  saveBitrixUsersCache,
  saveOAuthState,
  saveProviderTokens
} from "../state.mjs";

function normalizePortal(url) {
  return String(url || "").replace(/\/$/, "");
}

function makeState() {
  return Buffer.from(crypto.randomBytes(18)).toString("base64url");
}

function authUrl(cfg, state) {
  const portal = normalizePortal(cfg.bitrixPortalUrl);
  const qp = new URLSearchParams({
    client_id: cfg.bitrixClientId,
    response_type: "code",
    redirect_uri: cfg.bitrixRedirectUri,
    state
  });
  return `${portal}/oauth/authorize/?${qp.toString()}`;
}

function tokenUrl(cfg) {
  return `${normalizePortal(cfg.bitrixPortalUrl)}/oauth/token/`;
}

function restUrl(cfg, method) {
  return `${normalizePortal(cfg.bitrixPortalUrl)}/rest/${method}.json`;
}

async function postForm(url, bodyObj) {
  const body = new URLSearchParams(bodyObj);
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString()
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`bitrix_http_${res.status}`);
  if (data.error) throw new Error(`bitrix_${data.error}`);
  return data;
}

async function refreshIfNeeded(cfg, tokens) {
  if (!tokens) return null;
  const exp = Number(tokens.expires_at || 0);
  if (exp && Date.now() < exp - 60 * 1000) return tokens;
  if (!tokens.refresh_token) return tokens;

  const data = await postForm(tokenUrl(cfg), {
    grant_type: "refresh_token",
    client_id: cfg.bitrixClientId,
    client_secret: cfg.bitrixClientSecret,
    refresh_token: tokens.refresh_token
  });

  const next = {
    ...tokens,
    access_token: data.access_token,
    refresh_token: data.refresh_token || tokens.refresh_token,
    expires_in: Number(data.expires_in || 3600),
    expires_at: Date.now() + Number(data.expires_in || 3600) * 1000,
    domain: data.domain || tokens.domain || null
  };
  saveProviderTokens(cfg.stateDir, "bitrix", next);
  return next;
}

function normalizeBitrixDate(v) {
  if (!v) return null;
  const s = String(v).trim();

  const isoLike = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T\s](\d{2}):(\d{2})(?::(\d{2}))?)?$/);
  if (isoLike) {
    const [, y, m, d, hh = "00", mm = "00", ss = "00"] = isoLike;
    return `${y}-${m}-${d}T${hh}:${mm}:${ss}+03:00`;
  }

  const ruLike = s.match(/^(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?$/);
  if (ruLike) {
    const [, d, m, y, hh = "00", mm = "00", ss = "00"] = ruLike;
    return `${y}-${m}-${d}T${hh}:${mm}:${ss}+03:00`;
  }

  const ms = new Date(s).getTime();
  if (!Number.isFinite(ms)) return null;
  return new Date(ms).toISOString();
}

function parseUserId(v) {
  if (v == null) return null;
  if (typeof v === "number" && Number.isFinite(v)) return String(Math.trunc(v));
  const s = String(v).trim();
  if (!s) return null;
  const u = s.match(/^[Uu](\d+)$/);
  if (u) return u[1];
  if (/^\d+$/.test(s)) return s;
  return null;
}

function isDeclined(status) {
  const s = String(status || "").trim().toLowerCase();
  if (!s) return false;
  return ["n", "q", "declined", "decline", "rejected", "no", "cancelled", "canceled"].includes(s);
}

function ownerDeclinedEvent(evt, ownerId) {
  const oid = parseUserId(ownerId);
  if (!oid) return false;

  const statuses = [];

  for (const x of Array.isArray(evt.ATTENDEE_LIST) ? evt.ATTENDEE_LIST : []) {
    if (!x || typeof x !== "object") continue;
    const id = parseUserId(x.USER_ID || x.ID || x.id);
    if (id !== oid) continue;
    const st = x.STATUS || x.status || x.RESPONSE_STATUS || x.response_status;
    if (st != null && String(st).trim()) statuses.push(st);
  }

  for (const x of Array.isArray(evt.ATTENDEES) ? evt.ATTENDEES : []) {
    if (!x || typeof x !== "object") continue;
    const id = parseUserId(x.USER_ID || x.ID || x.id || x.ENTITY_ID);
    if (id !== oid) continue;
    const st = x.STATUS || x.status || x.RESPONSE_STATUS || x.response_status;
    if (st != null && String(st).trim()) statuses.push(st);
  }

  for (const x of Array.isArray(evt.MEETING?.USERS) ? evt.MEETING.USERS : []) {
    if (!x || typeof x !== "object") continue;
    const id = parseUserId(x.USER_ID || x.ID || x.id);
    if (id !== oid) continue;
    const st = x.STATUS || x.status || x.RESPONSE_STATUS || x.response_status;
    if (st != null && String(st).trim()) statuses.push(st);
  }

  if (!statuses.length) return false;
  return statuses.every((s) => isDeclined(s));
}

function extractAttendeeIds(evt) {
  const ids = new Set();

  for (const x of Array.isArray(evt.ATTENDEES_CODES) ? evt.ATTENDEES_CODES : []) {
    const id = parseUserId(x);
    if (id) ids.add(id);
  }

  for (const x of Array.isArray(evt.ATTENDEES) ? evt.ATTENDEES : []) {
    if (x && typeof x === "object") {
      if (isDeclined(x.STATUS || x.status || x.RESPONSE_STATUS || x.response_status)) continue;
      const id = parseUserId(x.USER_ID || x.ID || x.id || x.ENTITY_ID);
      if (id) ids.add(id);
      continue;
    }
    const id = parseUserId(x);
    if (id) ids.add(id);
  }

  const host = parseUserId(evt.MEETING?.HOST || evt.MEETING_HOST || evt.CREATED_BY || evt.OWNER_ID);
  if (host) ids.add(host);

  for (const x of Array.isArray(evt.MEETING?.USERS) ? evt.MEETING.USERS : []) {
    if (x && typeof x === "object") {
      if (isDeclined(x.STATUS || x.status || x.RESPONSE_STATUS || x.response_status)) continue;
      const id = parseUserId(x.USER_ID || x.ID || x.id);
      if (id) ids.add(id);
      continue;
    }
    const id = parseUserId(x);
    if (id) ids.add(id);
  }

  return [...ids];
}

function normalizeEvent(evt, ownerId) {
  const id = String(evt.ID || evt.id || "");
  const title = String(evt.NAME || evt.name || "Без названия");
  const startRaw = evt.DATE_FROM || evt.dateFrom || evt.dt_from || null;
  const endRaw = evt.DATE_TO || evt.dateTo || evt.dt_to || null;
  const start = normalizeBitrixDate(startRaw);
  const end = normalizeBitrixDate(endRaw);
  if (!id || !start || !end) return null;
  if (ownerDeclinedEvent(evt, ownerId)) return null;
  return {
    source: "bitrix",
    id,
    title,
    start,
    end,
    location: evt.LOCATION || undefined,
    link: evt.MEETING?.URL || evt.URL || undefined,
    attendeeIds: extractAttendeeIds(evt),
    attendees: undefined,
    isAllDay: String(evt.SKIP_TIME || "N") === "Y"
  };
}

function appendParam(body, key, value) {
  if (value == null) return;
  if (Array.isArray(value)) {
    value.forEach((item, i) => appendParam(body, `${key}[${i}]`, item));
    return;
  }
  if (typeof value === "object") {
    Object.entries(value).forEach(([k, v]) => appendParam(body, `${key}[${k}]`, v));
    return;
  }
  body.set(key, String(value));
}

async function bitrixRest(cfg, accessToken, method, params = {}) {
  const body = new URLSearchParams({ auth: accessToken });
  Object.entries(params).forEach(([k, v]) => appendParam(body, k, v));

  const res = await fetch(restUrl(cfg, method), {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString()
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`bitrix_rest_${method}_${res.status}`);
  if (data.error) throw new Error(`bitrix_rest_${method}_${data.error}`);
  return data.result || [];
}

function dayBounds(dateISO) {
  return {
    from: `${dateISO}T00:00:00+03:00`,
    to: `${dateISO}T23:59:59+03:00`
  };
}

function isCacheFresh(savedAt, ttlHours) {
  if (!savedAt) return false;
  const t = new Date(savedAt).getTime();
  if (!Number.isFinite(t)) return false;
  return Date.now() - t < ttlHours * 60 * 60 * 1000;
}

function normalizeDisplayName(user) {
  const name = String(user?.NAME || "").trim();
  const last = String(user?.LAST_NAME || "").trim();
  const full = `${name} ${last}`.replace(/\s+/g, " ").trim();
  if (full) return full;
  const first = name || last;
  if (first) return first;
  const login = String(user?.LOGIN || "").trim();
  if (login) return login;
  const email = String(user?.EMAIL || "").trim();
  if (email) return email;
  return "";
}

async function fetchUsersMapByIds(cfg, accessToken, userIds) {
  const uniq = [...new Set((userIds || []).map((x) => String(x)).filter(Boolean))];
  if (!uniq.length) return {};

  const cache = loadBitrixUsersCache(cfg.stateDir);
  const users = { ...(cache.users || {}) };
  const fresh = isCacheFresh(cache.saved_at, cfg.bitrixUsersCacheTtlHours || 12);

  const missing = fresh
    ? uniq.filter((id) => !users[id])
    : uniq;

  if (missing.length) {
    const cmd = {};
    missing.forEach((id) => {
      cmd[`u${id}`] = `user.get?id=${id}`;
    });

    try {
      const batch = await bitrixRest(cfg, accessToken, "batch", { halt: 0, cmd });
      const perResult = batch?.result || {};
      Object.values(perResult).forEach((arr) => {
        const row = Array.isArray(arr) ? arr[0] : null;
        if (!row) return;
        const id = parseUserId(row.ID || row.id);
        if (!id) return;
        const display = normalizeDisplayName(row);
        if (display) users[id] = display;
      });
      saveBitrixUsersCache(cfg.stateDir, { users });
    } catch {
      // ignore user map errors, meetings will be shown without participants
    }
  }

  const out = {};
  uniq.forEach((id) => {
    if (users[id]) out[id] = users[id];
  });
  return out;
}

async function attachAttendeesNames(cfg, accessToken, meetings) {
  const owner = parseUserId(cfg.bitrixUserId) || String(cfg.bitrixUserId || "").trim();
  const allIds = new Set();
  (meetings || []).forEach((m) => {
    (m.attendeeIds || []).forEach((id) => {
      const uid = parseUserId(id);
      if (uid && uid !== owner) allIds.add(uid);
    });
  });

  const usersMap = await fetchUsersMapByIds(cfg, accessToken, [...allIds]);

  return (meetings || []).map((m) => {
    const ids = [];
    const seenIds = new Set();
    (m.attendeeIds || []).forEach((id) => {
      const uid = parseUserId(id);
      if (!uid || uid === owner || seenIds.has(uid)) return;
      seenIds.add(uid);
      ids.push(uid);
    });

    const attendees = [];
    const seenNames = new Set();
    ids.forEach((uid) => {
      const nm = (usersMap[uid] || "").trim();
      if (!nm || seenNames.has(nm)) return;
      seenNames.add(nm);
      attendees.push(nm);
    });

    return {
      ...m,
      attendeeIds: ids,
      attendees: attendees.length ? attendees : undefined
    };
  });
}

export function buildBitrixConnectUrl(cfg) {
  if (!cfg.bitrixPortalUrl || !cfg.bitrixClientId || !cfg.bitrixRedirectUri) {
    return { ok: false, error: "Bitrix OAuth не настроен в ENV." };
  }
  const state = makeState();
  saveOAuthState(cfg.stateDir, "bitrix", state, 30);
  return { ok: true, url: authUrl(cfg, state) };
}

function extractCodeState(input) {
  const raw = String(input || "").trim();
  try {
    const u = new URL(raw);
    return {
      code: u.searchParams.get("code") || "",
      state: u.searchParams.get("state") || ""
    };
  } catch {
    const p = raw.split(/\s+/);
    return { code: p[0] || "", state: p[1] || "" };
  }
}

export async function completeBitrixConnect(cfg, callbackInput) {
  const { code, state } = extractCodeState(callbackInput);
  if (!code) return { ok: false, error: "Не найден code в callback." };
  if (!state || !consumeOAuthState(cfg.stateDir, "bitrix", state)) {
    return { ok: false, error: "OAuth state невалиден или просрочен." };
  }

  const data = await postForm(tokenUrl(cfg), {
    grant_type: "authorization_code",
    client_id: cfg.bitrixClientId,
    client_secret: cfg.bitrixClientSecret,
    code,
    redirect_uri: cfg.bitrixRedirectUri
  });

  saveProviderTokens(cfg.stateDir, "bitrix", {
    access_token: data.access_token,
    refresh_token: data.refresh_token || null,
    expires_in: Number(data.expires_in || 3600),
    expires_at: Date.now() + Number(data.expires_in || 3600) * 1000,
    domain: data.domain || null,
    member_id: data.member_id || null
  });
  return { ok: true };
}

export async function bitrixConnected(cfg) {
  const t = getProviderTokens(cfg.stateDir, "bitrix");
  return !!(t && (t.access_token || t.refresh_token));
}

export async function fetchBitrixAgendaForDate(cfg, dateISO) {
  if (!cfg.bitrixPortalUrl || !cfg.bitrixClientId || !cfg.bitrixClientSecret || !cfg.bitrixUserId) {
    markAgendaSync(cfg.stateDir, "bitrix", false, "bitrix_env_missing");
    return [];
  }
  const tokens = await refreshIfNeeded(cfg, getProviderTokens(cfg.stateDir, "bitrix"));
  if (!tokens?.access_token) {
    markAgendaSync(cfg.stateDir, "bitrix", false, "bitrix_not_connected");
    return [];
  }

  try {
    const sections = await bitrixRest(cfg, tokens.access_token, "calendar.section.get", {
      type: "user",
      ownerId: cfg.bitrixUserId
    });

    const { from, to } = dayBounds(dateISO);
    const all = [];

    if (Array.isArray(sections) && sections.length) {
      for (const s of sections.slice(0, 50)) {
        const sid = s.ID || s.id;
        const events = await bitrixRest(cfg, tokens.access_token, "calendar.event.get", {
          type: "user",
          ownerId: cfg.bitrixUserId,
          section: sid,
          from,
          to
        });
        (events || []).forEach((e) => {
          const n = normalizeEvent(e, cfg.bitrixUserId);
          if (n) all.push(n);
        });
      }
    } else {
      const events = await bitrixRest(cfg, tokens.access_token, "calendar.event.get", {
        type: "user",
        ownerId: cfg.bitrixUserId,
        from,
        to
      });
      (events || []).forEach((e) => {
        const n = normalizeEvent(e, cfg.bitrixUserId);
        if (n) all.push(n);
      });
    }

    const withUsers = await attachAttendeesNames(cfg, tokens.access_token, all);
    markAgendaSync(cfg.stateDir, "bitrix", true);
    return withUsers;
  } catch (err) {
    markAgendaSync(cfg.stateDir, "bitrix", false, err.message || "bitrix_fetch_failed");
    return [];
  }
}

export async function bitrixPing(cfg) {
  const tokens = await refreshIfNeeded(cfg, getProviderTokens(cfg.stateDir, "bitrix"));
  if (!tokens?.access_token) return { ok: false, error: "bitrix_not_connected" };
  try {
    const sections = await bitrixRest(cfg, tokens.access_token, "calendar.section.get", {
      type: "user",
      ownerId: cfg.bitrixUserId
    });
    return { ok: true, sectionsCount: Array.isArray(sections) ? sections.length : 0 };
  } catch (err) {
    return { ok: false, error: err.message || "bitrix_ping_failed" };
  }
}
