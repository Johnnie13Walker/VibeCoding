import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import process from "node:process";

const TZ = process.env.TZ || "Europe/Moscow";
const BITRIX_HTTP_TIMEOUT_MS = Math.max(3_000, Number(process.env.BITRIX_HTTP_TIMEOUT_MS || 15_000));
const BITRIX_HTTP_RETRIES = Math.max(0, Math.min(3, Number(process.env.BITRIX_HTTP_RETRIES || 2)));

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

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function getTodayYmdInTz(tz) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());

  return {
    year: Number(parts.find((p) => p.type === "year")?.value),
    month: Number(parts.find((p) => p.type === "month")?.value),
    day: Number(parts.find((p) => p.type === "day")?.value),
  };
}

function makeValidYmd(year, month, day) {
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) return null;
  const dt = new Date(Date.UTC(year, month - 1, day));
  if (dt.getUTCFullYear() !== year || dt.getUTCMonth() + 1 !== month || dt.getUTCDate() !== day) return null;
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

function parseDateFromText(raw, tz = TZ) {
  const q = String(raw || "").toLowerCase().replace(/\s+/g, " ");
  const today = getTodayYmdInTz(tz);

  if (q.includes("послезавтра")) return addDays(today, 2);
  if (q.includes("завтра")) return addDays(today, 1);
  if (q.includes("сегодня")) return today;

  let m = q.match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (m) {
    const ymd = makeValidYmd(Number(m[1]), Number(m[2]), Number(m[3]));
    if (!ymd) throw new Error(`Невалидная дата: "${m[0]}"`);
    return ymd;
  }

  m = q.match(/(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?/);
  if (m) {
    const year = m[3] ? Number(m[3]) : today.year;
    const ymd = makeValidYmd(year, Number(m[2]), Number(m[1]));
    if (!ymd) throw new Error(`Невалидная дата: "${m[0]}"`);
    return ymd;
  }

  m = q.match(/(\d{1,2})\s+([а-яё]+)(?:\s+(\d{4}))?/u);
  if (m) {
    const day = Number(m[1]);
    const month = RU_MONTHS[m[2]];
    const year = m[3] ? Number(m[3]) : today.year;
    if (!month) throw new Error(`Невалидная дата: "${m[0]}"`);
    const ymd = makeValidYmd(year, month, day);
    if (!ymd) throw new Error(`Невалидная дата: "${m[0]}"`);
    return ymd;
  }

  throw new Error("Не смог распознать дату. Пример: 20.02.2026, 20 февраля, завтра");
}

function parseTimeFromText(raw) {
  const q = String(raw || "").toLowerCase();
  const m = q.match(/(?:в|с)\s*(\d{1,2})[:.](\d{2})/);
  if (!m) throw new Error("Не смог распознать время. Пример: в 11:00");
  const hh = Number(m[1]);
  const mm = Number(m[2]);
  if (hh < 0 || hh > 23 || mm < 0 || mm > 59) throw new Error(`Невалидное время: ${m[0]}`);
  return { hh, mm };
}

function parseDurationMinutes(raw) {
  const q = String(raw || "").toLowerCase();
  let m = q.match(/длител(?:ьность|ьностью)?\s*(\d+)\s*(мин(?:ут[аы]?)?|час(?:а|ов)?)/);
  if (!m) m = q.match(/в\s*\d{1,2}[:.]\d{2}.*на\s*(\d+)\s*(мин(?:ут[аы]?)?|час(?:а|ов)?)/);
  if (!m) return 60;
  const n = Number(m[1]);
  const unit = m[2] || "";
  if (!Number.isFinite(n) || n <= 0) return 60;
  return unit.startsWith("час") ? n * 60 : n;
}

function extractInviteeQueries(raw) {
  const trimPersonCandidate = (chunk) => {
    const words = String(chunk || "")
      .trim()
      .split(/\s+/u)
      .filter(Boolean);
    if (words.length <= 2) return words.join(" ");
    const third = words[2].toLowerCase();
    const isPatronymic = /(ович|евич|ич|овна|евна|ична|кызы|оглы)$/u.test(third);
    return isPatronymic ? words.slice(0, 3).join(" ") : words.slice(0, 2).join(" ");
  };

  const src = String(raw || "").trim();
  const m = src.match(/(?:^|\s)с\s+(.+)$/iu);
  if (!m) return [];

  let tail = m[1];
  // If the meeting title starts in quotes, stop invitee parsing before it.
  const quoteIdx = tail.search(/[«"]/u);
  if (quoteIdx >= 0) tail = tail.slice(0, quoteIdx);
  const stopAt = tail.search(
    /(?:^|\s)(?:в\s*\d{1,2}[:.]\d{2}|на\s+\d{1,2}[.]\d{1,2}(?:[.]\d{4})?|на\s+\d{4}-\d{1,2}-\d{1,2}|на\s*\d+\s*(?:мин(?:ут[аы]?)?|час(?:а|ов)?)|длител|названи|тема|все\s+правильно|всё\s+правильно|создавай|игнорируй|несмотря)/iu
  );
  if (stopAt >= 0) tail = tail.slice(0, stopAt);
  tail = tail.replace(/["«»]/g, " ").replace(/[.?!;]+$/g, " ").trim();
  if (!tail) return [];

  return tail
    .split(/\s*(?:,|\s+и\s+)\s*/iu)
    .map((x) => trimPersonCandidate(x))
    .filter(Boolean)
    .slice(0, 5);
}

function parseTitle(raw) {
  const sanitizeTitle = (s) =>
    String(s || "")
      .replace(/все правильно,?\s*создавай/giu, " ")
      .replace(/всё правильно,?\s*создавай/giu, " ")
      .replace(/создавай несмотря[^,.;\n]*/giu, " ")
      .replace(/игнорируй накладк[^,.;\n]*/giu, " ")
      .replace(/\s+/g, " ")
      .trim();

  const q = String(raw || "").trim();
  let m = q.match(/[«"]([^»"]+)[»"]/);
  if (m) return sanitizeTitle(m[1]);

  m = q.match(/(?:названи[ея]|тема)\s*[:\-]?\s*(.+)$/i);
  if (m) return sanitizeTitle(m[1]);

  const cleaned = q
    .replace(/поставь( мне)? встречу/gi, "")
    .replace(/создай встречу/gi, "")
    .replace(/на\s+\d{1,2}[.]\d{1,2}(?:[.]\d{4})?/gi, "")
    .replace(/на\s+\d{4}-\d{1,2}-\d{1,2}/gi, "")
    .replace(/на\s+\d{1,2}\s+[а-яё]+(?:\s+\d{4})?/giu, "")
    .replace(/(?:в|с)\s*\d{1,2}[:.]\d{2}/gi, "")
    .replace(/(?:^|\s)с\s+[а-яёa-z][^,.;\n]+/giu, " ")
    .replace(/все правильно,?\s*создавай/giu, " ")
    .replace(/всё правильно,?\s*создавай/giu, " ")
    .replace(/создавай несмотря[^,.;\n]*/giu, " ")
    .replace(/игнорируй накладк[^,.;\n]*/giu, " ")
    .replace(/длител(?:ьность|ьностью)?\s*\d+\s*(мин(?:ут[аы]?)?|час(?:а|ов)?)/gi, "")
    .replace(/на\s*\d+\s*(мин(?:ут[аы]?)?|час(?:а|ов)?)/gi, "")
    .replace(/\s+/g, " ")
    .trim();

  return sanitizeTitle(cleaned) || "Встреча";
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

  if (String(state?.refresh_token || "").trim()) {
    return refreshBitrixOauthToken(base);
  }

  if (token) return token;
  throw new Error("Missing env/token: BITRIX_OAUTH_ACCESS_TOKEN");
}

async function bitrixCall(base, method, params = {}, options = {}) {
  const oauthMode = !isWebhookBase(base);
  const allowRefresh = options.allowRefresh !== false;
  const timeoutMs = Math.max(1_000, Number(options.timeoutMs || BITRIX_HTTP_TIMEOUT_MS));

  const run = async (refreshAttempt, retryAttempt = 0) => {
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

    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), timeoutMs);
    let res;
    try {
      res = await fetch(u, { signal: ctl.signal });
    } catch (err) {
      clearTimeout(timer);
      const transient = /AbortError|ECONNRESET|ETIMEDOUT|EAI_AGAIN|network|fetch failed/i.test(
        String(err?.name || "") + " " + String(err?.message || err || "")
      );
      if (transient && retryAttempt < BITRIX_HTTP_RETRIES) {
        await sleep(250 * (retryAttempt + 1));
        return run(refreshAttempt, retryAttempt + 1);
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }

    if (!res.ok) {
      if (oauthMode && allowRefresh && res.status === 401 && !refreshAttempt) {
        return run(true, retryAttempt);
      }
      const transientStatus = [408, 425, 429, 500, 502, 503, 504].includes(res.status);
      if (transientStatus && retryAttempt < BITRIX_HTTP_RETRIES) {
        await sleep(250 * (retryAttempt + 1));
        return run(refreshAttempt, retryAttempt + 1);
      }
      throw new Error(`Bitrix error ${res.status}: ${await res.text()}`);
    }
    const payload = await res.json();
    if (payload?.error) {
      const errCode = String(payload.error || "");
      const errText = String(payload.error_description || payload.error || "");
      const authErr = /(expired_token|invalid_token|NO_AUTH_FOUND|WRONG_AUTH_TYPE|invalid_grant)/i.test(
        `${errCode} ${errText}`
      );
      if (oauthMode && allowRefresh && authErr && !refreshAttempt) {
        return run(true, retryAttempt);
      }
      throw new Error(`Bitrix error: ${errText || errCode}`);
    }
    return payload;
  };

  return run(false, 0);
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

function formatBitrixDateTime(ymd, hh, mm) {
  return `${pad2(ymd.day)}.${pad2(ymd.month)}.${ymd.year} ${pad2(hh)}:${pad2(mm)}:00`;
}

function addMinutes(hh, mm, minutes) {
  const total = hh * 60 + mm + minutes;
  const dayShift = Math.floor(total / (24 * 60));
  const minuteOfDay = ((total % (24 * 60)) + (24 * 60)) % (24 * 60);
  const endH = Math.floor(minuteOfDay / 60);
  const endM = minuteOfDay % 60;
  return { hh: endH, mm: endM, dayShift };
}

function shiftYmd(ymd, days) {
  const dt = new Date(Date.UTC(ymd.year, ymd.month - 1, ymd.day + days));
  return {
    year: dt.getUTCFullYear(),
    month: dt.getUTCMonth() + 1,
    day: dt.getUTCDate(),
  };
}

function minutesFromBitrixDateTime(v) {
  const m = String(v || "").match(/^(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})(?::\d{2})?$/);
  if (!m) return null;
  return {
    year: Number(m[3]),
    month: Number(m[2]),
    day: Number(m[1]),
    hh: Number(m[4]),
    mm: Number(m[5]),
    min: Number(m[4]) * 60 + Number(m[5]),
  };
}

function eventSlotText(ev) {
  const s = minutesFromBitrixDateTime(ev?.DATE_FROM);
  const e = minutesFromBitrixDateTime(ev?.DATE_TO);
  if (!s) return "Без времени";
  const start = `${pad2(s.hh)}:${pad2(s.mm)}`;
  if (!e) return start;
  const end = `${pad2(e.hh)}:${pad2(e.mm)}`;
  return `${start}-${end}`;
}

function buildDayBoundary(ymd, end = false) {
  return `${pad2(ymd.day)}.${pad2(ymd.month)}.${ymd.year} ${end ? "23:59:59" : "00:00:00"}`;
}

async function fetchBitrixDayEvents(base, ownerId, ymd) {
  const payload = await bitrixCall(base, "calendar.event.get", {
    type: "user",
    ownerId,
    from: buildDayBoundary(ymd, false),
    to: buildDayBoundary(ymd, true),
  });
  return Array.isArray(payload?.result) ? payload.result : [];
}

function hasOverlapOverride(raw) {
  return /(все правильно|всё правильно|да создавай|ок создавай|создавай несмотря|игнорируй накладк)/iu.test(
    String(raw || "")
  );
}

function findOverlaps(events, startMin, endMin, titleNorm) {
  const out = [];
  const seen = new Set();
  for (const ev of events) {
    if (String(ev?.DT_SKIP_TIME || "N") === "Y") continue;
    const s = minutesFromBitrixDateTime(ev?.DATE_FROM);
    const e = minutesFromBitrixDateTime(ev?.DATE_TO);
    if (!s || !e) continue;
    const sameTitle = normalizeRus(ev?.NAME || "") === titleNorm;
    if (sameTitle) continue;
    if (Math.min(endMin, e.min) > Math.max(startMin, s.min)) {
      const key = `${normalizeRus(ev?.NAME || "")}|${eventSlotText(ev)}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(ev);
    }
  }
  return out;
}

function normalizeRus(s) {
  return String(s || "")
    .toLowerCase()
    .replace(/ё/g, "е")
    .replace(/[^\p{L}\p{N}\s-]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function stemRu(w) {
  let s = normalizeRus(w);
  const suffixes = ["ыми", "ими", "ого", "ему", "ому", "ыми", "ыми", "ами", "ями", "ов", "ев", "ом", "ем", "ой", "ей", "ым", "им", "ую", "юю", "ая", "яя", "ах", "ях", "ы", "и", "а", "я", "у", "ю", "е"];
  for (const suf of suffixes) {
    if (s.length > 4 && s.endsWith(suf)) {
      s = s.slice(0, -suf.length);
      break;
    }
  }
  return s;
}

function userDisplayName(u) {
  const parts = [u?.NAME, u?.LAST_NAME].map((x) => String(x || "").trim()).filter(Boolean);
  return parts.join(" ").trim() || String(u?.ID || "");
}

function userEmails(u) {
  return [
    u?.EMAIL,
    u?.PERSONAL_MAILBOX,
    u?.UF_EMAIL,
    u?.UF_MAIL,
  ]
    .flatMap((x) => (Array.isArray(x) ? x : [x]))
    .map((x) => String(x || "").trim().toLowerCase())
    .filter((x) => x.includes("@"));
}

function tokenScore(queryToken, userToken) {
  const q = normalizeRus(queryToken);
  const u = normalizeRus(userToken);
  if (!q || !u) return 0;
  if (q === u) return 100;
  if (u.startsWith(q) || q.startsWith(u)) return 90;
  const qs = stemRu(q);
  const us = stemRu(u);
  if (qs && us && qs === us) return 85;
  if (qs && us && (us.startsWith(qs) || qs.startsWith(us))) return 75;
  if (u.includes(q) || q.includes(u)) return 60;
  return 0;
}

function scoreUserMatch(query, user) {
  const qTokens = normalizeRus(query).split(" ").filter(Boolean);
  if (qTokens.length === 0) return 0;

  const userTokens = [user?.NAME, user?.LAST_NAME, `${user?.NAME || ""} ${user?.LAST_NAME || ""}`]
    .flatMap((x) => normalizeRus(x).split(" ").filter(Boolean));

  let sum = 0;
  for (const qt of qTokens) {
    let best = 0;
    for (const ut of userTokens) best = Math.max(best, tokenScore(qt, ut));
    sum += best;
  }

  if (qTokens.length >= 2) {
    const q1 = qTokens[0];
    const q2 = qTokens[1];
    const first = normalizeRus(user?.NAME || "");
    const last = normalizeRus(user?.LAST_NAME || "");
    const pairA = tokenScore(q1, first) + tokenScore(q2, last);
    const pairB = tokenScore(q1, last) + tokenScore(q2, first);
    sum = Math.max(sum, pairA, pairB);

    // Explicit support for both "Имя Фамилия" and "Фамилия Имя"
    const qStem = qTokens.map(stemRu).join(" ").trim();
    const flStem = `${stemRu(user?.NAME || "")} ${stemRu(user?.LAST_NAME || "")}`.trim();
    const lfStem = `${stemRu(user?.LAST_NAME || "")} ${stemRu(user?.NAME || "")}`.trim();
    if (qStem && (qStem === flStem || qStem === lfStem)) sum = Math.max(sum, 200);
  }

  return Math.round(sum / qTokens.length);
}

function isExEmployeeUser(u) {
  const bool = (v) => ["1", "y", "yes", "true"].includes(String(v || "").trim().toLowerCase());
  const hasDismissalDate = (v) => /^\d{4}-\d{2}-\d{2}/.test(String(v || "").trim()) || /^\d{2}\.\d{2}\.\d{4}/.test(String(v || "").trim());
  if (bool(u?.UF_IS_EX_EMPLOYEE) || bool(u?.UF_EX_EMPLOYEE) || bool(u?.UF_TERMINATED) || bool(u?.UF_FIRED)) return true;
  if (hasDismissalDate(u?.UF_DISMISSAL_DATE) || hasDismissalDate(u?.UF_USER_DISMISSAL_DATE)) return true;
  const status = String(u?.STATUS || u?.EMPLOYMENT_STATUS || "").toLowerCase();
  if (/dismiss|fired|terminated|уволен/.test(status)) return true;
  return false;
}

async function fetchBitrixActiveUsers(base) {
  const call = async (withFilter) => {
    const all = [];
    let start = 0;
    while (true) {
      const params = withFilter ? { "FILTER[ACTIVE]": "Y", start } : { start };
      const payload = await bitrixCall(base, "user.get", params);
      const chunk = Array.isArray(payload?.result) ? payload.result : [];
      all.push(...chunk);
      const next = Number(payload?.next || 0);
      if (!next || chunk.length === 0 || next <= start) break;
      start = next;
    }
    return all;
  };

  let users = [];
  try {
    users = await call(true);
  } catch {
    users = await call(false);
  }

  return users.filter((u) => {
    const active = String(u?.ACTIVE || "").toUpperCase();
    const isActive = active === "Y" || active === "1" || active === "TRUE";
    return isActive && !isExEmployeeUser(u);
  });
}

function resolveInvitees(inviteeQueries, activeUsers) {
  if (!inviteeQueries.length) return { attendeeIds: [], attendeeNames: [] };

  const ids = new Set();
  const names = [];

  for (const raw of inviteeQueries) {
    const q = String(raw || "").trim();
    const idDirect = q.match(/(?:^|[\s#])(?:id[:\s-]*)?(\d{1,10})$/i);
    if (idDirect) {
      const id = Number(idDirect[1]);
      const exactById = activeUsers.find((u) => Number(u?.ID) === id);
      if (!exactById) {
        throw new Error(`Не нашел активного сотрудника по ID ${id}.`);
      }
      ids.add(Number(exactById.ID));
      names.push(userDisplayName(exactById));
      continue;
    }

    if (q.includes("@")) {
      const email = q.toLowerCase();
      const exactByEmail = activeUsers.find((u) => userEmails(u).includes(email));
      if (exactByEmail) {
        ids.add(Number(exactByEmail.ID));
        names.push(userDisplayName(exactByEmail));
        continue;
      }
    }

    const scored = activeUsers
      .map((u) => ({ u, score: scoreUserMatch(raw, u) }))
      .filter((x) => x.score >= 65)
      .sort((a, b) => b.score - a.score);

    if (scored.length === 0) {
      const hint = activeUsers.slice(0, 8).map((u) => userDisplayName(u)).join(", ");
      throw new Error(
        `Не нашел сотрудника "${raw}" среди активных пользователей Bitrix. Уточни ФИО, email или ID. Примеры: ${hint}`
      );
    }

    if (scored.length > 1 && scored[0].score - scored[1].score < 10) {
      const top = scored.slice(0, 5).map((x) => `${userDisplayName(x.u)} (ID ${x.u.ID})`).join(", ");
      throw new Error(`Неоднозначно, кого пригласить для "${raw}". Уточни ФИО. Варианты: ${top}`);
    }

    const best = scored[0].u;
    ids.add(Number(best.ID));
    names.push(userDisplayName(best));
  }

  return { attendeeIds: [...ids], attendeeNames: [...new Set(names)] };
}

function splitPersonList(raw) {
  const trimPersonCandidate = (chunk) => {
    const words = String(chunk || "")
      .trim()
      .split(/\s+/u)
      .filter(Boolean);
    if (words.length <= 2) return words.join(" ");
    const third = words[2].toLowerCase();
    const isPatronymic = /(ович|евич|ич|овна|евна|ична|кызы|оглы)$/u.test(third);
    return isPatronymic ? words.slice(0, 3).join(" ") : words.slice(0, 2).join(" ");
  };

  return String(raw || "")
    .split(/\s*(?:,|\s+и\s+)\s*/iu)
    .map((x) => trimPersonCandidate(x))
    .filter(Boolean)
    .slice(0, 5);
}

function parseAddParticipantsIntent(rawText) {
  const text = String(rawText || "").trim();
  const m = text.match(
    /^\s*добав(?:ь|ить)\s+(?:участник[аоуы]?\s+)?(.+?)\s+(?:в|во)\s+(?:эту\s+)?встреч[ауеи]\s+(.+)$/iu
  );
  if (!m) return null;

  const inviteeQueries = splitPersonList(m[1]);
  const eventQuery = String(m[2] || "").trim();
  if (!inviteeQueries.length) {
    throw new Error("Не смог распознать, кого добавить. Пример: добавь Ивана Петрова в встречу ...");
  }
  if (!eventQuery) {
    throw new Error("Не смог распознать, в какую встречу добавить. Укажи дату/время или точное название.");
  }
  return { inviteeQueries, eventQuery };
}

function splitCancelAndCreate(rawText) {
  const text = String(rawText || "").trim();
  const m = text.match(/^(.*?)(?:\s+(?:и\s+)?(?:поставь|создай)\s+)(.+)$/iu);
  if (!m) return { cancelPart: text, createPart: "" };
  return { cancelPart: m[1].trim(), createPart: `создай ${m[2].trim()}` };
}

async function deleteBitrixEvent(base, ownerId, id) {
  const payload = await bitrixCall(base, "calendar.event.delete", { id, type: "user", ownerId });
  return payload?.result;
}

function extractEventCandidateTitle(queryPart) {
  const src = String(queryPart || "").trim();
  let m = src.match(/[«"]([^»"]+)[»"]/);
  if (m) return m[1].trim();
  return src
    .replace(/на\s+\d{1,2}[.]\d{1,2}(?:[.]\d{4})?/giu, " ")
    .replace(/на\s+\d{4}-\d{1,2}-\d{1,2}/giu, " ")
    .replace(/на\s+\d{1,2}\s+[а-яё]+(?:\s+\d{4})?/giu, " ")
    .replace(/в\s*\d{1,2}[:.]\d{2}/giu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

async function findTargetEventByText(queryPart, base, ownerId) {
  const ymd = parseDateFromText(queryPart, TZ);
  const time = (() => {
    try {
      return parseTimeFromText(queryPart);
    } catch {
      return null;
    }
  })();
  const titleQ = extractEventCandidateTitle(queryPart);
  const titleNorm = normalizeRus(titleQ);

  const events = await fetchBitrixDayEvents(base, ownerId, ymd);
  const filtered = events
    .filter((e) => String(e?.DELETED || "N") !== "Y")
    .map((e) => {
      const s = minutesFromBitrixDateTime(e?.DATE_FROM);
      const scoreTitle = titleNorm ? tokenScore(titleNorm, normalizeRus(e?.NAME || "")) : 0;
      const scoreTime =
        time && s ? (time.hh === s.hh && time.mm === s.mm ? 100 : Math.max(0, 70 - Math.abs(time.hh * 60 + time.mm - s.min))) : 0;
      const score = scoreTitle * 2 + scoreTime;
      return { e, score };
    })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score);

  if (filtered.length === 0) {
    const hints = events.slice(0, 6).map((e) => `${eventSlotText(e)} ${e?.NAME || "(без названия)"}`).join("; ");
    throw new Error(`Не нашел встречу. Уточни точнее название/время. Примеры в этот день: ${hints || "нет событий"}`);
  }

  if (filtered.length > 1 && filtered[0].score - filtered[1].score < 15) {
    const options = filtered
      .slice(0, 5)
      .map((x) => `${eventSlotText(x.e)} — ${x.e?.NAME || "(без названия)"} (ID ${x.e?.ID})`)
      .join("; ");
    throw new Error(`Неоднозначно, какую встречу выбрать. Уточни точное название или время. Варианты: ${options}`);
  }

  return filtered[0].e;
}

function extractExistingAttendeeIds(ev, ownerId) {
  const ids = new Set();
  for (const row of Array.isArray(ev?.ATTENDEE_LIST) ? ev.ATTENDEE_LIST : []) {
    const id = Number(row?.id);
    if (id > 0 && id !== ownerId) ids.add(id);
  }
  for (const row of Array.isArray(ev?.attendeesEntityList) ? ev.attendeesEntityList : []) {
    if (String(row?.entityId) !== "user") continue;
    const id = Number(row?.id);
    if (id > 0 && id !== ownerId) ids.add(id);
  }
  for (const code of Array.isArray(ev?.ATTENDEES_CODES) ? ev.ATTENDEES_CODES : []) {
    const m = String(code || "").match(/^U(\d+)$/);
    if (!m) continue;
    const id = Number(m[1]);
    if (id > 0 && id !== ownerId) ids.add(id);
  }
  return [...ids];
}

async function updateBitrixEventParticipants(base, ownerId, ev, addIds) {
  const currentIds = extractExistingAttendeeIds(ev, ownerId);
  const currentSet = new Set(currentIds);
  const mergedSet = new Set(currentIds);
  for (const id of addIds) {
    if (id > 0 && id !== ownerId) mergedSet.add(Number(id));
  }

  const addedIds = [...mergedSet].filter((id) => !currentSet.has(id));
  if (addedIds.length === 0) {
    return { changed: false, addedIds: [], mergedIds: [...mergedSet] };
  }

  const payload = await bitrixCall(base, "calendar.event.update", {
    id: ev?.ID,
    type: "user",
    ownerId,
    name: String(ev?.NAME || "Встреча"),
    from: String(ev?.DATE_FROM || "").trim() || undefined,
    to: String(ev?.DATE_TO || "").trim() || undefined,
    "attendees[]": [...mergedSet],
    "attendeesCodes[]": [...mergedSet].map((id) => `U${id}`),
  });
  if (!payload?.result) throw new Error("Bitrix error: update returned empty result");
  return { changed: true, addedIds, mergedIds: [...mergedSet] };
}

async function cancelByText(cancelPart, base, ownerId, dryRun) {
  const target = await findTargetEventByText(cancelPart, base, ownerId);
  if (dryRun) {
    return `DRY RUN\nБудет отменено: ${eventSlotText(target)} — ${target?.NAME || "(без названия)"} (ID ${target?.ID})`;
  }

  await deleteBitrixEvent(base, ownerId, target?.ID);
  return `✅ Встреча отменена\n${eventSlotText(target)} — ${target?.NAME || "(без названия)"}\nID: ${target?.ID}`;
}

function validateEnv(sendTelegram) {
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
  if (sendTelegram) {
    for (const k of ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]) {
      if (!String(process.env[k] || "").trim()) throw new Error(`Missing env: ${k}`);
    }
  }
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
  for (const chunk of splitTelegramText(text)) {
    const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text: chunk }),
    });
    if (!res.ok) throw new Error(`Telegram error ${res.status}: ${await res.text()}`);
  }
}

async function createBitrixEventFromText(rawText, options = {}) {
  const send = Boolean(options.sendTelegram);
  const dryRun = Boolean(options.dryRun);
  const ignoreOverlapCheck = Boolean(options.ignoreOverlapCheck);

  validateEnv(send);

  const text = String(rawText || "").trim();
  if (!text) throw new Error("Пустой запрос. Пример: поставь встречу на 20.02 в 11:00 длительностью 1 час название Планерка");

  const ymd = parseDateFromText(text, TZ);
  const { hh, mm } = parseTimeFromText(text);
  const durationMin = parseDurationMinutes(text);
  const title = parseTitle(text);
  const inviteeQueries = extractInviteeQueries(text);

  const end = addMinutes(hh, mm, durationMin);
  const endYmd = shiftYmd(ymd, end.dayShift);
  const from = formatBitrixDateTime(ymd, hh, mm);
  const to = formatBitrixDateTime(endYmd, end.hh, end.mm);

  const base = bitrixBase(process.env.BITRIX_WEBHOOK_BASE);
  const ownerId = await resolveOwnerId(base);

  const activeUsers = inviteeQueries.length ? await fetchBitrixActiveUsers(base) : [];
  const { attendeeIds, attendeeNames } = resolveInvitees(inviteeQueries, activeUsers);

  const startMin = hh * 60 + mm;
  const endMin = end.hh * 60 + end.mm + (end.hh < hh ? 24 * 60 : 0);
  const dayEvents = await fetchBitrixDayEvents(base, ownerId, ymd);
  const overlaps = findOverlaps(dayEvents, startMin, endMin, normalizeRus(title));
  if (overlaps.length > 0 && !ignoreOverlapCheck && !hasOverlapOverride(text)) {
    const list = overlaps
      .slice(0, 5)
      .map((e) => `${eventSlotText(e)} — ${e.NAME || "(без названия)"}`)
      .join("\n");
    throw new Error(
      `Есть наслоение с другими встречами:\n${list}\n\nЕсли все равно нужно создать, напиши: \"все правильно, создавай\" в том же сообщении.`
    );
  }

  if (dryRun) {
    const who = attendeeNames.length ? `\nУчастники: ${attendeeNames.join(", ")}` : "";
    const preview = `DRY RUN\nВстреча: ${title}\nКогда: ${from} - ${to}\nДлительность: ${durationMin} мин${who}`;
    if (send) await sendTelegram(preview);
    return preview;
  }

  const buildCreateUrl = (ids = []) => {
    return {
      type: "user",
      ownerId,
      name: title,
      from,
      to,
      "attendees[]": ids,
      "attendeesCodes[]": ids.map((id) => `U${id}`),
    };
  };

  const requestCreate = async (ids = []) => {
    const payload = await bitrixCall(base, "calendar.event.add", buildCreateUrl(ids));
    return payload?.result?.id || payload?.result;
  };

  let eventId;
  let fallbackNotice = "";
  try {
    eventId = await requestCreate(attendeeIds);
  } catch (err) {
    const msg = String(err?.message || err || "");
    const canFallback =
      attendeeIds.length > 0 &&
      parseBool(process.env.BITRIX_ALLOW_CREATE_WITHOUT_ATTENDEES ?? "0") &&
      /(insufficient_scope|access denied|access_denied|forbidden|permission|scope|rights|not allowed|denied|403)/i.test(msg);
    if (!canFallback) throw err;
    eventId = await requestCreate([]);
    fallbackNotice = `\n⚠ Bitrix API не смог добавить приглашения. Встреча создана без участников: ${attendeeNames.join(", ")}.`;
  }

  const who = attendeeNames.length && !fallbackNotice ? `\nУчастники: ${attendeeNames.join(", ")}` : "";
  const out = `✅ Встреча создана\n${title}\n${from} - ${to}${who}\nID: ${eventId ?? "n/a"}${fallbackNotice}`;
  if (send) await sendTelegram(out);
  return out;
}

async function addParticipantsByText(rawText, base, ownerId, dryRun) {
  const parsed = parseAddParticipantsIntent(rawText);
  if (!parsed) throw new Error("Не смог распознать команду добавления участника.");

  const activeUsers = await fetchBitrixActiveUsers(base);
  const { attendeeIds, attendeeNames } = resolveInvitees(parsed.inviteeQueries, activeUsers);
  const target = await findTargetEventByText(parsed.eventQuery, base, ownerId);

  if (dryRun) {
    return `DRY RUN\nБудет добавлено в: ${eventSlotText(target)} — ${target?.NAME || "(без названия)"} (ID ${target?.ID})\nУчастники: ${attendeeNames.join(", ")}`;
  }

  const result = await updateBitrixEventParticipants(base, ownerId, target, attendeeIds);
  if (!result.changed) {
    return `ℹ️ Участники уже добавлены\n${eventSlotText(target)} — ${target?.NAME || "(без названия)"} (ID ${target?.ID})`;
  }

  return `✅ Участники добавлены\n${eventSlotText(target)} — ${target?.NAME || "(без названия)"}\nДобавлены: ${attendeeNames.join(", ")}\nID: ${target?.ID}`;
}

async function handleRequest(rawText, options = {}) {
  const send = Boolean(options.sendTelegram);
  const dryRun = Boolean(options.dryRun);
  const text = String(rawText || "").trim();
  const base = bitrixBase(process.env.BITRIX_WEBHOOK_BASE);
  const ownerId = await resolveOwnerId(base);

  if (/^\s*добав(?:ь|ить)\b/iu.test(text)) {
    const out = await addParticipantsByText(text, base, ownerId, dryRun);
    if (send) await sendTelegram(out);
    return out;
  }

  if (/^\s*отмени(?:\s|$)/iu.test(text)) {
    const { cancelPart, createPart } = splitCancelAndCreate(text);
    if (!createPart) {
      const cancelResult = await cancelByText(cancelPart, base, ownerId, dryRun);
      if (send) await sendTelegram(cancelResult);
      return cancelResult;
    }

    // Preflight before deletion: ensure the new meeting is valid.
    await createBitrixEventFromText(createPart, {
      sendTelegram: false,
      dryRun: true,
      ignoreOverlapCheck: false,
    });

    const cancelResult = await cancelByText(cancelPart, base, ownerId, dryRun);
    const createResult = await createBitrixEventFromText(createPart, {
      sendTelegram: false,
      dryRun,
      ignoreOverlapCheck: false,
    });
    const out = `${cancelResult}\n\n${createResult}`;
    if (send) await sendTelegram(out);
    return out;
  }

  return createBitrixEventFromText(text, options);
}

async function main() {
  const args = process.argv.slice(2);
  const sendTelegramFlag = args.includes("--send-telegram");
  const dryRun = args.includes("--dry-run");
  const useStdin = args.includes("--stdin");

  let raw = args.filter((a) => a !== "--send-telegram" && a !== "--dry-run" && a !== "--stdin").join(" ").trim();
  if (useStdin) {
    raw = await new Promise((resolve) => {
      let buf = "";
      process.stdin.setEncoding("utf8");
      process.stdin.on("data", (d) => {
        buf += d;
      });
      process.stdin.on("end", () => resolve(buf.trim()));
      process.stdin.resume();
    });
  }

  const out = await handleRequest(raw, { sendTelegram: sendTelegramFlag, dryRun });
  if (sendTelegramFlag) {
    console.log("OK");
    return;
  }
  console.log(out);
}

main().catch((e) => {
  console.error(e.message || String(e));
  process.exit(1);
});
