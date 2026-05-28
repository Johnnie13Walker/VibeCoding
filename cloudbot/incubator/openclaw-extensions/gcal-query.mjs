import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { google } from "googleapis";

const DEFAULT_TZ = process.env.TZ || "Europe/Moscow";
const BITRIX_USER_CACHE_FILE = process.env.BITRIX_USER_CACHE_FILE || "/tmp/clawbot-cache/bitrix-users-v1.json";
const BITRIX_USER_CACHE_TTL_HOURS = Math.max(
  1,
  Math.min(168, Number(process.env.BITRIX_USER_CACHE_TTL_HOURS || 24))
);
const BITRIX_USER_CACHE_TTL_MS = BITRIX_USER_CACHE_TTL_HOURS * 60 * 60 * 1000;
const OVERLAP_MINUTES_THRESHOLD = Math.max(1, Math.min(240, Number(process.env.OVERLAP_MINUTES_THRESHOLD || 10)));

const RU_MONTHS = {
  "января": 1,
  "февраля": 2,
  "марта": 3,
  "апреля": 4,
  "мая": 5,
  "июня": 6,
  "июля": 7,
  "августа": 8,
  "сентября": 9,
  "октября": 10,
  "ноября": 11,
  "декабря": 12,
};

function pad2(n) {
  return String(n).padStart(2, "0");
}

function parseBool(v) {
  return ["1", "true", "yes", "on"].includes(String(v || "").toLowerCase());
}

function parseCsv(v) {
  return String(v || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function getBackend() {
  const explicit = String(process.env.CALENDAR_BACKEND || "").trim().toLowerCase();
  if (explicit) return explicit;
  const hasBitrix =
    Boolean(String(process.env.BITRIX_WEBHOOK_BASE || "").trim()) ||
    Boolean(String(process.env.BITRIX_API_BASE || "").trim()) ||
    Boolean(String(process.env.BITRIX_PORTAL_URL || process.env.BITRIX_OAUTH_DOMAIN || "").trim());
  if (hasBitrix) return "bitrix";
  return "google";
}

function getTodayYmdInTz(tz) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());

  const year = Number(parts.find((p) => p.type === "year")?.value);
  const month = Number(parts.find((p) => p.type === "month")?.value);
  const day = Number(parts.find((p) => p.type === "day")?.value);

  return { year, month, day };
}

function makeValidYmd(year, month, day) {
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) return null;
  const dt = new Date(Date.UTC(year, month - 1, day));
  if (
    dt.getUTCFullYear() !== year ||
    dt.getUTCMonth() + 1 !== month ||
    dt.getUTCDate() !== day
  ) {
    return null;
  }
  return { year, month, day };
}

function addDays(ymd, days) {
  const dt = new Date(Date.UTC(ymd.year, ymd.month - 1, ymd.day + days));
  return {
    year: dt.getUTCFullYear(),
    month: dt.getUTCMonth() + 1,
    day: dt.getUTCDate(),
  };
}

function parseDateQuery(rawInput, tz = DEFAULT_TZ) {
  const raw = (rawInput || "").trim();
  const q = raw.toLowerCase().replace(/\s+/g, " ").trim();
  const today = getTodayYmdInTz(tz);

  if (!q || q === "сегодня" || q === "today") return today;
  if (q === "завтра" || q === "tomorrow") return addDays(today, 1);
  if (q === "вчера" || q === "yesterday") return addDays(today, -1);
  if (q === "послезавтра") return addDays(today, 2);
  if (q === "позавчера") return addDays(today, -2);

  let m = q.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (m) {
    const ymd = makeValidYmd(Number(m[1]), Number(m[2]), Number(m[3]));
    if (!ymd) throw new Error(`Невалидная дата: "${raw}"`);
    return ymd;
  }

  m = q.match(/^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?$/);
  if (m) {
    const year = m[3] ? Number(m[3]) : today.year;
    const ymd = makeValidYmd(year, Number(m[2]), Number(m[1]));
    if (!ymd) throw new Error(`Невалидная дата: "${raw}"`);
    return ymd;
  }

  m = q.match(/^(\d{1,2})\s+([а-яё]+)(?:\s+(\d{4}))?$/u);
  if (m) {
    const day = Number(m[1]);
    const month = RU_MONTHS[m[2]];
    const year = m[3] ? Number(m[3]) : today.year;
    if (!month) throw new Error(`Невалидная дата: "${raw}"`);
    const ymd = makeValidYmd(year, month, day);
    if (!ymd) throw new Error(`Невалидная дата: "${raw}"`);
    return ymd;
  }

  throw new Error(
    `Не понял дату: "${raw}". Примеры: завтра, вчера, послезавтра, 25.02.2026, 2026-02-25, 25 февраля 2026`
  );
}

function tzOffsetForDate(ymd, tz = DEFAULT_TZ) {
  const probe = new Date(Date.UTC(ymd.year, ymd.month - 1, ymd.day, 12, 0, 0));
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: tz,
    timeZoneName: "shortOffset",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(probe);

  const tzName = parts.find((p) => p.type === "timeZoneName")?.value || "GMT+00";
  const match = tzName.match(/^GMT([+-])(\d{1,2})(?::?(\d{2}))?$/);
  if (!match) return "+00:00";

  const sign = match[1];
  const hh = pad2(Number(match[2]));
  const mm = pad2(Number(match[3] || 0));
  return `${sign}${hh}:${mm}`;
}

function buildRange(ymd, tz = DEFAULT_TZ) {
  const dateIso = `${ymd.year}-${pad2(ymd.month)}-${pad2(ymd.day)}`;
  const offset = tzOffsetForDate(ymd, tz);
  return {
    label: `${pad2(ymd.day)}.${pad2(ymd.month)}.${ymd.year}`,
    timeMin: `${dateIso}T00:00:00${offset}`,
    timeMax: `${dateIso}T23:59:59${offset}`,
  };
}

function startTextGoogle(ev, tz = DEFAULT_TZ) {
  if (ev.start?.dateTime) {
    return new Intl.DateTimeFormat("ru-RU", {
      timeZone: tz,
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(ev.start.dateTime));
  }
  if (ev.start?.date) return "Весь день";
  return "Без времени";
}

function startTextBitrix(ev, tz = DEFAULT_TZ) {
  if (String(ev.DT_SKIP_TIME || "N") === "Y") return "Весь день";
  const m = String(ev.DATE_FROM || "").match(/\b(\d{2}):(\d{2})/);
  if (m) return `${m[1]}:${m[2]}`;
  const ts = Number(ev.DATE_FROM_TS_UTC || 0);
  if (ts > 0) {
    return new Intl.DateTimeFormat("ru-RU", {
      timeZone: tz,
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(ts * 1000));
  }
  return "Без времени";
}

function parseBitrixDateTimeParts(v) {
  const m = String(v || "").match(
    /^(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?$/
  );
  if (!m) return null;
  return {
    day: Number(m[1]),
    month: Number(m[2]),
    year: Number(m[3]),
    hour: Number(m[4] || 0),
    minute: Number(m[5] || 0),
    second: Number(m[6] || 0),
  };
}

function minutesOfDayFromBitrix(ev) {
  const p = parseBitrixDateTimeParts(ev.DATE_FROM);
  if (p) return p.hour * 60 + p.minute;
  const m = String(startTextBitrix(ev)).match(/^(\d{2}):(\d{2})$/);
  if (m) return Number(m[1]) * 60 + Number(m[2]);
  return Number.MAX_SAFE_INTEGER;
}

function endMinutesOfDayFromBitrix(ev) {
  const p = parseBitrixDateTimeParts(ev.DATE_TO);
  if (p) return p.hour * 60 + p.minute;
  const start = minutesOfDayFromBitrix(ev);
  const lenMin = Math.max(0, Math.round(Number(ev.DT_LENGTH || 0) / 60));
  if (Number.isFinite(start) && start < Number.MAX_SAFE_INTEGER && lenMin > 0) return start + lenMin;
  return start;
}

function fmtHm(min) {
  const h = Math.floor(min / 60) % 24;
  const m = min % 60;
  return `${pad2(h)}:${pad2(m)}`;
}

function slotTextBitrix(ev) {
  if (String(ev.DT_SKIP_TIME || "N") === "Y") return "Весь день";
  const start = minutesOfDayFromBitrix(ev);
  if (!Number.isFinite(start) || start === Number.MAX_SAFE_INTEGER) return "Без времени";
  const end = endMinutesOfDayFromBitrix(ev);
  if (!Number.isFinite(end) || end <= start) return fmtHm(start);
  return `${fmtHm(start)}-${fmtHm(end)}`;
}

function ymdEquals(a, b) {
  return a.year === b.year && a.month === b.month && a.day === b.day;
}

function bitrixEventStartYmd(ev, tz = DEFAULT_TZ) {
  const local = String(ev.DATE_FROM || "").match(/^(\d{2})\.(\d{2})\.(\d{4})/);
  if (local) {
    return {
      day: Number(local[1]),
      month: Number(local[2]),
      year: Number(local[3]),
    };
  }

  const ts = Number(ev.DATE_FROM_TS_UTC || 0);
  if (ts > 0) {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: tz,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date(ts * 1000));
    return {
      year: Number(parts.find((p) => p.type === "year")?.value),
      month: Number(parts.find((p) => p.type === "month")?.value),
      day: Number(parts.find((p) => p.type === "day")?.value),
    };
  }
  return null;
}

function validateRequiredEnv(sendTelegram) {
  if (sendTelegram) {
    for (const k of ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]) {
      if (!process.env[k] || !String(process.env[k]).trim()) throw new Error(`Missing env: ${k}`);
    }
  }

  const backend = getBackend();
  if (backend === "bitrix") {
    const base = bitrixBase(process.env.BITRIX_WEBHOOK_BASE);
    if (!base) {
      throw new Error(
        "Missing env: BITRIX_WEBHOOK_BASE or BITRIX_API_BASE or BITRIX_PORTAL_URL/BITRIX_OAUTH_DOMAIN"
      );
    }
    if (!isWebhookBase(base)) {
      const hasAccess = Boolean(String(process.env.BITRIX_OAUTH_ACCESS_TOKEN || "").trim());
      const hasRefresh = Boolean(String(process.env.BITRIX_OAUTH_REFRESH_TOKEN || "").trim());
      if (!hasAccess && !hasRefresh) {
        throw new Error("Missing env/token: BITRIX_OAUTH_ACCESS_TOKEN or BITRIX_OAUTH_REFRESH_TOKEN");
      }
    }
    return;
  }

  if (!process.env.GOOGLE_SERVICE_ACCOUNT_JSON || !String(process.env.GOOGLE_SERVICE_ACCOUNT_JSON).trim()) {
    throw new Error("Missing env: GOOGLE_SERVICE_ACCOUNT_JSON");
  }

  const hasSingle = Boolean(String(process.env.GOOGLE_CALENDAR_ID || "").trim());
  const hasMany = parseCsv(process.env.GOOGLE_CALENDAR_IDS).length > 0;
  const includeAll = parseBool(process.env.GOOGLE_CALENDAR_INCLUDE_ALL);
  if (!hasSingle && !hasMany && !includeAll) {
    throw new Error("Missing env: GOOGLE_CALENDAR_ID or GOOGLE_CALENDAR_IDS or GOOGLE_CALENDAR_INCLUDE_ALL=1");
  }
}

function parseBitrixUserIdFromWebhook(base) {
  const m = String(base || "").match(/\/rest\/(\d+)\//);
  return m ? Number(m[1]) : null;
}

function bitrixBase(base) {
  const webhook = String(base || "").trim();
  if (webhook) return webhook.replace(/\/+$/, "");

  const apiBase = String(process.env.BITRIX_API_BASE || "").trim();
  if (apiBase) return apiBase.replace(/\/+$/, "");

  const portal = String(process.env.BITRIX_PORTAL_URL || process.env.BITRIX_OAUTH_DOMAIN || "").trim();
  if (!portal) return "";
  const normalized = portal.startsWith("http://") || portal.startsWith("https://") ? portal : `https://${portal}`;
  return `${normalized.replace(/\/+$/, "")}/rest`;
}

function isWebhookBase(base) {
  return /\/rest\/\d+\//.test(String(base || ""));
}

function oauthTokenFilePath() {
  return String(process.env.BITRIX_OAUTH_TOKEN_FILE || "/tmp/clawbot-cache/bitrix-oauth.json").trim();
}

function bitrixPortalOrigin(base) {
  const fromEnv = String(process.env.BITRIX_OAUTH_DOMAIN || process.env.BITRIX_PORTAL_URL || "").trim();
  const raw = fromEnv || String(base || "").replace(/\/rest\/.*$/, "");
  if (!raw) return "";
  const withProto = raw.startsWith("http://") || raw.startsWith("https://") ? raw : `https://${raw}`;
  try {
    return new URL(withProto).origin;
  } catch {
    return "";
  }
}

let oauthStatePromise;

async function loadOauthState(base) {
  if (!oauthStatePromise) {
    oauthStatePromise = (async () => {
      const fromEnv = {
        access_token: String(process.env.BITRIX_OAUTH_ACCESS_TOKEN || "").trim(),
        refresh_token: String(process.env.BITRIX_OAUTH_REFRESH_TOKEN || "").trim(),
        expires_at: Number(process.env.BITRIX_OAUTH_EXPIRES_AT || 0),
      };
      const file = oauthTokenFilePath();
      try {
        const raw = await readFile(file, "utf8");
        const parsed = JSON.parse(raw);
        return {
          access_token: fromEnv.access_token || String(parsed?.access_token || "").trim(),
          refresh_token: fromEnv.refresh_token || String(parsed?.refresh_token || "").trim(),
          expires_at: fromEnv.expires_at || Number(parsed?.expires_at || 0),
          domain: bitrixPortalOrigin(base),
        };
      } catch {
        return { ...fromEnv, domain: bitrixPortalOrigin(base) };
      }
    })();
  }
  return oauthStatePromise;
}

async function saveOauthState(state) {
  oauthStatePromise = Promise.resolve(state);
  const file = oauthTokenFilePath();
  try {
    await mkdir(dirname(file), { recursive: true });
    await writeFile(
      file,
      JSON.stringify({
        access_token: state?.access_token || "",
        refresh_token: state?.refresh_token || "",
        expires_at: Number(state?.expires_at || 0),
      }),
      "utf8"
    );
  } catch {
    // ignore token cache write errors
  }
}

async function refreshBitrixOauthToken(base) {
  const state = await loadOauthState(base);
  const refreshToken = String(state?.refresh_token || "").trim();
  const clientId = String(process.env.BITRIX_CLIENT_ID || "").trim();
  const clientSecret = String(process.env.BITRIX_CLIENT_SECRET || "").trim();
  const origin = bitrixPortalOrigin(base);

  if (!refreshToken) throw new Error("Missing env/token: BITRIX_OAUTH_REFRESH_TOKEN");
  if (!clientId || !clientSecret) throw new Error("Missing env: BITRIX_CLIENT_ID or BITRIX_CLIENT_SECRET");
  if (!origin) throw new Error("Missing env: BITRIX_PORTAL_URL or BITRIX_OAUTH_DOMAIN");

  const url = new URL(`${origin}/oauth/token/`);
  url.searchParams.set("grant_type", "refresh_token");
  url.searchParams.set("client_id", clientId);
  url.searchParams.set("client_secret", clientSecret);
  url.searchParams.set("refresh_token", refreshToken);

  const res = await fetch(url);
  if (!res.ok) throw new Error(`Bitrix OAuth error ${res.status}: ${await res.text()}`);
  const payload = await res.json();
  if (payload?.error) throw new Error(`Bitrix OAuth error: ${payload.error_description || payload.error}`);

  const access = String(payload?.access_token || "").trim();
  const nextRefresh = String(payload?.refresh_token || refreshToken).trim();
  const expiresIn = Number(payload?.expires_in || 0);
  if (!access) throw new Error("Bitrix OAuth error: no access_token in response");

  const nextState = {
    access_token: access,
    refresh_token: nextRefresh,
    expires_at: expiresIn > 0 ? Date.now() + expiresIn * 1000 : 0,
    domain: origin,
  };
  await saveOauthState(nextState);
  return nextState.access_token;
}

async function getBitrixAccessToken(base, forceRefresh = false) {
  const state = await loadOauthState(base);
  const token = String(state?.access_token || "").trim();
  const exp = Number(state?.expires_at || 0);
  const isExpired = exp > 0 && Date.now() >= exp - 60 * 1000;

  if (!forceRefresh && token && !isExpired) return token;
  if (String(state?.refresh_token || "").trim()) return refreshBitrixOauthToken(base);
  if (token) return token;
  throw new Error("Missing env/token: BITRIX_OAUTH_ACCESS_TOKEN");
}

async function bitrixCall(base, method, params = {}, options = {}) {
  const oauthMode = !isWebhookBase(base);
  const allowRefresh = options.allowRefresh !== false;

  const run = async (refreshAttempt) => {
    const u = new URL(`${base}/${method}.json`);
    for (const [k, v] of Object.entries(params || {})) {
      if (Array.isArray(v)) {
        for (const item of v) u.searchParams.append(k, String(item));
      } else if (v !== undefined && v !== null) {
        u.searchParams.set(k, String(v));
      }
    }
    if (oauthMode) {
      const token = await getBitrixAccessToken(base, refreshAttempt);
      u.searchParams.set("auth", token);
    }

    const res = await fetch(u);
    if (!res.ok) {
      if (oauthMode && allowRefresh && res.status === 401 && !refreshAttempt) return run(true);
      throw new Error(`Bitrix error ${res.status}: ${await res.text()}`);
    }
    const payload = await res.json();
    if (payload?.error) {
      const errCode = String(payload.error || "");
      const errText = String(payload.error_description || payload.error || "");
      const authErr = /(expired_token|invalid_token|NO_AUTH_FOUND|WRONG_AUTH_TYPE|invalid_grant)/i.test(
        `${errCode} ${errText}`
      );
      if (oauthMode && allowRefresh && authErr && !refreshAttempt) return run(true);
      throw new Error(`Bitrix error: ${errText || errCode}`);
    }
    return payload;
  };

  return run(false);
}

let ownerIdPromise;

async function resolveOwnerId(base) {
  const explicit = Number(process.env.BITRIX_USER_ID || 0);
  if (explicit > 0) return explicit;

  const fromWebhook = parseBitrixUserIdFromWebhook(base);
  if (fromWebhook) return fromWebhook;

  if (!ownerIdPromise) {
    ownerIdPromise = (async () => {
      const payload = await bitrixCall(base, "user.current", {});
      const user = payload?.result;
      const id = Number(user?.ID || user?.id || 0);
      if (!id) throw new Error("Missing/invalid owner id: set BITRIX_USER_ID or provide valid OAuth token");
      return id;
    })();
  }
  return ownerIdPromise;
}

function extractBitrixAttendeeIds(ev, ownerId) {
  const out = new Set();
  for (const a of Array.isArray(ev.ATTENDEE_LIST) ? ev.ATTENDEE_LIST : []) {
    const id = Number(a?.id);
    if (id > 0 && id !== ownerId) out.add(id);
  }
  for (const a of Array.isArray(ev.attendeesEntityList) ? ev.attendeesEntityList : []) {
    if (String(a?.entityId) !== "user") continue;
    const id = Number(a?.id);
    if (id > 0 && id !== ownerId) out.add(id);
  }
  return [...out];
}

function bitrixUserDisplayName(u) {
  const parts = [u?.NAME, u?.LAST_NAME].map((x) => String(x || "").trim()).filter(Boolean);
  const full = parts.join(" ").trim();
  return full || String(u?.ID || "");
}

function formatParticipantNames(names, limit = 5) {
  if (!names.length) return "";
  if (names.length <= limit) return names.join(", ");
  const shown = names.slice(0, limit).join(", ");
  return `${shown} +${names.length - limit}`;
}

function parseOutputLines(text) {
  const rows = String(text || "").split("\n").map((x) => x.trim()).filter(Boolean);
  return rows.filter((r) => /^\d+\.\s+/.test(r));
}

function parseLineEvent(line) {
  const m = String(line).match(/^\d+\.\s+(.+?)\s+—\s+(.+)$/);
  if (!m) return null;
  const slot = m[1].trim();
  const rest = m[2].trim();

  const pm = rest.match(/^(.*?)(?:\s+\(с:\s*(.*?)\))?(?:\s+\[.*\])?$/);
  const title = (pm?.[1] || rest).trim();
  const participantsRaw = String(pm?.[2] || "").trim();
  const participants = participantsRaw
    ? participantsRaw.split(",").map((x) => x.trim()).filter(Boolean)
    : [];

  const sm = slot.match(/^(\d{2}):(\d{2})(?:-(\d{2}):(\d{2}))?/);
  const startMin = sm ? Number(sm[1]) * 60 + Number(sm[2]) : Number.MAX_SAFE_INTEGER;
  const hasRange = Boolean(sm && sm[3] && sm[4]);
  const endMin = hasRange ? Number(sm[3]) * 60 + Number(sm[4]) : startMin;
  return { slot, title, participants, startMin, endMin, hasRange };
}

function normalizeTitle(s) {
  return String(s || "").toLowerCase().replace(/[«»"']/g, "").replace(/\s+/g, " ").trim();
}

function buildOverlapWarnings(items) {
  const timed = items
    .map((e, i) => ({ ...e, idx: i + 1 }))
    .filter((e) => Number.isFinite(e.startMin) && Number.isFinite(e.endMin) && e.endMin > e.startMin)
    .sort((a, b) => (a.startMin - b.startMin) || (a.endMin - b.endMin));

  const warnings = [];
  for (let i = 0; i < timed.length; i++) {
    const a = timed[i];
    for (let j = i + 1; j < timed.length; j++) {
      const b = timed[j];
      if (b.startMin >= a.endMin) break;
      const overlapMin = Math.min(a.endMin, b.endMin) - Math.max(a.startMin, b.startMin);
      if (overlapMin < OVERLAP_MINUTES_THRESHOLD) continue;
      warnings.push(`❗ Накладка: #${a.idx} «${a.title}» пересекается с #${b.idx} «${b.title}».`);
    }
  }
  return warnings;
}

function buildOverlapWarningsFromLines(lines) {
  const parsed = lines
    .map((line) => parseLineEvent(line))
    .filter(Boolean)
    .map((e, i) => ({ ...e, idx: i + 1 }));
  return buildOverlapWarnings(parsed);
}

function mergeBackendTexts(ymd, bitrixText, googleText, status = {}) {
  const bitrixOk = status.bitrixOk !== false;
  const googleOk = status.googleOk !== false;
  const bitrixErr = String(status.bitrixErr || "").trim();
  const googleErr = String(status.googleErr || "").trim();

  const map = new Map();
  const add = (src, line) => {
    const ev = parseLineEvent(line);
    if (!ev) return;
    const key = `${ev.startMin}|${ev.endMin}|${normalizeTitle(ev.title)}`;
    const prev = map.get(key);
    if (!prev) {
      map.set(key, {
        ...ev,
        src,
        sources: new Set([src]),
        slotsBySource: { [src]: ev.slot },
      });
      return;
    }

    const mergedParticipants = [...new Set([...prev.participants, ...ev.participants])];
    const slot = prev.hasRange ? prev.slot : ev.hasRange ? ev.slot : prev.slot;
    const title = prev.title.length >= ev.title.length ? prev.title : ev.title;

    const score = (x) =>
      (x.participants.length ? 100 : 0) +
      (x.hasRange ? 20 : 0) +
      (x.title.length > 0 ? 5 : 0) +
      (x.src === "bitrix" ? 1 : 0);
    const base = score(prev) >= score(ev) ? prev : ev;

    const next = {
      ...base,
      slot,
      title,
      participants: mergedParticipants,
      startMin: Math.min(prev.startMin, ev.startMin),
      endMin: Math.max(prev.endMin, ev.endMin),
      sources: new Set([...(prev.sources || []), src]),
      slotsBySource: { ...(prev.slotsBySource || {}), [src]: ev.slot },
    };
    map.set(key, next);
  };

  for (const line of parseOutputLines(bitrixText)) add("bitrix", line);
  for (const line of parseOutputLines(googleText)) add("google", line);

  const items = [...map.values()].sort((a, b) => {
    if (a.startMin !== b.startMin) return a.startMin - b.startMin;
    return a.title.localeCompare(b.title, "ru");
  });

  const label = `${pad2(ymd.day)}.${pad2(ymd.month)}.${ymd.year}`;
  const sourceWarnings = [];
  if (!bitrixOk) sourceWarnings.push(`⚠ Bitrix недоступен${bitrixErr ? `: ${bitrixErr}` : ""}. Показаны данные из Google.`);
  if (!googleOk) sourceWarnings.push(`⚠ Google недоступен${googleErr ? `: ${googleErr}` : ""}. Показаны данные из Bitrix.`);

  const lines = items.length
    ? items.map((e, i) => {
        const withWho = e.participants.length ? ` (с: ${formatParticipantNames(e.participants)})` : "";
        return `${i + 1}. ${e.slot} — ${e.title}${withWho}`;
      })
    : ["Событий нет."];
  const overlapWarnings = buildOverlapWarningsFromLines(lines);
  return `Календарь на ${label}\n${[...sourceWarnings, ...lines, ...overlapWarnings].join("\n")}`;
}

function googleAttendeeDisplayName(a) {
  const byName = String(a?.displayName || "").trim();
  if (byName) return byName;
  const email = String(a?.email || "").trim();
  if (!email) return "";
  return email.includes("@") ? email.split("@")[0] : email;
}

function normalizedEmailSet(values) {
  const s = new Set();
  for (const v of values) {
    const email = String(v || "").trim().toLowerCase();
    if (email && email.includes("@")) s.add(email);
  }
  return s;
}

function googlePersonDisplayName(p) {
  const byName = String(p?.displayName || "").trim();
  if (byName) return byName;
  const email = String(p?.email || "").trim();
  if (!email) return "";
  return email.includes("@") ? email.split("@")[0] : email;
}

function isGroupCalendarEmail(email) {
  return String(email || "").toLowerCase().endsWith("@group.calendar.google.com");
}

function isTechnicalHandleName(name) {
  return /^[a-z0-9._-]{3,}$/i.test(String(name || "").trim());
}

function hasHumanReadableName(name) {
  const n = String(name || "").trim();
  return /[\sА-Яа-яЁё]/.test(n);
}

function googleSelfEmails() {
  const list = [
    ...parseCsv(process.env.GOOGLE_SELF_EMAILS),
    String(process.env.GOOGLE_CALENDAR_ID || "").trim(),
    ...parseCsv(process.env.GOOGLE_CALENDAR_IDS),
  ];
  return normalizedEmailSet(list);
}

function extractGoogleParticipantNames(ev, selfEmails = new Set()) {
  const out = [];
  const seen = new Set();
  for (const a of Array.isArray(ev?.attendees) ? ev.attendees : []) {
    if (a?.self) continue;
    if (a?.resource) continue;
    if (String(a?.responseStatus || "").toLowerCase() === "declined") continue;
    const attendeeEmail = String(a?.email || "").trim().toLowerCase();
    if (attendeeEmail && selfEmails.has(attendeeEmail)) continue;
    const name = googleAttendeeDisplayName(a);
    if (!name) continue;
    const key = name.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(name);
  }

  if (out.length > 0) {
    const hasHuman = out.some(hasHumanReadableName);
    if (hasHuman) return out.filter((n) => !isTechnicalHandleName(n));
    return out;
  }

  for (const person of [ev?.organizer, ev?.creator]) {
    const email = String(person?.email || "").trim().toLowerCase();
    const displayName = String(person?.displayName || "").trim();
    if (email && selfEmails.has(email)) continue;
    if (out.length > 0 && !displayName) continue;
    // Для календарей-интеграций (group.calendar) берем человекочитаемое имя организатора.
    if (email && isGroupCalendarEmail(email) && !displayName) continue;
    const name = displayName || googlePersonDisplayName(person);
    if (!name) continue;
    const key = name.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(name);
  }
  const hasHuman = out.some(hasHumanReadableName);
  if (hasHuman) return out.filter((n) => !isTechnicalHandleName(n));
  return out;
}

function googleEventRichnessScore(ev, selfEmails = new Set()) {
  let score = 0;
  const participants = extractGoogleParticipantNames(ev, selfEmails);
  score += participants.length * 100;
  if (Array.isArray(ev?.attendees)) score += 10;
  if (String(ev?.creator?.email || "").trim()) score += 3;
  if (String(ev?.organizer?.email || "").trim()) score += 2;
  if (String(ev?.description || "").trim()) score += 1;
  return score;
}

function mergeGoogleEventsForDisplay(baseEv, nextEv, selfEmails = new Set()) {
  const out = { ...baseEv };

  const baseParticipants = extractGoogleParticipantNames(baseEv, selfEmails);
  const nextParticipants = extractGoogleParticipantNames(nextEv, selfEmails);
  if (nextParticipants.length > baseParticipants.length) {
    out.attendees = nextEv.attendees;
    out.creator = nextEv.creator;
    out.organizer = nextEv.organizer;
  } else {
    const baseOrgName = String(baseEv?.organizer?.displayName || "").trim();
    const nextOrgName = String(nextEv?.organizer?.displayName || "").trim();
    if (!baseOrgName && nextOrgName) out.organizer = nextEv.organizer;

    const baseCreatorName = String(baseEv?.creator?.displayName || "").trim();
    const nextCreatorName = String(nextEv?.creator?.displayName || "").trim();
    if (!baseCreatorName && nextCreatorName) out.creator = nextEv.creator;
  }

  const baseDescLen = String(baseEv?.description || "").trim().length;
  const nextDescLen = String(nextEv?.description || "").trim().length;
  if (nextDescLen > baseDescLen) out.description = nextEv.description;

  return out;
}

async function fetchBitrixUsersByIds(base, ids) {
  const loadCache = async () => {
    try {
      const raw = await readFile(BITRIX_USER_CACHE_FILE, "utf8");
      const parsed = JSON.parse(raw);
      return parsed && parsed.items && typeof parsed.items === "object" ? parsed : { v: 1, items: {} };
    } catch {
      return { v: 1, items: {} };
    }
  };
  const saveCache = async (cache) => {
    try {
      await mkdir(dirname(BITRIX_USER_CACHE_FILE), { recursive: true });
      await writeFile(BITRIX_USER_CACHE_FILE, JSON.stringify(cache), "utf8");
    } catch {
      // ignore cache write errors
    }
  };

  const userMap = new Map();
  let scopeDenied = false;
  const cache = await loadCache();
  const now = Date.now();
  const toFetch = [];

  for (const id of ids) {
    const entry = cache.items?.[String(id)];
    if (entry && typeof entry.name === "string" && now - Number(entry.ts || 0) <= BITRIX_USER_CACHE_TTL_MS) {
      userMap.set(Number(id), entry.name);
    } else {
      toFetch.push(id);
    }
  }

  await Promise.all(
    toFetch.map(async (id) => {
      let payload;
      try {
        payload = await bitrixCall(base, "user.get", { ID: id });
      } catch (e) {
        const msg = String(e?.message || e || "");
        if (/insufficient_scope|scope|permission|forbidden/i.test(msg)) {
          scopeDenied = true;
        }
        return;
      }
      if (payload?.error === "insufficient_scope") {
        scopeDenied = true;
        return;
      }
      const row = Array.isArray(payload?.result) ? payload.result[0] : null;
      if (row) {
        const name = bitrixUserDisplayName(row);
        userMap.set(Number(row.ID), name);
        cache.items[String(row.ID)] = { name, ts: now };
      }
    })
  );
  await saveCache(cache);
  return { userMap, scopeDenied };
}

async function listBitrixEventsForDate(ymd, tz = DEFAULT_TZ) {
  const { label, timeMin, timeMax } = buildRange(ymd, tz);
  const base = bitrixBase(process.env.BITRIX_WEBHOOK_BASE);
  const ownerId = await resolveOwnerId(base);

  const payload = await bitrixCall(base, "calendar.event.get", {
    type: "user",
    ownerId,
    from: timeMin,
    to: timeMax,
  });

  const rawItems = Array.isArray(payload.result) ? payload.result : [];
  const items = rawItems.filter((e) => {
    // Bitrix can return canceled/deleted entries in some setups; hide them from user schedule.
    if (String(e?.DELETED || "N").toUpperCase() === "Y") return false;
    const eventStatus = String(e?.STATUS || e?.MEETING_STATUS || "").toUpperCase();
    if (eventStatus === "N" || eventStatus === "CANCELED" || eventStatus === "CANCELLED") return false;
    const start = bitrixEventStartYmd(e, tz);
    return start ? ymdEquals(start, ymd) : false;
  });
  const dedup = [];
  const seen = new Set();
  for (const e of items) {
    const key = `${e.NAME || ""}|${e.DATE_FROM || ""}|${e.DATE_TO || ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    dedup.push(e);
  }

  dedup.sort((a, b) => {
    const sa = minutesOfDayFromBitrix(a);
    const sb = minutesOfDayFromBitrix(b);
    if (sa !== sb) return sa - sb;
    const ea = endMinutesOfDayFromBitrix(a);
    const eb = endMinutesOfDayFromBitrix(b);
    if (ea !== eb) return ea - eb;
    return String(a.NAME || "").localeCompare(String(b.NAME || ""), "ru");
  });

  const attendeeIdSet = new Set();
  for (const e of dedup) {
    for (const id of extractBitrixAttendeeIds(e, ownerId)) attendeeIdSet.add(id);
  }
  const { userMap: attendeeNames, scopeDenied } = attendeeIdSet.size
    ? await fetchBitrixUsersByIds(base, [...attendeeIdSet])
    : { userMap: new Map(), scopeDenied: false };

  const lines = dedup.length
    ? dedup.map((e, i) => {
        const ids = extractBitrixAttendeeIds(e, ownerId);
        const names = ids.map((id) => attendeeNames.get(id)).filter(Boolean);
        const withWho = names.length
          ? ` (с: ${formatParticipantNames(names)})`
          : ids.length
            ? scopeDenied
              ? ` (с участниками: ${ids.length} чел.; для имен добавьте право user в вебхуке Bitrix)`
              : ` (с участниками: ${ids.length} чел.)`
            : "";
        return `${i + 1}. ${slotTextBitrix(e)} — ${e.NAME || "(без названия)"}${withWho}`;
      })
    : ["Событий нет."];

  return `Календарь на ${label}\n${lines.join("\n")}`;
}

async function listCalendarsFromCalendarList(calendar) {
  const out = [];
  let pageToken;
  do {
    const res = await calendar.calendarList.list({ maxResults: 250, pageToken });
    for (const c of res.data.items || []) {
      if (c.id) out.push({ id: c.id, summary: c.summary || c.id });
    }
    pageToken = res.data.nextPageToken || undefined;
  } while (pageToken);
  return out;
}

async function resolveGoogleTargets(calendar) {
  const byId = new Map();

  for (const id of parseCsv(process.env.GOOGLE_CALENDAR_IDS)) byId.set(id, { id, summary: id });

  const single = String(process.env.GOOGLE_CALENDAR_ID || "").trim();
  const includeAllById = single === "*" || single.toLowerCase() === "all";
  if (single && !includeAllById) byId.set(single, { id: single, summary: single });

  const includeAll = includeAllById || parseBool(process.env.GOOGLE_CALENDAR_INCLUDE_ALL);
  if (includeAll) {
    try {
      const list = await listCalendarsFromCalendarList(calendar);
      for (const c of list) byId.set(c.id, c);
    } catch {
      // ignore
    }
  }

  if (byId.size === 0) throw new Error("Нет доступных календарей Google.");
  return [...byId.values()];
}

function eventSortKeyGoogle(ev) {
  if (ev.start?.dateTime) return new Date(ev.start.dateTime).getTime();
  if (ev.start?.date) return new Date(`${ev.start.date}T00:00:00Z`).getTime();
  return Number.MAX_SAFE_INTEGER;
}

function eventDedupKeyGoogle(ev) {
  const start = ev.start?.dateTime || ev.start?.date || "";
  return `${ev.iCalUID || ev.id || ""}|${start}|${ev.summary || ""}`;
}

async function listGoogleEventsForDate(ymd, tz = DEFAULT_TZ) {
  await readFile(process.env.GOOGLE_SERVICE_ACCOUNT_JSON, "utf8");

  const auth = new google.auth.GoogleAuth({
    keyFile: process.env.GOOGLE_SERVICE_ACCOUNT_JSON,
    scopes: ["https://www.googleapis.com/auth/calendar.readonly"],
  });

  const calendar = google.calendar({ version: "v3", auth });
  const { timeMin, timeMax, label } = buildRange(ymd, tz);
  const targets = await resolveGoogleTargets(calendar);

  const results = await Promise.all(
    targets.map(async (t) => {
      try {
        const res = await calendar.events.list({
          calendarId: t.id,
          timeMin,
          timeMax,
          singleEvents: true,
          orderBy: "startTime",
          maxResults: 250,
        });
        return { target: t, items: res.data.items || [], error: "" };
      } catch (e) {
        return { target: t, items: [], error: e?.message || "ошибка" };
      }
    })
  );

  if (results.length > 0 && results.every((r) => String(r.error || "").trim())) {
    const details = results
      .slice(0, 3)
      .map((r) => `${r.target.id}: ${r.error}`)
      .join("; ");
    throw new Error(`Google недоступен: ${details}`);
  }

  const merged = [];
  const calNames = new Map();
  for (const r of results) {
    calNames.set(r.target.id, r.target.summary || r.target.id);
    for (const e of r.items) merged.push({ ...e, _calendarId: r.target.id });
  }

  const selfEmails = googleSelfEmails();
  const bestByKey = new Map();
  for (const e of merged) {
    const k = eventDedupKeyGoogle(e);
    const prev = bestByKey.get(k);
    if (!prev) {
      bestByKey.set(k, e);
      continue;
    }
    const mergedEv = mergeGoogleEventsForDisplay(prev, e, selfEmails);
    const prevScore = googleEventRichnessScore(prev, selfEmails);
    const nextScore = googleEventRichnessScore(mergedEv, selfEmails);
    if (nextScore >= prevScore) bestByKey.set(k, mergedEv);
  }
  const dedup = [...bestByKey.values()];

  dedup.sort((a, b) => eventSortKeyGoogle(a) - eventSortKeyGoogle(b));

  const showCalendarLabel = targets.length > 1;
  const lines = dedup.length
    ? dedup.map((e, i) => {
        const participants = extractGoogleParticipantNames(e, selfEmails);
        const withWho = participants.length ? ` (с: ${formatParticipantNames(participants)})` : "";
        const base = `${i + 1}. ${startTextGoogle(e, tz)} — ${e.summary ?? "(без названия)"}${withWho}`;
        if (!showCalendarLabel) return base;
        const name = calNames.get(e._calendarId) || e._calendarId || "календарь";
        return `${base} [${name}]`;
      })
    : ["Событий нет."];

  return `Календарь на ${label}\n${lines.join("\n")}`;
}

function splitTelegramText(text, maxLen = 3900) {
  const src = String(text || "");
  if (!src) return [""];
  if (src.length <= maxLen) return [src];

  const chunks = [];
  let rest = src;
  while (rest.length > maxLen) {
    let cut = rest.lastIndexOf("\n\n", maxLen);
    if (cut < Math.floor(maxLen * 0.6)) cut = rest.lastIndexOf("\n", maxLen);
    if (cut < Math.floor(maxLen * 0.4)) cut = maxLen;
    const piece = rest.slice(0, cut).trim();
    chunks.push(piece);
    rest = rest.slice(cut).trim();
  }
  if (rest) chunks.push(rest);
  return chunks;
}

async function sendTelegram(text) {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  const buildBoldEntities = (raw) => {
    const entities = [];
    const re = /\(с:\s*([^)]+)\)/g;
    for (const m of String(raw).matchAll(re)) {
      const full = m[0];
      const group = m[1] || "";
      const matchStart = Number(m.index || 0);
      const groupStart = matchStart + full.indexOf(group);
      let cursor = 0;
      for (const part of group.split(",")) {
        const at = group.indexOf(part, cursor);
        if (at < 0) continue;
        cursor = at + part.length;
        const leadWs = (part.match(/^\s*/) || [""])[0].length;
        const trimmed = part.trim();
        if (!trimmed) continue;
        const nm = trimmed.match(/^(.*?)(\s+\+\d+)?$/);
        const name = (nm?.[1] || trimmed).trim();
        if (!name) continue;
        const namePos = trimmed.indexOf(name);
        const offset = groupStart + at + leadWs + namePos;
        entities.push({ offset, length: name.length, type: "bold" });
      }
    }
    return entities;
  };

  for (const chunk of splitTelegramText(text)) {
    const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text: chunk,
        entities: buildBoldEntities(chunk),
        disable_web_page_preview: true,
      }),
    });
    if (!res.ok) throw new Error(`Telegram error ${res.status}: ${await res.text()}`);
  }
}

async function listEventsForDate(ymd, tz = DEFAULT_TZ) {
  const backend = getBackend();
  if (backend === "combined" || backend === "merge" || backend === "both") {
    const [b, g] = await Promise.allSettled([
      listBitrixEventsForDate(ymd, tz),
      listGoogleEventsForDate(ymd, tz),
    ]);
    const bitrixOk = b.status === "fulfilled";
    const googleOk = g.status === "fulfilled";
    if (!bitrixOk && !googleOk) {
      const bErr = b.status === "rejected" ? (b.reason?.message || String(b.reason || "")) : "";
      const gErr = g.status === "rejected" ? (g.reason?.message || String(g.reason || "")) : "";
      throw new Error(`Оба источника недоступны. Bitrix: ${bErr || "ошибка"}; Google: ${gErr || "ошибка"}`);
    }
    const bitrixText = bitrixOk ? b.value : "";
    const googleText = googleOk ? g.value : "";
    const bitrixErr = !bitrixOk ? (b.reason?.message || String(b.reason || "")) : "";
    const googleErr = !googleOk ? (g.reason?.message || String(g.reason || "")) : "";
    return mergeBackendTexts(ymd, bitrixText, googleText, { bitrixOk, googleOk, bitrixErr, googleErr });
  }
  if (backend === "bitrix") return listBitrixEventsForDate(ymd, tz);
  return listGoogleEventsForDate(ymd, tz);
}

export async function queryScheduleByText(rawDateQuery, options = {}) {
  const tz = options.tz || DEFAULT_TZ;
  const send = Boolean(options.sendTelegram);

  validateRequiredEnv(send);
  const ymd = parseDateQuery(rawDateQuery, tz);
  const text = await listEventsForDate(ymd, tz);

  if (send) await sendTelegram(text);
  return text;
}

async function main() {
  const args = process.argv.slice(2);
  const sendTelegramFlag = args.includes("--send-telegram");
  const query = args.filter((a) => a !== "--send-telegram").join(" ").trim();

  const text = await queryScheduleByText(query, { sendTelegram: sendTelegramFlag });

  if (sendTelegramFlag) {
    console.log("OK");
    return;
  }
  console.log(text);
}

main().catch((err) => {
  console.error(err.message || String(err));
  process.exit(1);
});
