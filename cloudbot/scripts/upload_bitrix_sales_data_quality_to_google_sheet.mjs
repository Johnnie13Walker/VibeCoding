#!/usr/bin/env node
import { createSign } from "node:crypto";
import { readFile } from "node:fs/promises";

const DEFAULT_TARGET_URL = "https://docs.google.com/spreadsheets/d/1WMXNBqigq-uq7izvnkDfQsK3tgecHRc8nvvte1TXUKc/edit?gid=0#gid=0";
const TARGET_URL = process.env.BITRIX_SALES_DATA_QUALITY_SHEET_URL || process.argv[3] || DEFAULT_TARGET_URL;
const DATA_PATH = process.env.BITRIX_SALES_DATA_QUALITY_JSON_PATH || process.argv[2];
const SA_PATH = process.env.MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON
  || process.env.GOOGLE_SERVICE_ACCOUNT_JSON
  || "/Users/pro2kuror/.config/openclo/assistant/secrets/finance-director-sheets-903611b799c3.json";
const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SCOPE = "https://www.googleapis.com/auth/spreadsheets";

const COLORS = {
  header: { red: 0.121, green: 0.306, blue: 0.471 },
  summary: { red: 0.898, green: 0.933, blue: 0.965 },
  warning: { red: 1, green: 0.949, blue: 0.8 },
  white: { red: 1, green: 1, blue: 1 },
};

function base64url(input) {
  return Buffer.from(input).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
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
  const text = String(value ?? "");
  return /^[=+\-@]/.test(text) ? `'${text}` : text;
}

function buildJwt({ client_email: clientEmail, private_key: privateKey }) {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "RS256", typ: "JWT" };
  const claim = { iss: clientEmail, scope: SCOPE, aud: TOKEN_URL, exp: now + 3600, iat: now };
  const encodedHeader = base64url(JSON.stringify(header));
  const encodedClaim = base64url(JSON.stringify(claim));
  const signer = createSign("RSA-SHA256");
  signer.update(`${encodedHeader}.${encodedClaim}`);
  signer.end();
  const signature = signer.sign(privateKey, "base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  return `${encodedHeader}.${encodedClaim}.${signature}`;
}

async function fetchAccessToken(serviceAccount) {
  const body = new URLSearchParams({
    grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
    assertion: buildJwt(serviceAccount),
  });
  const res = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
  });
  const payload = await res.json();
  if (!res.ok || !payload.access_token) {
    throw new Error(`OAuth error: ${res.status} ${JSON.stringify(payload)}`);
  }
  return String(payload.access_token);
}

async function fetchJson(url, token, init = {}) {
  const res = await fetch(url, {
    ...init,
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json", ...(init.headers || {}) },
  });
  const payload = await res.json();
  if (!res.ok) {
    throw new Error(`Sheets API error: ${res.status} ${JSON.stringify(payload)}`);
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

async function valuesUpdate(spreadsheetId, token, title, grid) {
  const rows = Math.max(grid.length, 1);
  const cols = Math.max(...grid.map((row) => row.length), 1);
  const normalized = grid.map((row) => Array.from({ length: cols }, (_, index) => row[index] ?? ""));
  const range = `${quoteSheetTitle(title)}!A1:${colLetter(cols)}${rows}`;
  const res = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}?valueInputOption=USER_ENTERED`, {
    method: "PUT",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify({ majorDimension: "ROWS", values: normalized }),
  });
  const payload = await res.json();
  if (!res.ok) {
    throw new Error(`Values update error: ${res.status} ${JSON.stringify(payload)}`);
  }
  return payload;
}

async function valuesClear(spreadsheetId, token, title, rows, cols) {
  const range = `${quoteSheetTitle(title)}!A1:${colLetter(cols)}${rows}`;
  const res = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}:clear`, {
    method: "POST",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: "{}",
  });
  const payload = await res.json();
  if (!res.ok) {
    throw new Error(`Values clear error: ${res.status} ${JSON.stringify(payload)}`);
  }
  return payload;
}

async function ensureSheets(spreadsheetId, token, desired) {
  const metadata = await fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}?includeGridData=false`, token);
  const sheets = new Map((metadata.sheets || []).map((sheet) => [sheet.properties.title, sheet.properties]));
  const requests = [];

  for (const item of desired) {
    if (!sheets.has(item.title)) {
      requests.push({
        addSheet: {
          properties: {
            title: item.title,
            gridProperties: { rowCount: Math.max(item.rows + 20, 100), columnCount: Math.max(item.cols + 2, 12) },
          },
        },
      });
    }
  }

  if (requests.length) await batchUpdate(spreadsheetId, token, requests);
  const updated = await fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}?includeGridData=false`, token);
  return new Map((updated.sheets || []).map((sheet) => [sheet.properties.title, sheet.properties.sheetId]));
}

function styleRequests(sheetId, rows, cols, widths) {
  const requests = [
    {
      updateSheetProperties: {
        properties: { sheetId, gridProperties: { frozenRowCount: 1, rowCount: Math.max(rows + 20, 100), columnCount: Math.max(cols + 2, 12) } },
        fields: "gridProperties(frozenRowCount,rowCount,columnCount)",
      },
    },
    {
      repeatCell: {
        range: { sheetId, startRowIndex: 0, endRowIndex: 1, startColumnIndex: 0, endColumnIndex: cols },
        cell: {
          userEnteredFormat: {
            backgroundColor: COLORS.header,
            textFormat: { bold: true, foregroundColor: COLORS.white },
            wrapStrategy: "WRAP",
            verticalAlignment: "MIDDLE",
          },
        },
        fields: "userEnteredFormat(backgroundColor,textFormat,wrapStrategy,verticalAlignment)",
      },
    },
    {
      repeatCell: {
        range: { sheetId, startRowIndex: 1, endRowIndex: Math.max(rows, 2), startColumnIndex: 0, endColumnIndex: cols },
        cell: { userEnteredFormat: { wrapStrategy: "WRAP", verticalAlignment: "TOP" } },
        fields: "userEnteredFormat(wrapStrategy,verticalAlignment)",
      },
    },
    {
      setBasicFilter: {
        filter: { range: { sheetId, startRowIndex: 0, endRowIndex: Math.max(rows, 2), startColumnIndex: 0, endColumnIndex: cols } },
      },
    },
  ];
  widths.forEach((pixelSize, index) => {
    requests.push({
      updateDimensionProperties: {
        range: { sheetId, dimension: "COLUMNS", startIndex: index, endIndex: index + 1 },
        properties: { pixelSize },
        fields: "pixelSize",
      },
    });
  });
  return requests;
}

function buildSummaryGrid(payload) {
  const byBucket = payload.by_bucket || {};
  const byBucketWithProblems = payload.by_bucket_with_problems || {};
  const byProblem = payload.by_problem || {};
  const rows = [
    ["Отчёт по качеству данных сделок Bitrix24", ""],
    ["Сформировано, МСК", nowMsk()],
    ["Воронка/category_id", String(payload.category_id || "")],
    ["Шаблон БП обновления данных", String(payload.bp_template_id || "")],
    ["Поля «Сайт клиента»", [
      ...(payload.client_site_fields?.deal || []).map((field) => `deal:${field}`),
      ...(payload.client_site_fields?.company || []).map((field) => `company:${field}`),
    ].join(", ")],
    ["Поля причины отказа", (payload.lost_reason_fields || []).join(", ")],
    ["Исключено как СПАМ по причине отказа", Number(payload.excluded_spam_reason_count || 0)],
    ["Сделок проверено", Number(payload.deals_checked_count || 0)],
    ["Сделок с проблемами", Number(payload.deals_with_problems_count || 0)],
    ["Сделок без проблем", Number(payload.deals_without_problems_count || 0)],
    ["", ""],
    ["Статус сделки", "Всего / с проблемами"],
  ];
  for (const [bucket, count] of Object.entries(byBucket)) {
    rows.push([safeText(bucket), `${count} / ${byBucketWithProblems[bucket] || 0}`]);
  }
  rows.push(["", ""]);
  rows.push(["Проблема", "Кол-во сделок"]);
  for (const [problem, count] of Object.entries(byProblem)) {
    rows.push([safeText(problem), Number(count || 0)]);
  }
  const warnings = Array.isArray(payload.warnings) ? payload.warnings.filter(Boolean) : [];
  if (warnings.length) {
    rows.push(["", ""]);
    rows.push(["Предупреждение", warnings.map(safeText).join("\n")]);
  }
  return rows;
}

const DETAIL_COLUMNS = [
  ["priority", "Приоритет"],
  ["stage_bucket", "Статус"],
  ["stage_name", "Стадия"],
  ["deal_id", "Сделка ID"],
  ["deal_title", "Сделка"],
  ["deal_url", "Ссылка на сделку"],
  ["company_id", "Компания ID"],
  ["company_title", "Компания"],
  ["company_url", "Ссылка на компанию"],
  ["company_web", "Сайт"],
  ["client_site", "Сайт клиента"],
  ["inn", "ИНН"],
  ["kpp", "КПП"],
  ["ogrn", "ОГРН"],
  ["requisites_count", "Реквизитов"],
  ["running_bp_count", "Активных БП"],
  ["company_contacts_count", "Контактов в компании"],
  ["deal_contacts_count", "Контактов в сделке"],
  ["missing_contacts_count", "Не добавлено контактов"],
  ["missing_contacts", "Каких контактов не хватает"],
  ["problems_count", "Кол-во проблем"],
  ["problems", "Проблемы"],
  ["recommended_actions", "Что нужно сделать"],
  ["opportunity", "Сумма"],
  ["currency", "Валюта"],
  ["date_create", "Создана"],
  ["date_modify", "Обновлена"],
  ["assigned_by_id", "Ответственный ID"],
];

function buildRows(items) {
  return [
    DETAIL_COLUMNS.map(([, title]) => title),
    ...items.map((item) => DETAIL_COLUMNS.map(([key]) => safeText(item[key]))),
  ];
}

function buildData(payload) {
  const rows = Array.isArray(payload.rows) ? payload.rows : [];
  const problemRows = rows.filter((row) => Number(row.problems_count || 0) > 0);
  const detailWidths = [110, 100, 220, 95, 270, 280, 110, 280, 280, 260, 260, 140, 110, 140, 100, 100, 120, 120, 135, 340, 110, 360, 520, 110, 90, 160, 160, 130];
  return [
    { title: "Сводка Bitrix", grid: buildSummaryGrid(payload), widths: [320, 240] },
    {
      title: "Проблемные сделки",
      grid: buildRows(problemRows.length ? problemRows : [{ priority: "ОК", problems: "Проблемных сделок не найдено" }]),
      widths: detailWidths,
    },
    {
      title: "Все сделки",
      grid: buildRows(rows.length ? rows : [{ priority: "Нет данных", problems: "Сделки не найдены" }]),
      widths: detailWidths,
    },
  ];
}

async function main() {
  if (!DATA_PATH) throw new Error("Не передан путь к JSON-отчёту.");
  const spreadsheetId = extractSheetId(TARGET_URL);
  if (!spreadsheetId) throw new Error("Не удалось извлечь spreadsheet id.");

  const serviceAccount = JSON.parse(await readFile(SA_PATH, "utf8"));
  const token = await fetchAccessToken(serviceAccount);
  const payload = JSON.parse(await readFile(DATA_PATH, "utf8"));
  const sheets = buildData(payload);
  const sheetIds = await ensureSheets(spreadsheetId, token, sheets.map((sheet) => ({
    title: sheet.title,
    rows: sheet.grid.length,
    cols: Math.max(...sheet.grid.map((row) => row.length)),
  })));

  for (const sheet of sheets) {
    const cols = Math.max(...sheet.grid.map((row) => row.length));
    await valuesClear(spreadsheetId, token, sheet.title, Math.max(sheet.grid.length + 100, 500), Math.max(cols + 5, 32));
    await valuesUpdate(spreadsheetId, token, sheet.title, sheet.grid);
    const sheetId = sheetIds.get(sheet.title);
    await batchUpdate(spreadsheetId, token, styleRequests(sheetId, sheet.grid.length, cols, sheet.widths));
  }

  const verifyRange = `${quoteSheetTitle("Сводка Bitrix")}!A1:B7`;
  const verify = await fetchJson(
    `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(verifyRange)}?majorDimension=ROWS`,
    token,
  );
  console.log(JSON.stringify({
    ok: true,
    spreadsheetId,
    url: TARGET_URL,
    summaryRows: verify.values?.length || 0,
    problemRows: Number(payload.deals_with_problems_count || 0),
    allRows: Number(payload.deals_checked_count || 0),
  }, null, 2));
}

main().catch((error) => {
  console.error(String(error?.message || error || "unknown error"));
  process.exit(1);
});
