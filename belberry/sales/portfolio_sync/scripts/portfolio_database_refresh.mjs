#!/usr/bin/env node
import { createSign } from "node:crypto";
import { readFile } from "node:fs/promises";

const DEFAULT_SOURCE_URL = "https://docs.google.com/spreadsheets/d/17SBisFgKrf3hRP_zjVPC2e4wMzlq8j8HDC2bvkyS74Y/edit?gid=1482533080#gid=1482533080";
const DEFAULT_TARGET_URL = "https://docs.google.com/spreadsheets/d/1TgWlFHOvSDtW0e60fCLNvWDW7ADwOimHpypbQG7GI9E/edit";
const DEFAULT_SA_PATH = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json";

const SOURCE_SHEET_TITLE = "Все года";
const DATA_SHEET_TITLE = "Данные";
const README_SHEET_TITLE = "README";
const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SCOPE = "https://www.googleapis.com/auth/spreadsheets";

const REQUIRED_COLUMNS = [
  "Проект",
  "Услуга",
  "Бренд",
  "Год",
  "Месяц",
  "Дата оплаты",
  "Отдел",
  "New/Old",
];

const EXCLUDED_SERVICES = new Set(["agency", "service"]);
const EXCLUDED_SERVICE_LABELS = ["Agency", "Service"];

const COLORS = {
  header: { red: 0.137, green: 0.243, blue: 0.365 },
  headerText: { red: 1, green: 1, blue: 1 },
  readme: { red: 0.929, green: 0.953, blue: 0.976 },
};

function parseArgs(argv) {
  const args = {
    dryRun: false,
    sourceUrl: process.env.PORTFOLIO_SOURCE_SHEET_URL || DEFAULT_SOURCE_URL,
    targetUrl: process.env.PORTFOLIO_TARGET_SHEET_URL || DEFAULT_TARGET_URL,
    serviceAccountPath: process.env.MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON
      || process.env.GOOGLE_SERVICE_ACCOUNT_JSON
      || DEFAULT_SA_PATH,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const token = String(argv[index] || "");
    const next = String(argv[index + 1] || "");
    if (token === "--dry-run") {
      args.dryRun = true;
      continue;
    }
    if (token === "--source-url") {
      args.sourceUrl = next;
      index += 1;
      continue;
    }
    if (token === "--target-url") {
      args.targetUrl = next;
      index += 1;
      continue;
    }
    if (token === "--service-account") {
      args.serviceAccountPath = next;
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

function extractSheetId(url) {
  const match = String(url || "").match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
  return match ? match[1] : "";
}

function quoteSheetTitle(title) {
  return `'${String(title).replace(/'/g, "''")}'`;
}

function colLetter(index1Based) {
  let n = index1Based;
  let result = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    result = String.fromCharCode(65 + rem) + result;
    n = Math.floor((n - 1) / 26);
  }
  return result;
}

function nowMsk() {
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: "Europe/Moscow",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date());
}

function safeText(value) {
  const text = String(value ?? "").trim();
  return /^[=+\-@]/.test(text) ? `'${text}` : text;
}

function normalizeHeader(value) {
  return String(value ?? "").replace(/\s+/g, " ").trim().toLowerCase();
}

function normalizeService(value) {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[сС]/g, "c");
}

function buildJwt({ client_email: clientEmail, private_key: privateKey }) {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "RS256", typ: "JWT" };
  const claim = {
    iss: clientEmail,
    scope: SCOPE,
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
  const body = new URLSearchParams({
    grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
    assertion: buildJwt(serviceAccount),
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
  return String(payload.access_token);
}

async function fetchJson(url, token, init = {}) {
  const response = await fetch(url, {
    ...init,
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      ...(init.headers || {}),
    },
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(`Sheets API error: ${response.status} ${JSON.stringify(payload)}`);
  }
  return payload;
}

async function batchUpdate(spreadsheetId, token, requests) {
  if (!requests.length) return {};
  return fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}:batchUpdate`, token, {
    method: "POST",
    body: JSON.stringify({ requests }),
  });
}

async function valuesGet(spreadsheetId, token, range) {
  const payload = await fetchJson(
    `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}?majorDimension=ROWS`,
    token,
  );
  return payload.values || [];
}

async function valuesBatchGet(spreadsheetId, token, ranges) {
  const params = new URLSearchParams({ majorDimension: "COLUMNS" });
  for (const range of ranges) {
    params.append("ranges", range);
  }
  const payload = await fetchJson(
    `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values:batchGet?${params.toString()}`,
    token,
  );
  return payload.valueRanges || [];
}

async function valuesUpdate(spreadsheetId, token, sheetTitle, grid) {
  const rows = Math.max(grid.length, 1);
  const cols = Math.max(...grid.map((row) => row.length), 1);
  const normalized = grid.map((row) => Array.from({ length: cols }, (_, index) => row[index] ?? ""));
  const range = `${quoteSheetTitle(sheetTitle)}!A1:${colLetter(cols)}${rows}`;
  const response = await fetch(
    `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}?valueInputOption=USER_ENTERED`,
    {
      method: "PUT",
      headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({ majorDimension: "ROWS", values: normalized }),
    },
  );
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(`Values update error: ${response.status} ${JSON.stringify(payload)}`);
  }
  return payload;
}

async function valuesClear(spreadsheetId, token, sheetTitle, rows, cols) {
  const range = `${quoteSheetTitle(sheetTitle)}!A1:${colLetter(cols)}${rows}`;
  const response = await fetch(
    `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}:clear`,
    {
      method: "POST",
      headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: "{}",
    },
  );
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(`Values clear error: ${response.status} ${JSON.stringify(payload)}`);
  }
  return payload;
}

async function ensureTargetSheets(spreadsheetId, token, desiredSheets) {
  const metadata = await fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}?includeGridData=false`, token);
  const existing = new Map((metadata.sheets || []).map((sheet) => [sheet.properties.title, sheet.properties]));
  const requests = [];

  for (const sheet of desiredSheets) {
    if (!existing.has(sheet.title)) {
      requests.push({
        addSheet: {
          properties: {
            title: sheet.title,
            gridProperties: {
              rowCount: Math.max(sheet.rows + 20, 100),
              columnCount: Math.max(sheet.cols, 8),
            },
          },
        },
      });
    }
  }

  if (requests.length) {
    await batchUpdate(spreadsheetId, token, requests);
  }

  const updated = await fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}?includeGridData=false`, token);
  return new Map((updated.sheets || []).map((sheet) => [sheet.properties.title, sheet.properties.sheetId]));
}

function dataStyleRequests(sheetId, rows, cols) {
  return [
    { clearBasicFilter: { sheetId } },
    {
      updateSheetProperties: {
        properties: {
          sheetId,
          gridProperties: {
            frozenRowCount: 1,
            rowCount: Math.max(rows + 20, 100),
            columnCount: cols,
          },
        },
        fields: "gridProperties(frozenRowCount,rowCount,columnCount)",
      },
    },
    {
      repeatCell: {
        range: { sheetId, startRowIndex: 0, endRowIndex: 1, startColumnIndex: 0, endColumnIndex: cols },
        cell: {
          userEnteredFormat: {
            backgroundColor: COLORS.header,
            textFormat: { bold: true, foregroundColor: COLORS.headerText },
            horizontalAlignment: "CENTER",
            verticalAlignment: "MIDDLE",
            wrapStrategy: "WRAP",
          },
        },
        fields: "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)",
      },
    },
    {
      repeatCell: {
        range: { sheetId, startRowIndex: 1, endRowIndex: Math.max(rows, 2), startColumnIndex: 0, endColumnIndex: cols },
        cell: { userEnteredFormat: { verticalAlignment: "TOP", wrapStrategy: "WRAP" } },
        fields: "userEnteredFormat(verticalAlignment,wrapStrategy)",
      },
    },
    {
      setBasicFilter: {
        filter: {
          range: { sheetId, startRowIndex: 0, endRowIndex: Math.max(rows, 2), startColumnIndex: 0, endColumnIndex: cols },
        },
      },
    },
    ...[260, 150, 180, 90, 90, 120, 150, 100].map((pixelSize, index) => ({
      updateDimensionProperties: {
        range: { sheetId, dimension: "COLUMNS", startIndex: index, endIndex: index + 1 },
        properties: { pixelSize },
        fields: "pixelSize",
      },
    })),
  ];
}

function readmeStyleRequests(sheetId, rows) {
  return [
    {
      updateSheetProperties: {
        properties: { sheetId, gridProperties: { frozenRowCount: 1, rowCount: Math.max(rows + 20, 100), columnCount: 2 } },
        fields: "gridProperties(frozenRowCount,rowCount,columnCount)",
      },
    },
    {
      repeatCell: {
        range: { sheetId, startRowIndex: 0, endRowIndex: Math.max(rows, 1), startColumnIndex: 0, endColumnIndex: 2 },
        cell: {
          userEnteredFormat: {
            backgroundColor: COLORS.readme,
            wrapStrategy: "WRAP",
            verticalAlignment: "TOP",
          },
        },
        fields: "userEnteredFormat(backgroundColor,wrapStrategy,verticalAlignment)",
      },
    },
    {
      repeatCell: {
        range: { sheetId, startRowIndex: 0, endRowIndex: Math.max(rows, 1), startColumnIndex: 0, endColumnIndex: 1 },
        cell: { userEnteredFormat: { textFormat: { bold: true } } },
        fields: "userEnteredFormat.textFormat.bold",
      },
    },
    {
      updateDimensionProperties: {
        range: { sheetId, dimension: "COLUMNS", startIndex: 0, endIndex: 1 },
        properties: { pixelSize: 260 },
        fields: "pixelSize",
      },
    },
    {
      updateDimensionProperties: {
        range: { sheetId, dimension: "COLUMNS", startIndex: 1, endIndex: 2 },
        properties: { pixelSize: 520 },
        fields: "pixelSize",
      },
    },
  ];
}

async function readPortfolioRows(sourceSpreadsheetId, token) {
  const headerRows = await valuesGet(sourceSpreadsheetId, token, `${quoteSheetTitle(SOURCE_SHEET_TITLE)}!A1:Z1`);
  const headers = headerRows[0] || [];
  const headerMap = new Map(headers.map((header, index) => [normalizeHeader(header), index + 1]));
  const missing = REQUIRED_COLUMNS.filter((name) => !headerMap.has(normalizeHeader(name)));
  if (missing.length) {
    throw new Error(`В источнике не найдены обязательные колонки: ${missing.join(", ")}`);
  }

  const ranges = REQUIRED_COLUMNS.map((name) => {
    const index = headerMap.get(normalizeHeader(name));
    const column = colLetter(index);
    return `${quoteSheetTitle(SOURCE_SHEET_TITLE)}!${column}:${column}`;
  });
  const valueRanges = await valuesBatchGet(sourceSpreadsheetId, token, ranges);
  const columns = valueRanges.map((range) => range.values?.[0] || []);
  const maxRows = Math.max(...columns.map((column) => column.length), 1);
  const rows = [REQUIRED_COLUMNS];
  let skippedEmptyProject = 0;
  let skippedExcludedService = 0;

  for (let rowIndex = 1; rowIndex < maxRows; rowIndex += 1) {
    const row = columns.map((column) => safeText(column[rowIndex] ?? ""));
    const [project, service] = row;
    if (!project) {
      skippedEmptyProject += 1;
      continue;
    }
    if (EXCLUDED_SERVICES.has(normalizeService(service))) {
      skippedExcludedService += 1;
      continue;
    }
    rows.push(row);
  }

  return { rows, skippedEmptyProject, skippedExcludedService, sourceHeaderCount: headers.length };
}

function buildReadmeGrid({ dataRows, skippedEmptyProject, skippedExcludedService, sourceUrl, targetUrl }) {
  return [
    ["Назначение", "Закрытая база для автоматического обновления клиентского портфолио. Финансовые суммы не переносятся."],
    ["Источник", `${sourceUrl} / вкладка ${SOURCE_SHEET_TITLE}`],
    ["Цель", `${targetUrl} / вкладка ${DATA_SHEET_TITLE}`],
    ["Поля", REQUIRED_COLUMNS.join(", ")],
    ["Исключены услуги", EXCLUDED_SERVICE_LABELS.join(", ")],
    ["Строк данных", String(dataRows)],
    ["Пропущено без проекта", String(skippedEmptyProject)],
    ["Пропущено по исключённым услугам", String(skippedExcludedService)],
    ["Обновлено, МСК", nowMsk()],
  ];
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const sourceSpreadsheetId = extractSheetId(args.sourceUrl);
  const targetSpreadsheetId = extractSheetId(args.targetUrl);
  if (!sourceSpreadsheetId) throw new Error("Не удалось извлечь id исходной Google Sheets.");
  if (!targetSpreadsheetId) throw new Error("Не удалось извлечь id целевой Google Sheets.");

  const serviceAccount = JSON.parse(await readFile(args.serviceAccountPath, "utf8"));
  const token = await fetchAccessToken(serviceAccount);
  const portfolio = await readPortfolioRows(sourceSpreadsheetId, token);
  const readmeGrid = buildReadmeGrid({
    dataRows: portfolio.rows.length - 1,
    skippedEmptyProject: portfolio.skippedEmptyProject,
    skippedExcludedService: portfolio.skippedExcludedService,
    sourceUrl: args.sourceUrl,
    targetUrl: args.targetUrl,
  });

  if (!args.dryRun) {
    const sheetIds = await ensureTargetSheets(targetSpreadsheetId, token, [
      { title: DATA_SHEET_TITLE, rows: portfolio.rows.length, cols: REQUIRED_COLUMNS.length },
      { title: README_SHEET_TITLE, rows: readmeGrid.length, cols: 2 },
    ]);
    await valuesClear(targetSpreadsheetId, token, DATA_SHEET_TITLE, Math.max(portfolio.rows.length + 500, 1000), REQUIRED_COLUMNS.length);
    await valuesUpdate(targetSpreadsheetId, token, DATA_SHEET_TITLE, portfolio.rows);
    await batchUpdate(targetSpreadsheetId, token, dataStyleRequests(sheetIds.get(DATA_SHEET_TITLE), portfolio.rows.length, REQUIRED_COLUMNS.length));

    await valuesClear(targetSpreadsheetId, token, README_SHEET_TITLE, 100, 2);
    await valuesUpdate(targetSpreadsheetId, token, README_SHEET_TITLE, readmeGrid);
    await batchUpdate(targetSpreadsheetId, token, readmeStyleRequests(sheetIds.get(README_SHEET_TITLE), readmeGrid.length));
  }

  console.log(JSON.stringify({
    ok: true,
    dryRun: args.dryRun,
    source: args.sourceUrl,
    target: args.targetUrl,
    rows: portfolio.rows.length - 1,
    skippedEmptyProject: portfolio.skippedEmptyProject,
    skippedExcludedService: portfolio.skippedExcludedService,
    updatedAtMsk: nowMsk(),
  }, null, 2));
}

main().catch((error) => {
  console.error(String(error?.message || error || "unknown error"));
  process.exit(1);
});
