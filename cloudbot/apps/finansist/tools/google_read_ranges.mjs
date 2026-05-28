#!/usr/bin/env node
import { createSign } from "node:crypto";
import { readFile } from "node:fs/promises";

const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly";

function parseArgs(argv) {
  const args = { sheetUrl: "", ranges: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const token = String(argv[i] || "");
    const next = String(argv[i + 1] || "");
    if (token === "--sheet-url") {
      args.sheetUrl = next;
      i += 1;
      continue;
    }
    if (token === "--range") {
      args.ranges.push(next);
      i += 1;
    }
  }
  return args;
}

function base64url(input) {
  return Buffer.from(input)
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function extractSheetId(url) {
  const match = String(url || "").match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
  return match ? match[1] : "";
}

async function loadServiceAccount() {
  const filePath = String(process.env.GOOGLE_SERVICE_ACCOUNT_JSON || "").trim();
  if (!filePath) {
    throw new Error("Не задан GOOGLE_SERVICE_ACCOUNT_JSON");
  }
  return JSON.parse(await readFile(filePath, "utf8"));
}

function buildJwt(key, scope) {
  const now = Math.floor(Date.now() / 1000);
  const header = base64url(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const claim = base64url(JSON.stringify({
    iss: key.client_email,
    scope,
    aud: TOKEN_URL,
    exp: now + 3600,
    iat: now,
  }));
  const signer = createSign("RSA-SHA256");
  signer.update(`${header}.${claim}`);
  signer.end();
  const signature = signer.sign(key.private_key, "base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
  return `${header}.${claim}.${signature}`;
}

async function token(key) {
  const body = new URLSearchParams({
    grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
    assertion: buildJwt(key, SHEETS_SCOPE),
  });
  const response = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
  });
  const payload = await response.json();
  if (!response.ok || !payload.access_token) {
    throw new Error(`OAuth error: ${response.status} ${JSON.stringify(payload)}`);
  }
  return payload.access_token;
}

async function getRange(spreadsheetId, accessToken, range) {
  const response = await fetch(
    `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}?majorDimension=ROWS`,
    { headers: { authorization: `Bearer ${accessToken}` } },
  );
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(`Read range error ${range}: ${response.status} ${JSON.stringify(payload)}`);
  }
  return payload.values || [];
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const spreadsheetId = extractSheetId(args.sheetUrl);
  if (!spreadsheetId) {
    throw new Error("Не удалось извлечь spreadsheet id");
  }
  if (!args.ranges.length) {
    throw new Error("Нужно передать хотя бы один --range");
  }
  const key = await loadServiceAccount();
  const accessToken = await token(key);
  const output = {};
  for (const range of args.ranges) {
    output[range] = await getRange(spreadsheetId, accessToken, range);
  }
  console.log(JSON.stringify(output, null, 2));
}

main().catch((error) => {
  console.error(String(error?.message || error || "unknown error"));
  process.exit(1);
});
