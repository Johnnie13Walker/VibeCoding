#!/usr/bin/env node
import { createSign } from "node:crypto";
import { readFile } from "node:fs/promises";

const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly";

function parseArgs(argv) {
  const args = { sheetUrl: "" };
  for (let i = 0; i < argv.length; i += 1) {
    const token = String(argv[i] || "");
    const next = String(argv[i + 1] || "");
    if (token === "--sheet-url") {
      args.sheetUrl = next;
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

function normalizeText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/ё/g, "е")
    .replace(/[().,]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function quoteSheetTitle(title) {
  return `'${String(title).replace(/'/g, "''")}'`;
}

function detectMonthlySheetSpec(title, rows) {
  const normalizedTitle = normalizeText(title);
  const match = normalizedTitle.match(/(январь|февраль|март|апрель|май|июнь|июль|август|сентябрь|октябрь|ноябрь|декабрь)\s+(\d{2})/);
  if (!match) return null;
  const year = Number(`20${match[2]}`);
  if (![2024, 2025, 2026].includes(year)) {
    return null;
  }
  for (let rowIndex = 0; rowIndex < Math.min(rows.length, 5); rowIndex += 1) {
    const row = rows[rowIndex] || [];
    const normalized = row.map((cell) => normalizeText(cell));
    const employeeIndex = normalized.findIndex((cell) => cell === "сотрудник" || cell === "фио" || cell.includes("фио") || cell.includes("сотрудник"));
    if (employeeIndex >= 0) {
      return {
        title,
        year,
        headerRowIndex: rowIndex,
        employeeColumn: employeeIndex,
      };
    }
  }
  return null;
}

function splitTokens(name) {
  return normalizeText(name)
    .split(" ")
    .filter(Boolean)
    .filter((token) => token !== "ип" && token !== "смз" && token !== "физлицо");
}

function buildCanonicalName(name) {
  const tokens = splitTokens(name);
  if (!tokens.length) {
    return { canonical: "", surname: "", firstName: "", patronymic: "", short: "" };
  }
  const surname = tokens[0] || "";
  const firstName = tokens[1] || "";
  const patronymic = tokens[2] || "";
  const canonical = [surname, firstName].filter(Boolean).join(" ").trim();
  const short = [surname, firstName ? `${firstName[0]}.` : ""].filter(Boolean).join(" ").trim();
  return { canonical, surname, firstName, patronymic, short };
}

function confidenceLabel(score) {
  if (score >= 0.95) return "Высокая";
  if (score >= 0.75) return "Средняя";
  return "Низкая";
}

function commentForPair(left, right, score) {
  if (left.canonical === right.canonical && left.patronymic !== right.patronymic) {
    return "Совпадение по фамилии и имени, различие только в отчестве";
  }
  if (left.canonical === right.canonical) {
    return "Совпадение по фамилии и имени";
  }
  if (left.surname === right.surname && left.firstName && right.firstName && left.firstName[0] === right.firstName[0]) {
    return score >= 0.75
      ? "Совпадает фамилия и первая буква имени"
      : "Совпадает фамилия и инициал имени, нужна ручная проверка";
  }
  return "Похожее написание, нужна ручная проверка";
}

function pairScore(left, right) {
  if (!left.surname || !right.surname) return 0;
  if (left.surname !== right.surname) return 0;
  if (left.firstName && right.firstName && left.firstName === right.firstName) {
    return left.patronymic && right.patronymic && left.patronymic !== right.patronymic ? 0.92 : 0.99;
  }
  if (left.firstName && right.firstName && left.firstName[0] === right.firstName[0]) {
    return 0.78;
  }
  if (left.firstName && right.firstName && (left.firstName.startsWith(right.firstName) || right.firstName.startsWith(left.firstName))) {
    return 0.82;
  }
  return 0;
}

async function valuesGet(spreadsheetId, accessToken, range) {
  const payload = await fetchJson(
    `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}?majorDimension=ROWS`,
    accessToken,
  );
  return payload.values || [];
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const spreadsheetId = extractSheetId(args.sheetUrl);
  if (!spreadsheetId) {
    throw new Error("Не удалось извлечь spreadsheet id");
  }

  const serviceAccount = await loadServiceAccount();
  const accessToken = await fetchAccessToken(serviceAccount);
  const metadata = await fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}`, accessToken);

  const rawEmployees = [];
  for (const sheet of metadata.sheets || []) {
    const title = String(sheet.properties?.title || "");
    const preview = await valuesGet(spreadsheetId, accessToken, `${quoteSheetTitle(title)}!A1:Z8`);
    const spec = detectMonthlySheetSpec(title, preview);
    if (!spec) continue;
    const full = await valuesGet(spreadsheetId, accessToken, `${quoteSheetTitle(title)}!A:Z`);
    for (const row of full.slice(spec.headerRowIndex + 1)) {
      const rawName = String(row[spec.employeeColumn] || "").trim();
      if (!rawName) continue;
      const normalized = buildCanonicalName(rawName);
      if (!normalized.canonical) continue;
      rawEmployees.push({
        year: spec.year,
        sheet: title,
        rawName,
        ...normalized,
      });
    }
  }

  const uniqueRawMap = new Map();
  for (const item of rawEmployees) {
    const key = item.rawName;
    if (!uniqueRawMap.has(key)) {
      uniqueRawMap.set(key, {
        rawName: item.rawName,
        canonical: item.canonical,
        surname: item.surname,
        firstName: item.firstName,
        patronymic: item.patronymic,
        years: new Set(),
        sheets: new Set(),
      });
    }
    const target = uniqueRawMap.get(key);
    target.years.add(item.year);
    target.sheets.add(item.sheet);
  }

  const dictionary = [...uniqueRawMap.values()]
    .map((item) => ({
      rawName: item.rawName,
      canonical: item.canonical,
      comment: item.rawName === item.canonical ? "Базовое имя" : (item.patronymic ? "Нормализация: убрано отчество" : "Нормализация: приведено к Фамилия Имя"),
      confidence: "Высокая",
      years: [...item.years].sort(),
    }))
    .sort((a, b) => a.canonical.localeCompare(b.canonical, "ru") || a.rawName.localeCompare(b.rawName, "ru"));

  const uniqueItems = [...uniqueRawMap.values()];
  const doubtful = [];
  for (let i = 0; i < uniqueItems.length; i += 1) {
    for (let j = i + 1; j < uniqueItems.length; j += 1) {
      const left = uniqueItems[i];
      const right = uniqueItems[j];
      if (left.rawName === right.rawName) continue;
      const score = pairScore(left, right);
      if (score < 0.75 || score >= 0.95) continue;
      doubtful.push({
        left: left.rawName,
        right: right.rawName,
        reason: commentForPair(left, right, score),
        confidence: confidenceLabel(score),
        normalizedLeft: left.canonical,
        normalizedRight: right.canonical,
      });
    }
  }

  doubtful.sort((a, b) => a.left.localeCompare(b.left, "ru") || a.right.localeCompare(b.right, "ru"));

  const summary = {
    totalRawVariants: dictionary.length,
    uniqueNormalizedNames: new Set(dictionary.map((item) => item.canonical)).size,
    doubtfulCount: doubtful.length,
  };

  console.log(JSON.stringify({ summary, dictionary, doubtful }, null, 2));
}

main().catch((error) => {
  console.error(String(error?.message || error || "unknown error"));
  process.exit(1);
});
