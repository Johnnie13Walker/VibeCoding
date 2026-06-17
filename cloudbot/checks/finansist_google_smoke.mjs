#!/usr/bin/env node
import { createSign } from "node:crypto";
import { readFile } from "node:fs/promises";

const SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly";
const DOCS_SCOPE = "https://www.googleapis.com/auth/documents.readonly";
const TOKEN_URL = "https://oauth2.googleapis.com/token";

function parseArgs(argv) {
  const args = {
    sheetUrl: "",
    docUrl: "",
  };
  for (let index = 0; index < argv.length; index += 1) {
    const token = String(argv[index] || "");
    const next = String(argv[index + 1] || "");
    if (token === "--sheet-url") {
      args.sheetUrl = next;
      index += 1;
      continue;
    }
    if (token === "--doc-url") {
      args.docUrl = next;
      index += 1;
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

function extractGoogleId(url, kind) {
  const source = String(url || "").trim();
  const pattern = kind === "sheet" ? /\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/ : /\/document\/d\/([a-zA-Z0-9-_]+)/;
  const match = source.match(pattern);
  return match ? match[1] : "";
}

async function loadServiceAccount() {
  const filePath = String(process.env.GOOGLE_SERVICE_ACCOUNT_JSON || "").trim();
  if (!filePath) {
    throw new Error("Не задан GOOGLE_SERVICE_ACCOUNT_JSON");
  }
  const payload = JSON.parse(await readFile(filePath, "utf8"));
  if (!payload.client_email || !payload.private_key) {
    throw new Error("Файл сервисного аккаунта неполный: нет client_email/private_key");
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

async function fetchAccessToken(serviceAccount, scope) {
  const assertion = buildJwt(serviceAccount, scope);
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
  if (!response.ok) {
    throw new Error(`Google OAuth token error: ${response.status} ${JSON.stringify(payload)}`);
  }
  if (!payload.access_token) {
    throw new Error("Google OAuth token не вернул access_token");
  }
  return String(payload.access_token);
}

async function fetchSheetSummary(accessToken, sheetId) {
  const response = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${sheetId}?includeGridData=false`, {
    headers: { authorization: `Bearer ${accessToken}` },
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(`Sheets API error: ${response.status} ${JSON.stringify(payload)}`);
  }
  const title = String(payload.properties?.title || "").trim();
  const sheetCount = Array.isArray(payload.sheets) ? payload.sheets.length : 0;
  return { title, sheetCount };
}

async function fetchDocSummary(accessToken, docId) {
  const response = await fetch(`https://docs.googleapis.com/v1/documents/${docId}`, {
    headers: { authorization: `Bearer ${accessToken}` },
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(`Docs API error: ${response.status} ${JSON.stringify(payload)}`);
  }
  return {
    title: String(payload.title || "").trim(),
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const serviceAccount = await loadServiceAccount();
  const outputs = [];

  if (args.sheetUrl) {
    const sheetId = extractGoogleId(args.sheetUrl, "sheet");
    if (!sheetId) {
      throw new Error("Не удалось извлечь sheet id из --sheet-url");
    }
    const sheetToken = await fetchAccessToken(serviceAccount, SHEETS_SCOPE);
    const summary = await fetchSheetSummary(sheetToken, sheetId);
    outputs.push(`Google Sheets OK: ${summary.title} (tabs=${summary.sheetCount})`);
  }

  if (args.docUrl) {
    const docId = extractGoogleId(args.docUrl, "doc");
    if (!docId) {
      throw new Error("Не удалось извлечь doc id из --doc-url");
    }
    const docToken = await fetchAccessToken(serviceAccount, DOCS_SCOPE);
    const summary = await fetchDocSummary(docToken, docId);
    outputs.push(`Google Docs OK: ${summary.title || "(без заголовка)"}`);
  }

  if (outputs.length === 0) {
    throw new Error("Нужно передать хотя бы --sheet-url или --doc-url");
  }

  for (const line of outputs) {
    console.log(line);
  }
}

main().catch((error) => {
  console.error(String(error?.message || error || "unknown error"));
  process.exit(1);
});
