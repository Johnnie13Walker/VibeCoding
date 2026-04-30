#!/usr/bin/env node
import { createSign } from "node:crypto";
import { readFile } from "node:fs/promises";

const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly";

function parseArgs(argv) {
  const args = {
    sheetUrl: "",
    rows: 8,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const token = String(argv[i] || "");
    const next = String(argv[i + 1] || "");
    if (token === "--sheet-url") {
      args.sheetUrl = next;
      i += 1;
      continue;
    }
    if (token === "--rows") {
      args.rows = Number(next || "8");
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
  const payload = JSON.parse(await readFile(filePath, "utf8"));
  if (!payload.client_email || !payload.private_key) {
    throw new Error("Файл сервисного аккаунта неполный");
  }
  return payload;
}

function buildJwt({ client_email: clientEmail, private_key: privateKey }, scope) {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "RS256", typ: "JWT" };
  const claim = {
    iss: clientEmail,
    scope,
    aud: TOKEN_URL,
    exp: now + 3600,
    iat: now,
  };
  const encodedHeader = base64url(JSON.stringify(header));
  const encodedClaim = base64url(JSON.stringify(claim));
  const signer = createSign("RSA-SHA256");
  signer.update(`${encodedHeader}.${encodedClaim}`);
  signer.end();
  const signature = signer.sign(privateKey, "base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
  return `${encodedHeader}.${encodedClaim}.${signature}`;
}

async function fetchAccessToken(serviceAccount) {
  const assertion = buildJwt(serviceAccount, SHEETS_SCOPE);
  const body = new URLSearchParams({
    grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
    assertion,
  });
  const response = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
  });
  const payload = await response.json();
  if (!response.ok || !payload.access_token) {
    throw new Error(`Google OAuth token error: ${response.status} ${JSON.stringify(payload)}`);
  }
  return String(payload.access_token);
}

async function fetchJson(url, accessToken) {
  const response = await fetch(url, {
    headers: { authorization: `Bearer ${accessToken}` },
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(`Sheets API error: ${response.status} ${JSON.stringify(payload)}`);
  }
  return payload;
}

function quoteSheetTitle(title) {
  return `'${String(title).replace(/'/g, "''")}'`;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const sheetId = extractSheetId(args.sheetUrl);
  if (!sheetId) {
    throw new Error("Не удалось извлечь spreadsheet id из --sheet-url");
  }

  const serviceAccount = await loadServiceAccount();
  const accessToken = await fetchAccessToken(serviceAccount);
  const metadata = await fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${sheetId}`, accessToken);
  const sheets = Array.isArray(metadata.sheets) ? metadata.sheets : [];

  const output = {
    spreadsheetTitle: String(metadata.properties?.title || ""),
    sheetCount: sheets.length,
    sheets: [],
  };

  for (const sheet of sheets) {
    const title = String(sheet.properties?.title || "");
    const gridRows = Number(sheet.properties?.gridProperties?.rowCount || 0);
    const gridCols = Number(sheet.properties?.gridProperties?.columnCount || 0);
    const range = `${quoteSheetTitle(title)}!A1:Z${Math.max(1, args.rows)}`;
    const valuesPayload = await fetchJson(
      `https://sheets.googleapis.com/v4/spreadsheets/${sheetId}/values/${encodeURIComponent(range)}?majorDimension=ROWS`,
      accessToken,
    );
    output.sheets.push({
      title,
      sheetId: sheet.properties?.sheetId,
      rowCount: gridRows,
      columnCount: gridCols,
      preview: valuesPayload.values || [],
    });
  }

  console.log(JSON.stringify(output, null, 2));
}

main().catch((error) => {
  console.error(String(error?.message || error || "unknown error"));
  process.exit(1);
});
