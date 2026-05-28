import { createSign } from "node:crypto";
import { readFile } from "node:fs/promises";

const SHEET_URL = "https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit#gid=0";
const SA_PATH = process.env.MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON || process.env.GOOGLE_SERVICE_ACCOUNT_JSON || "/Users/pro2kuror/Downloads/finance-director-sheets-903611b799c3.json";
const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SCOPE = "https://www.googleapis.com/auth/spreadsheets";

const TO_HIDE = new Set([
  "Acoola Team",
  "Belberry",
  "Динамика по месяцам",
  "Источники по месяцам",
  "События по месяцам",
  "Без бренда",
  "RAW · ceo_charts",
  "RAW · cohort_source",
  "RAW · event_brand",
  "RAW · event_sales",
  "RAW · source_trends_2026",
  "RAW · spam_sources_2026",
]);

function base64url(input) {
  return Buffer.from(input).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}
function extractSheetId(url) {
  const match = String(url || "").match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
  return match ? match[1] : "";
}
async function loadJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}
function buildJwt({ client_email, private_key }) {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "RS256", typ: "JWT" };
  const claim = { iss: client_email, scope: SCOPE, aud: TOKEN_URL, exp: now + 3600, iat: now };
  const encodedHeader = base64url(JSON.stringify(header));
  const encodedClaim = base64url(JSON.stringify(claim));
  const signer = createSign("RSA-SHA256");
  signer.update(`${encodedHeader}.${encodedClaim}`);
  signer.end();
  const signature = signer.sign(private_key, "base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  return `${encodedHeader}.${encodedClaim}.${signature}`;
}
async function fetchAccessToken(sa) {
  const body = new URLSearchParams({
    grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
    assertion: buildJwt(sa),
  });
  const res = await fetch(TOKEN_URL, { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" }, body });
  const payload = await res.json();
  if (!res.ok || !payload.access_token) throw new Error(`OAuth error: ${res.status} ${JSON.stringify(payload)}`);
  return payload.access_token;
}
async function fetchJson(url, token, init = {}) {
  const res = await fetch(url, {
    ...init,
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json", ...(init.headers || {}) },
  });
  const payload = await res.json();
  if (!res.ok) throw new Error(`API error: ${res.status} ${JSON.stringify(payload)}`);
  return payload;
}
async function batchUpdate(spreadsheetId, token, requests) {
  return fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}:batchUpdate`, token, {
    method: "POST",
    body: JSON.stringify({ requests }),
  });
}

const spreadsheetId = extractSheetId(SHEET_URL);
const sa = await loadJson(SA_PATH);
const token = await fetchAccessToken(sa);
const metadata = await fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}`, token);
const requests = [];
const hidden = [];
const visible = [];

for (const sheet of metadata.sheets || []) {
  const title = sheet.properties?.title || "";
  const hiddenNow = Boolean(sheet.properties?.hidden);
  if (TO_HIDE.has(title)) {
    if (!hiddenNow) {
      requests.push({
        updateSheetProperties: {
          properties: { sheetId: sheet.properties.sheetId, hidden: true },
          fields: "hidden",
        },
      });
    }
    hidden.push(title);
  } else {
    visible.push(title);
  }
}

if (requests.length) await batchUpdate(spreadsheetId, token, requests);

console.log(JSON.stringify({ hidden, visible }, null, 2));
