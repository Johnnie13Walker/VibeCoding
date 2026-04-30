import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { getProviderTokens, loadAgendaSyncStatus, markAgendaSync, saveProviderTokens } from "../state.mjs";
import { dateISOInTz, addDaysISO } from "../../time.mjs";

function dbPath(stateDir) {
  return path.join(stateDir, "bitrix_directory.db");
}

function withDb(stateDir, fn) {
  const db = new DatabaseSync(dbPath(stateDir));
  try {
    db.exec(`
      CREATE TABLE IF NOT EXISTS bitrix_users (
        user_id INTEGER PRIMARY KEY,
        full_name TEXT,
        name TEXT,
        last_name TEXT,
        email TEXT,
        login TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        department TEXT,
        updated_at TEXT
      );
      CREATE TABLE IF NOT EXISTS bitrix_meta (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TEXT
      );
      CREATE INDEX IF NOT EXISTS idx_bitrix_users_active_name ON bitrix_users(active, full_name);
    `);
    return fn(db);
  } finally {
    db.close();
  }
}

function setMeta(stateDir, key, value) {
  withDb(stateDir, (db) => {
    db.prepare(`
      INSERT INTO bitrix_meta(key, value, updated_at)
      VALUES (?, ?, datetime('now'))
      ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')
    `).run(String(key), String(value ?? ""));
  });
}

function getMeta(stateDir, key, fallback = "") {
  return withDb(stateDir, (db) => {
    const row = db.prepare("SELECT value FROM bitrix_meta WHERE key=?").get(String(key));
    if (!row) return fallback;
    return row.value ?? fallback;
  });
}

function normalizePortal(url) {
  return String(url || "").replace(/\/$/, "");
}

function tokenUrl(cfg) {
  return `${normalizePortal(cfg.bitrixPortalUrl)}/oauth/token/`;
}

function restUrl(cfg, method) {
  return `${normalizePortal(cfg.bitrixPortalUrl)}/rest/${method}.json`;
}

function parseUserId(v) {
  if (v == null) return null;
  const s = String(v).trim();
  const m = s.match(/^[Uu](\d+)$/);
  if (m) return m[1];
  if (/^\d+$/.test(s)) return s;
  return null;
}

function normalizeDisplayName(user) {
  const name = String(user?.NAME || "").trim();
  const last = String(user?.LAST_NAME || "").trim();
  const full = `${name} ${last}`.replace(/\s+/g, " ").trim();
  if (full) return full;
  const login = String(user?.LOGIN || "").trim();
  if (login) return login;
  const email = String(user?.EMAIL || "").trim();
  if (email) return email;
  return "";
}

function isActiveUser(user) {
  const active = String(user?.ACTIVE ?? "Y").toUpperCase();
  const ufFired = String(user?.UF_USER_FIRED || user?.UF_DEPARTMENT || "").toLowerCase();
  const ext = String(user?.EXTERNAL_AUTH_ID || "").toLowerCase();
  if (active === "N" || active === "0" || active === "FALSE") return false;
  if (ufFired === "1" || ufFired === "y" || ufFired === "true") return false;
  if (ext === "email") return false;
  return true;
}

function normalizeNameToken(v) {
  return String(v || "")
    .toLowerCase()
    .replace(/ё/g, "е")
    .replace(/[^a-zа-я0-9\s-]/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function deinflectWord(word) {
  const w = normalizeNameToken(word);
  if (!w) return "";
  const repl = [
    [/ом$/i, ""], [/ем$/i, ""], [/ой$/i, ""], [/ей$/i, ""],
    [/у$/i, ""], [/ю$/i, ""], [/а$/i, ""], [/я$/i, ""], [/е$/i, ""], [/ы$/i, ""], [/и$/i, ""]
  ];
  let out = w;
  for (const [rgx, to] of repl) out = out.replace(rgx, to);
  return out || w;
}

function similarity(a, b) {
  if (!a || !b) return 0;
  if (a === b) return 1;
  if (a.includes(b) || b.includes(a)) return 0.92;
  const at = a.split(" ").filter(Boolean);
  const bt = b.split(" ").filter(Boolean);
  const inter = at.filter((x) => bt.includes(x)).length;
  const union = new Set([...at, ...bt]).size || 1;
  return inter / union;
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

async function bitrixRestRaw(cfg, accessToken, method, params = {}) {
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
  return data;
}

async function bitrixRest(cfg, accessToken, method, params = {}) {
  const data = await bitrixRestRaw(cfg, accessToken, method, params);
  return data.result || [];
}

async function getAccessToken(cfg) {
  const tokens = await refreshIfNeeded(cfg, getProviderTokens(cfg.stateDir, "bitrix"));
  if (!tokens?.access_token) throw new Error("bitrix_not_connected");
  return tokens.access_token;
}

function rowFromUser(u) {
  const userId = Number(parseUserId(u.ID || u.id) || 0);
  if (!userId) return null;
  const name = String(u.NAME || "").trim();
  const last = String(u.LAST_NAME || "").trim();
  const full = normalizeDisplayName(u);
  if (!full) return null;
  return {
    user_id: userId,
    full_name: full,
    name,
    last_name: last,
    email: String(u.EMAIL || "").trim() || null,
    login: String(u.LOGIN || "").trim() || null,
    active: isActiveUser(u) ? 1 : 0,
    department: Array.isArray(u.UF_DEPARTMENT) ? u.UF_DEPARTMENT.map(String).join(",") : (u.UF_DEPARTMENT ? String(u.UF_DEPARTMENT) : null)
  };
}


export function getStoredDefaultSectionId(stateDir) {
  return getMeta(stateDir, "default_section_id", "");
}

export function setStoredDefaultSectionId(stateDir, sectionId) {
  setMeta(stateDir, "default_section_id", String(sectionId || ""));
}

export function getBitrixUsersCount(stateDir) {
  return withDb(stateDir, (db) => {
    const r = db.prepare("SELECT COUNT(*) AS c FROM bitrix_users WHERE active=1").get();
    return Number(r?.c || 0);
  });
}

export function getBitrixUsersSyncMeta(stateDir) {
  return {
    lastSyncAt: getMeta(stateDir, "users_last_sync_at", ""),
    lastSyncStatus: getMeta(stateDir, "users_last_sync_status", "unknown"),
    lastSyncError: getMeta(stateDir, "users_last_sync_error", "")
  };
}

export function isUsersSyncFresh(stateDir, ttlHours = 24) {
  const last = getMeta(stateDir, "users_last_sync_at", "");
  if (!last) return false;
  const ts = new Date(last).getTime();
  if (!Number.isFinite(ts)) return false;
  return Date.now() - ts < Number(ttlHours || 24) * 3600 * 1000;
}

export async function syncBitrixUsers(cfg, opts = {}) {
  if (!cfg.bitrixPortalUrl || !cfg.bitrixClientId || !cfg.bitrixClientSecret || !cfg.bitrixUserId) {
    throw new Error("bitrix_env_missing");
  }
  if (!opts.force && isUsersSyncFresh(cfg.stateDir, cfg.bitrixUsersCacheTtlHours || 24)) {
    return { ok: true, skipped: true, count: getBitrixUsersCount(cfg.stateDir) };
  }

  try {
    const token = await getAccessToken(cfg);
    const all = [];
    let start = 0;
    for (let i = 0; i < 50; i += 1) {
      const resp = await bitrixRestRaw(cfg, token, "user.get", {
        FILTER: { ACTIVE: true },
        start
      });
      const list = Array.isArray(resp.result) ? resp.result : [];
      all.push(...list);
      if (resp.next == null || list.length === 0) break;
      start = Number(resp.next || 0);
      if (!Number.isFinite(start)) break;
    }

    const rows = all
      .map(rowFromUser)
      .filter((x) => !!x && x.active === 1);

    withDb(cfg.stateDir, (db) => {
      db.exec("BEGIN");
      try {
        db.prepare("DELETE FROM bitrix_users").run();
        const ins = db.prepare(`
          INSERT INTO bitrix_users(user_id, full_name, name, last_name, email, login, active, department, updated_at)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        `);
        rows.forEach((r) => ins.run(r.user_id, r.full_name, r.name, r.last_name, r.email, r.login, r.active, r.department));
        db.exec("COMMIT");
      } catch (e) {
        db.exec("ROLLBACK");
        throw e;
      }
    });

    setMeta(cfg.stateDir, "users_last_sync_at", new Date().toISOString());
    setMeta(cfg.stateDir, "users_last_sync_status", "ok");
    setMeta(cfg.stateDir, "users_last_sync_error", "");
    markAgendaSync(cfg.stateDir, "bitrix_users", true);
    return { ok: true, count: rows.length, skipped: false };
  } catch (err) {
    const m = String(err.message || err);
    setMeta(cfg.stateDir, "users_last_sync_at", new Date().toISOString());
    setMeta(cfg.stateDir, "users_last_sync_status", "fail");
    setMeta(cfg.stateDir, "users_last_sync_error", m);
    markAgendaSync(cfg.stateDir, "bitrix_users", false, m);
    return { ok: false, error: m };
  }
}

function findLocalCandidates(stateDir, query, limit = 10) {
  const q = normalizeNameToken(query);
  const base = deinflectWord(q);
  return withDb(stateDir, (db) => {
    const rows = db.prepare(`
      SELECT user_id, full_name, name, last_name, department
      FROM bitrix_users
      WHERE active=1
      ORDER BY full_name COLLATE NOCASE
      LIMIT 1500
    `).all();

    const scored = rows.map((r) => {
      const full = normalizeNameToken(r.full_name);
      const fullBase = full.split(" ").map(deinflectWord).join(" ").trim();
      const score = Math.max(similarity(q, full), similarity(base, fullBase));
      return { ...r, score };
    }).filter((r) => r.score > 0.15)
      .sort((a, b) => b.score - a.score || String(a.full_name).localeCompare(String(b.full_name), "ru"));

    return scored.slice(0, limit).map((r) => ({
      userId: Number(r.user_id),
      fullName: r.full_name,
      department: r.department || "",
      score: Number(r.score.toFixed(4))
    }));
  });
}

export async function usersFind(cfg, query, limit = 10) {
  if (!isUsersSyncFresh(cfg.stateDir, cfg.bitrixUsersCacheTtlHours || 24)) {
    await syncBitrixUsers(cfg, { force: false });
  }
  return findLocalCandidates(cfg.stateDir, query, limit);
}

export async function resolveUserMentions(cfg, rawNames = []) {
  const threshold = Number(cfg.nameMatchThreshold || 0.78);
  const maxCandidates = Number(cfg.nameMatchMaxCandidates || 8);
  const resolved = [];
  const unresolved = [];

  for (const raw of rawNames) {
    const candidates = await usersFind(cfg, raw, maxCandidates);
    if (!candidates.length) {
      unresolved.push({ token: raw, reason: "not_found", candidates: [] });
      continue;
    }
    if (candidates.length === 1 && candidates[0].score >= threshold) {
      resolved.push(candidates[0]);
      continue;
    }

    const top = candidates[0];
    const second = candidates[1];
    if (top && top.score >= threshold && (!second || top.score - second.score >= 0.18)) {
      resolved.push(top);
      continue;
    }

    unresolved.push({ token: raw, reason: "ambiguous", candidates });
  }

  const uniq = new Map();
  resolved.forEach((r) => uniq.set(String(r.userId), r));
  return { resolved: [...uniq.values()], unresolved };
}

function extractMeetingAttendeesCodes(event) {
  const out = new Set();
  const arrs = [event?.ATTENDEES_CODES, event?.ATTENDEES, event?.MEETING?.USERS];
  for (const arr of arrs) {
    for (const x of Array.isArray(arr) ? arr : []) {
      const id = parseUserId(x?.USER_ID || x?.ID || x?.id || x);
      if (id) out.add(`U${id}`);
    }
  }
  const host = parseUserId(event?.MEETING?.HOST || event?.OWNER_ID || event?.CREATED_BY);
  if (host) out.add(`U${host}`);
  return [...out].sort();
}

function eventTitle(ev) {
  return String(ev?.NAME || ev?.name || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function eventStartMs(ev) {
  const from = ev?.DATE_FROM || ev?.dateFrom || ev?.dt_from || ev?.from;
  if (!from) return null;
  const ms = new Date(String(from).replace(" ", "T")).getTime();
  return Number.isFinite(ms) ? ms : null;
}

function attendeesSetFromCodes(codes = []) {
  return [...new Set((codes || []).map((x) => String(x || "").trim()).filter(Boolean))].sort();
}

export async function getDefaultSection(cfg) {
  const token = await getAccessToken(cfg);
  const stored = getStoredDefaultSectionId(cfg.stateDir);
  const desired = String(cfg.bitrixDefaultSectionId || stored || "").trim();

  const sections = await bitrixRest(cfg, token, "calendar.section.get", {
    type: "user",
    ownerId: cfg.bitrixUserId
  });
  const list = Array.isArray(sections) ? sections : [];
  if (!list.length) throw new Error("bitrix_section_not_found");

  if (desired) {
    const hit = list.find((s) => String(s.ID || s.id) === desired);
    if (hit) {
      setStoredDefaultSectionId(cfg.stateDir, desired);
      return { id: String(hit.ID || hit.id), title: String(hit.NAME || hit.name || "") };
    }
  }

  throw new Error("bitrix_default_section_required");
}

export async function listSections(cfg) {
  const token = await getAccessToken(cfg);
  const sections = await bitrixRest(cfg, token, "calendar.section.get", {
    type: "user",
    ownerId: cfg.bitrixUserId
  });
  return (Array.isArray(sections) ? sections : []).map((s) => ({
    id: String(s.ID || s.id),
    title: String(s.NAME || s.name || "")
  }));
}

export function parseDurationMinutes(text) {
  const t = String(text || "").toLowerCase();
  const range = t.match(/\b([01]?\d|2[0-3]):([0-5]\d)\s*[-–]\s*([01]?\d|2[0-3]):([0-5]\d)\b/);
  if (range) {
    const s = Number(range[1]) * 60 + Number(range[2]);
    const e = Number(range[3]) * 60 + Number(range[4]);
    const d = e - s;
    return d > 0 ? d : 30;
  }
  const hm = t.match(/\b(\d{1,2})\s*[:ч]\s*(\d{1,2})\b/);
  if (hm && t.includes("ч")) return Number(hm[1]) * 60 + Number(hm[2]);
  const h = t.match(/\b(\d{1,2})\s*ч(?:ас|\.)?/);
  if (h) return Math.max(15, Number(h[1]) * 60);
  const m = t.match(/\b(\d{1,3})\s*(?:м|мин|минут)/);
  if (m) return Math.max(10, Number(m[1]));
  return 30;
}

export function extractPotentialNames(text) {
  const t = String(text || "").replace(/—/g, "-");
  const result = [];

  const participants = t.match(/участники\s*:\s*([^\n]+)/i);
  if (participants) result.push(participants[1]);

  const withWho = t.match(/(?:созвон|встреча|митинг|meeting)\s+с\s+([^\n]+?)(?:\s+(?:про|по|тема)(?:\s|$)|$)/i);
  if (withWho) result.push(withWho[1]);

  const dashList = t.match(/:\s*([^\n]+?)\s*-\s*(?:сегодня|завтра|послезавтра|\d{1,2}:\d{2}|\d{2}\.\d{2}|\d{4}-\d{2}-\d{2})/i);
  if (dashList) result.push(dashList[1]);

  const chunks = result.join(",").split(/,|\s+и\s+/i).map((x) => x.trim()).filter(Boolean);
  return [...new Set(chunks.map((x) => x.replace(/^с\s+/i, "").replace(/\s+(?:про|по|тема)\s+.*$/i, "").trim()).filter(Boolean))];
}

export function buildMeetingFromDraft(draft, text, attendeeResolved = []) {
  const due = draft.dueDateTime || (draft.dueDate ? `${draft.dueDate}T09:00:00+03:00` : null);
  const startIso = due;
  const durationMin = parseDurationMinutes(text);
  let endIso = null;
  if (startIso) {
    const ms = new Date(startIso).getTime();
    endIso = new Date(ms + durationMin * 60000).toISOString().replace(".000Z", "+03:00");
  }

  const cleaned = String(draft.content || "").replace(/\s+/g, " ").trim();
  const title = cleaned || "Встреча";

  return {
    title,
    startIso,
    endIso,
    durationMin,
    attendees: attendeeResolved,
    attendeesCodes: attendeesSetFromCodes(attendeeResolved.map((x) => `U${x.userId}`))
  };
}

async function fetchEventsInWindow(cfg, token, fromIso, toIso, sectionId) {
  const params = {
    type: "user",
    ownerId: cfg.bitrixUserId,
    from: fromIso,
    to: toIso
  };
  if (sectionId) params.section = sectionId;
  const events = await bitrixRest(cfg, token, "calendar.event.get", params);
  return Array.isArray(events) ? events : [];
}

export async function detectMeetingDuplicate(cfg, candidate) {
  const token = await getAccessToken(cfg);
  const section = await getDefaultSection(cfg);
  const start = new Date(candidate.startIso).getTime();
  const from = new Date(start - 10 * 60000).toISOString();
  const to = new Date(start + 10 * 60000).toISOString();
  const events = await fetchEventsInWindow(cfg, token, from, to, section.id);

  const candTitle = String(candidate.title || "").toLowerCase().replace(/\s+/g, " ").trim();
  const candCodes = attendeesSetFromCodes([`U${cfg.bitrixUserId}`, ...(candidate.attendeesCodes || [])]);

  const found = events.find((ev) => {
    const t = eventTitle(ev);
    if (t !== candTitle) return false;
    const evCodes = attendeesSetFromCodes(extractMeetingAttendeesCodes(ev));
    return JSON.stringify(evCodes) === JSON.stringify(candCodes);
  });

  if (!found) return null;
  return {
    id: String(found.ID || found.id || ""),
    title: String(found.NAME || found.name || ""),
    start: found.DATE_FROM || "",
    end: found.DATE_TO || ""
  };
}

export async function createMeeting(cfg, payload, opts = {}) {
  const token = await getAccessToken(cfg);
  const section = await getDefaultSection(cfg);

  const attendeesCodes = attendeesSetFromCodes([...(payload.attendeesCodes || [])]);
  const hostCode = `U${cfg.bitrixUserId}`;
  if (!attendeesCodes.includes(hostCode)) attendeesCodes.push(hostCode);

  const fields = {
    type: "user",
    ownerId: cfg.bitrixUserId,
    section: section.id,
    name: payload.title,
    from: payload.startIso,
    to: payload.endIso,
    skipTime: "N",
    is_meeting: "Y",
    attendeesCodes,
    MEETING: {
      HOST: cfg.bitrixUserId,
      NOTIFY: "Y",
      REINVITE: "Y",
      ALLOW_INVITE: "Y"
    },
    SEND_INVITATION: "Y"
  };

  if (opts.dryRun) {
    return {
      dryRun: true,
      section,
      fields
    };
  }

  const eventId = await bitrixRest(cfg, token, "calendar.event.add", fields);

  const checkFrom = new Date(new Date(payload.startIso).getTime() - 20 * 60000).toISOString();
  const checkTo = new Date(new Date(payload.endIso).getTime() + 20 * 60000).toISOString();
  const list = await fetchEventsInWindow(cfg, token, checkFrom, checkTo, section.id);

  const matched = list.find((ev) => String(ev.ID || ev.id) === String(eventId)
    || (eventTitle(ev) === String(payload.title || "").toLowerCase().replace(/\s+/g, " ").trim()
      && Math.abs((eventStartMs(ev) || 0) - new Date(payload.startIso).getTime()) <= 120000));

  if (!matched) {
    throw new Error("meeting_readback_not_found");
  }

  const isMeeting = String(matched.IS_MEETING || matched.isMeeting || matched.MEETING_STATUS || "").toLowerCase();
  const readCodes = attendeesSetFromCodes(extractMeetingAttendeesCodes(matched));
  const required = attendeesSetFromCodes(attendeesCodes);
  const attendeesOk = required.every((c) => readCodes.includes(c));
  const meetingOk = isMeeting === "y" || isMeeting === "1" || !!matched.MEETING;

  if (!meetingOk || !attendeesOk) {
    throw new Error(`meeting_readback_invalid isMeeting=${isMeeting || "n/a"} attendees=${readCodes.join(",")}`);
  }

  return {
    dryRun: false,
    section,
    eventId: String(matched.ID || matched.id || eventId),
    readback: {
      isMeeting: true,
      attendeesCodes: readCodes
    }
  };
}

export async function moveMeeting(cfg, eventId, startIso, endIso, opts = {}) {
  const token = await getAccessToken(cfg);
  if (opts.dryRun) {
    return { dryRun: true, eventId: String(eventId), startIso, endIso };
  }

  await bitrixRest(cfg, token, "calendar.event.edit", {
    id: eventId,
    from: startIso,
    to: endIso,
    sendInvites: "Y"
  });

  const list = await bitrixRest(cfg, token, "calendar.event.get", {
    type: "user",
    ownerId: cfg.bitrixUserId,
    from: new Date(new Date(startIso).getTime() - 20 * 60000).toISOString(),
    to: new Date(new Date(endIso).getTime() + 20 * 60000).toISOString()
  });
  const matched = (Array.isArray(list) ? list : []).find((x) => String(x.ID || x.id) === String(eventId));
  if (!matched) throw new Error("meeting_move_readback_not_found");
  return { dryRun: false, eventId: String(eventId), ok: true };
}

export async function cancelMeeting(cfg, eventId, opts = {}) {
  const token = await getAccessToken(cfg);
  if (opts.dryRun) {
    return { dryRun: true, eventId: String(eventId) };
  }
  await bitrixRest(cfg, token, "calendar.event.delete", { id: eventId, sendInvitation: "Y" });
  return { dryRun: false, eventId: String(eventId), ok: true };
}

export async function maybeSyncUsersBySchedule(cfg, now = new Date()) {
  const hhmm = String(cfg.bitrixUsersSyncTime || "03:00");
  const [hh, mm] = hhmm.split(":").map((x) => Number(x));
  if (!Number.isFinite(hh) || !Number.isFinite(mm)) return { skipped: true, reason: "bad_time" };

  const local = new Intl.DateTimeFormat("en-GB", {
    timeZone: cfg.tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).formatToParts(now);
  const pick = (t) => local.find((p) => p.type === t)?.value || "";
  const curDate = `${pick("year")}-${pick("month")}-${pick("day")}`;
  const curHH = Number(pick("hour") || 0);
  const curMM = Number(pick("minute") || 0);
  const nowMin = curHH * 60 + curMM;
  const targetMin = hh * 60 + mm;

  const lastDate = getMeta(cfg.stateDir, "users_last_scheduled_date", "");
  if (lastDate === curDate) return { skipped: true, reason: "already_ran" };
  if (nowMin < targetMin) return { skipped: true, reason: "too_early" };

  const res = await syncBitrixUsers(cfg, { force: true });
  setMeta(cfg.stateDir, "users_last_scheduled_date", curDate);
  return res;
}

export function formatUsersMatches(matches = []) {
  if (!matches.length) return "Совпадений нет.";
  return matches.slice(0, 10).map((m, idx) => `${idx + 1}) ${m.fullName}${m.department ? ` (${m.department})` : ""} [${m.userId}]`).join("\n");
}

export function buildDateTimeByDateAndTime(dateIso, timeHHMM = "09:00") {
  const hhmm = /^\d{2}:\d{2}$/.test(String(timeHHMM || "")) ? timeHHMM : "09:00";
  return `${dateIso}T${hhmm}:00+03:00`;
}

export function shiftIsoByMinutes(iso, mins) {
  const ms = new Date(iso).getTime();
  return new Date(ms + Number(mins || 0) * 60000).toISOString().replace(".000Z", "+03:00");
}


export async function getMeetingById(cfg, eventId) {
  const token = await getAccessToken(cfg);
  const sections = await bitrixRest(cfg, token, "calendar.section.get", {
    type: "user",
    ownerId: cfg.bitrixUserId
  });
  const listSections = Array.isArray(sections) ? sections : [];
  for (const s of listSections.slice(0, 60)) {
    const events = await bitrixRest(cfg, token, "calendar.event.get", {
      type: "user",
      ownerId: cfg.bitrixUserId,
      section: s.ID || s.id,
      from: addDaysISO(dateISOInTz(new Date(), cfg.tz), -30) + "T00:00:00+03:00",
      to: addDaysISO(dateISOInTz(new Date(), cfg.tz), 90) + "T23:59:59+03:00"
    });
    const found = (Array.isArray(events) ? events : []).find((e) => String(e.ID || e.id) === String(eventId));
    if (found) return found;
  }
  return null;
}

export async function searchMeetingsByText(cfg, query, dateIso = "") {
  const token = await getAccessToken(cfg);
  const from = (dateIso || dateISOInTz(new Date(), cfg.tz)) + "T00:00:00+03:00";
  const to = addDaysISO((dateIso || dateISOInTz(new Date(), cfg.tz)), 1) + "T23:59:59+03:00";
  const events = await bitrixRest(cfg, token, "calendar.event.get", {
    type: "user",
    ownerId: cfg.bitrixUserId,
    from,
    to
  });
  const q = String(query || "").toLowerCase().trim();
  return (Array.isArray(events) ? events : [])
    .filter((e) => String(e.NAME || e.name || "").toLowerCase().includes(q))
    .slice(0, 10)
    .map((e) => ({
      id: String(e.ID || e.id || ""),
      title: String(e.NAME || e.name || ""),
      from: String(e.DATE_FROM || "")
    }));
}
