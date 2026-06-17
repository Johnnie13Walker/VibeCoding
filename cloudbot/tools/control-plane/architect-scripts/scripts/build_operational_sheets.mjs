import { createSign } from "node:crypto";
import { readFile } from "node:fs/promises";

const SHEET_URL = "https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit#gid=0";
const SA_PATH = process.env.MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON || process.env.GOOGLE_SERVICE_ACCOUNT_JSON || "/Users/pro2kuror/Downloads/finance-director-sheets-903611b799c3.json";
const COHORT_PATH = "/tmp/cohort_slice_3.json";
const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SCOPE = "https://www.googleapis.com/auth/spreadsheets";

const COLORS = {
  white: { red: 1, green: 1, blue: 1 },
  page: { red: 0.965, green: 0.973, blue: 0.984 },
  navy: { red: 0.071, green: 0.129, blue: 0.2 },
  navySoft: { red: 0.898, green: 0.933, blue: 0.965 },
  text: { red: 0.129, green: 0.161, blue: 0.215 },
  muted: { red: 0.325, green: 0.4, blue: 0.49 },
  acoola: { red: 0.067, green: 0.463, blue: 0.431 },
  acoolaSoft: { red: 0.875, green: 0.961, blue: 0.937 },
  belberry: { red: 0.113, green: 0.306, blue: 0.847 },
  belberrySoft: { red: 0.89, green: 0.929, blue: 0.992 },
  warningSoft: { red: 0.992, green: 0.945, blue: 0.863 },
  neutralSoft: { red: 0.949, green: 0.969, blue: 0.988 },
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
function makeGrid(rows, cols) {
  return Array.from({ length: rows }, () => Array(cols).fill(""));
}
function putRow(grid, rowIndex, colIndex, values) {
  values.forEach((value, offset) => {
    grid[rowIndex][colIndex + offset] = value;
  });
}
function fmtInt(value) {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(Number(value || 0));
}
function fmtPct(numerator, denominator) {
  const ratio = denominator ? Number(numerator || 0) / Number(denominator || 0) : 0;
  return new Intl.NumberFormat("ru-RU", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(ratio);
}
function sumRows(rows) {
  return rows.reduce((acc, row) => {
    acc.obr += Number(row.obr || 0);
    acc.lead += Number(row.lead || 0);
    acc.kp += Number(row.kp || 0);
    acc.contract += Number(row.contract || 0);
    acc.sale += Number(row.sale || 0);
    acc.revenue += Number(row.revenue || 0);
    return acc;
  }, { obr: 0, lead: 0, kp: 0, contract: 0, sale: 0, revenue: 0 });
}
function brandStyle(brand) {
  if (brand === "Acoola Team") return { accent: COLORS.acoola, soft: COLORS.acoolaSoft };
  if (brand === "Belberry") return { accent: COLORS.belberry, soft: COLORS.belberrySoft };
  return { accent: COLORS.navy, soft: COLORS.neutralSoft };
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
async function valuesUpdate(spreadsheetId, token, title, grid) {
  const rows = grid.length;
  const cols = grid[0].length;
  const range = `${quoteSheetTitle(title)}!A1:${colLetter(cols)}${rows}`;
  const res = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}?valueInputOption=USER_ENTERED`, {
    method: "PUT",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify({ majorDimension: "ROWS", values: grid }),
  });
  const payload = await res.json();
  if (!res.ok) throw new Error(`Values update error: ${res.status} ${JSON.stringify(payload)}`);
  return payload;
}
async function ensureSheet(spreadsheetId, token, sheets, title, rowCount = 200, columnCount = 12) {
  if (sheets.has(title)) return sheets.get(title);
  const result = await batchUpdate(spreadsheetId, token, [{ addSheet: { properties: { title, gridProperties: { rowCount, columnCount } } } }]);
  const createdSheetId = result.replies?.[0]?.addSheet?.properties?.sheetId;
  if (createdSheetId == null) throw new Error(`Не удалось создать вкладку "${title}"`);
  sheets.set(title, createdSheetId);
  return createdSheetId;
}
function styleRange(sheetId, startRow, endRow, startCol, endCol, userEnteredFormat) {
  return {
    repeatCell: {
      range: { sheetId, startRowIndex: startRow, endRowIndex: endRow, startColumnIndex: startCol, endColumnIndex: endCol },
      cell: { userEnteredFormat },
      fields: "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy,numberFormat)",
    },
  };
}
function setColumnWidth(sheetId, startCol, endCol, pixelSize) {
  return {
    updateDimensionProperties: {
      range: { sheetId, dimension: "COLUMNS", startIndex: startCol, endIndex: endCol },
      properties: { pixelSize },
      fields: "pixelSize",
    },
  };
}
function setRowHeight(sheetId, startRow, endRow, pixelSize) {
  return {
    updateDimensionProperties: {
      range: { sheetId, dimension: "ROWS", startIndex: startRow, endIndex: endRow },
      properties: { pixelSize },
      fields: "pixelSize",
    },
  };
}
function buildBrandTab(brand, rows, periodLabel) {
  const style = brandStyle(brand);
  const grid = makeGrid(28, 10);
  const total = sumRows(rows);
  putRow(grid, 0, 0, [`${brand} · Когортный слой`]);
  putRow(grid, 1, 0, [`Период: ${periodLabel}. Строка месяца = месяц создания сделки, метрики справа показывают текущий срез этой когорты на дату обновления.`]);
  putRow(grid, 3, 0, ["Обращения", fmtInt(total.obr), "Лиды", fmtInt(total.lead), "КП", fmtInt(total.kp), "Договоры", fmtInt(total.contract), "Продажи", fmtInt(total.sale)]);
  putRow(grid, 4, 0, ["Выручка", fmtInt(total.revenue), "CR обр → лид", fmtPct(total.lead, total.obr), "CR лид → КП", fmtPct(total.kp, total.lead), "CR КП → договор", fmtPct(total.contract, total.kp), "CR обр → продажа", fmtPct(total.sale, total.obr)]);
  putRow(grid, 6, 0, ["Месяц", "Обращения", "Лиды", "КП", "Договоры", "Продажи", "Выручка", "CR обр → лид", "CR КП → договор", "CR обр → продажа"]);
  rows.forEach((row, idx) => {
    putRow(grid, 7 + idx, 0, [
      row.month,
      fmtInt(row.obr),
      fmtInt(row.lead),
      fmtInt(row.kp),
      fmtInt(row.contract),
      fmtInt(row.sale),
      fmtInt(row.revenue),
      fmtPct(row.lead, row.obr),
      fmtPct(row.contract, row.kp),
      fmtPct(row.sale, row.obr),
    ]);
  });
  putRow(grid, 7 + rows.length, 0, [
    "Итого",
    fmtInt(total.obr),
    fmtInt(total.lead),
    fmtInt(total.kp),
    fmtInt(total.contract),
    fmtInt(total.sale),
    fmtInt(total.revenue),
    fmtPct(total.lead, total.obr),
    fmtPct(total.contract, total.kp),
    fmtPct(total.sale, total.obr),
  ]);
  return { grid, style };
}
function buildDealsGrid(rows, periodLabel) {
  const grid = makeGrid(Math.max(12, rows.length + 5), 8);
  putRow(grid, 0, 0, ["Все сделки sales-only"]);
  putRow(grid, 1, 0, [`Логика: сделка учитывается, если в ${periodLabel} проходила через воронку продаж. Даже если сейчас уже лежит в другой воронке, карточка остаётся в списке.`]);
  putRow(grid, 2, 0, ["Дата обращения", "Сделка", "ID", "Бренд", "Источник", "Менеджер", "Текущая воронка", "Текущий статус"]);
  rows.forEach((row, idx) => {
    putRow(grid, 3 + idx, 0, [
      row.created_at,
      `=HYPERLINK("${row.url}";"${String(row.title).replace(/"/g, '""')}")`,
      row.id,
      row.brand,
      row.source,
      row.manager || "—",
      row.current_category,
      row.current_stage,
    ]);
  });
  return grid;
}
function buildNoBrandGrid(rows, periodLabel) {
  const grid = makeGrid(Math.max(8, rows.length + 4), 8);
  putRow(grid, 0, 0, ["Сделки без бренда"]);
  putRow(grid, 1, 0, ["Период", periodLabel, "Количество", String(rows.length)]);
  putRow(grid, 2, 0, ["Дата обращения", "Сделка", "ID", "Бренд", "Источник", "Менеджер", "Текущая воронка", "Текущий статус"]);
  if (!rows.length) {
    putRow(grid, 3, 0, ["Нет строк"]);
    return grid;
  }
  rows.forEach((row, idx) => {
    putRow(grid, 3 + idx, 0, [
      row.created_at,
      `=HYPERLINK("${row.url}";"${String(row.title).replace(/"/g, '""')}")`,
      row.id,
      row.brand,
      row.source,
      row.manager || "—",
      row.current_category,
      row.current_stage,
    ]);
  });
  return grid;
}
function baseRequests(sheetId, rowCount, colCount, frozenRows = 3) {
  return [
    { updateCells: { range: { sheetId }, fields: "userEnteredValue,userEnteredFormat,textFormatRuns,dataValidation,note" } },
    { updateSheetProperties: { properties: { sheetId, gridProperties: { rowCount, columnCount: colCount, frozenRowCount: frozenRows } }, fields: "gridProperties.rowCount,gridProperties.columnCount,gridProperties.frozenRowCount" } },
    styleRange(sheetId, 0, 1, 0, colCount, { backgroundColor: COLORS.navy, textFormat: { foregroundColor: COLORS.white, fontSize: 18, bold: true }, horizontalAlignment: "CENTER", verticalAlignment: "MIDDLE" }),
    styleRange(sheetId, 1, 2, 0, colCount, { backgroundColor: COLORS.navySoft, textFormat: { foregroundColor: COLORS.text, bold: true }, verticalAlignment: "MIDDLE", wrapStrategy: "WRAP" }),
  ];
}
function buildDealsRequests(sheetId, rowCount) {
  return [
    ...baseRequests(sheetId, rowCount, 8, 3),
    { setBasicFilter: { filter: { range: { sheetId, startRowIndex: 2, endRowIndex: rowCount, startColumnIndex: 0, endColumnIndex: 8 } } } },
    styleRange(sheetId, 1, 2, 0, 8, { backgroundColor: COLORS.white, textFormat: { bold: true, foregroundColor: COLORS.text }, verticalAlignment: "MIDDLE", wrapStrategy: "WRAP" }),
    styleRange(sheetId, 2, 3, 0, 8, { backgroundColor: COLORS.white, textFormat: { bold: true, foregroundColor: COLORS.text }, horizontalAlignment: "CENTER", verticalAlignment: "MIDDLE", wrapStrategy: "WRAP" }),
    styleRange(sheetId, 3, rowCount, 0, 8, { backgroundColor: COLORS.white, textFormat: { foregroundColor: COLORS.text }, horizontalAlignment: "CENTER", verticalAlignment: "MIDDLE" }),
    setColumnWidth(sheetId, 0, 1, 116),
    setColumnWidth(sheetId, 1, 2, 270),
    setColumnWidth(sheetId, 2, 3, 86),
    setColumnWidth(sheetId, 3, 4, 145),
    setColumnWidth(sheetId, 4, 5, 150),
    setColumnWidth(sheetId, 5, 6, 150),
    setColumnWidth(sheetId, 6, 7, 145),
    setColumnWidth(sheetId, 7, 8, 180),
    setRowHeight(sheetId, 0, 1, 42),
    setRowHeight(sheetId, 1, 2, 30),
    setRowHeight(sheetId, 2, rowCount, 28),
  ];
}
function buildNoBrandRequests(sheetId, rowCount) {
  return [
    ...baseRequests(sheetId, rowCount, 8, 3),
    styleRange(sheetId, 1, 2, 0, 4, { backgroundColor: COLORS.warningSoft, textFormat: { foregroundColor: COLORS.text, bold: true }, verticalAlignment: "MIDDLE" }),
    styleRange(sheetId, 2, 3, 0, 8, { backgroundColor: COLORS.neutralSoft, textFormat: { bold: true, foregroundColor: COLORS.text }, horizontalAlignment: "CENTER", verticalAlignment: "MIDDLE" }),
    styleRange(sheetId, 3, rowCount, 0, 8, { backgroundColor: COLORS.white, textFormat: { foregroundColor: COLORS.text }, horizontalAlignment: "CENTER", verticalAlignment: "MIDDLE" }),
    setColumnWidth(sheetId, 0, 1, 116),
    setColumnWidth(sheetId, 1, 2, 270),
    setColumnWidth(sheetId, 2, 3, 86),
    setColumnWidth(sheetId, 3, 4, 145),
    setColumnWidth(sheetId, 4, 5, 150),
    setColumnWidth(sheetId, 5, 6, 150),
    setColumnWidth(sheetId, 6, 7, 145),
    setColumnWidth(sheetId, 7, 8, 180),
    setRowHeight(sheetId, 0, 1, 42),
    setRowHeight(sheetId, 1, 2, 28),
    setRowHeight(sheetId, 2, rowCount, 28),
  ];
}
function buildBrandRequests(sheetId, rowCount, brand) {
  const style = brandStyle(brand);
  return [
    ...baseRequests(sheetId, rowCount, 10, 7),
    styleRange(sheetId, 3, 5, 0, 10, { backgroundColor: style.soft, textFormat: { foregroundColor: COLORS.text, bold: true }, horizontalAlignment: "CENTER", verticalAlignment: "MIDDLE" }),
    styleRange(sheetId, 6, 7, 0, 10, { backgroundColor: style.accent, textFormat: { foregroundColor: COLORS.white, bold: true }, horizontalAlignment: "CENTER", verticalAlignment: "MIDDLE" }),
    styleRange(sheetId, 7, rowCount, 0, 10, { backgroundColor: COLORS.white, textFormat: { foregroundColor: COLORS.text }, horizontalAlignment: "CENTER", verticalAlignment: "MIDDLE" }),
    setColumnWidth(sheetId, 0, 1, 110),
    setColumnWidth(sheetId, 1, 6, 96),
    setColumnWidth(sheetId, 6, 7, 120),
    setColumnWidth(sheetId, 7, 10, 110),
    setRowHeight(sheetId, 0, 1, 42),
    setRowHeight(sheetId, 1, 2, 36),
    setRowHeight(sheetId, 3, 5, 28),
    setRowHeight(sheetId, 6, rowCount, 28),
  ];
}

const spreadsheetId = extractSheetId(SHEET_URL);
const sa = await loadJson(SA_PATH);
const cohort = await loadJson(COHORT_PATH);
const token = await fetchAccessToken(sa);
const metadata = await fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}`, token);
const sheets = new Map((metadata.sheets || []).map((sheet) => [sheet.properties.title, sheet.properties.sheetId]));

const detailRows = [...(cohort.detail_rows || [])];
const noBrandRows = detailRows.filter((row) => row.brand === "Без бренда");
const brandMonthRows = Object.entries(cohort.cohort_by_brand || {})
  .map(([key, metrics]) => {
    const [month, brand] = key.split("|||");
    return {
      month,
      brand,
      obr: Number(metrics.obr || 0),
      lead: Number(metrics.lead || 0),
      kp: Number(metrics.kp || 0),
      contract: Number(metrics.contract || 0),
      sale: Number(metrics.sale || 0),
      revenue: Number(metrics.revenue || 0),
    };
  })
  .sort((a, b) => a.month.localeCompare(b.month));

const periodLabel = String(cohort.meta?.period || "").replace("..", " — ");
const dealsTitle = "Сделки";
const noBrandTitle = "Без бренда";
const acoolaTitle = "Acoola Team";
const belberryTitle = "Belberry";

const dealsId = await ensureSheet(spreadsheetId, token, sheets, dealsTitle, Math.max(120, detailRows.length + 10), 7);
const noBrandId = await ensureSheet(spreadsheetId, token, sheets, noBrandTitle, Math.max(20, noBrandRows.length + 8), 7);
const acoolaId = await ensureSheet(spreadsheetId, token, sheets, acoolaTitle, 40, 10);
const belberryId = await ensureSheet(spreadsheetId, token, sheets, belberryTitle, 40, 10);

const dealsGrid = buildDealsGrid(detailRows, periodLabel);
const noBrandGrid = buildNoBrandGrid(noBrandRows, periodLabel);
const acoolaData = buildBrandTab(acoolaTitle, brandMonthRows.filter((row) => row.brand === acoolaTitle), periodLabel);
const belberryData = buildBrandTab(belberryTitle, brandMonthRows.filter((row) => row.brand === belberryTitle), periodLabel);

await batchUpdate(spreadsheetId, token, buildDealsRequests(dealsId, dealsGrid.length));
await valuesUpdate(spreadsheetId, token, dealsTitle, dealsGrid);

await batchUpdate(spreadsheetId, token, buildNoBrandRequests(noBrandId, noBrandGrid.length));
await valuesUpdate(spreadsheetId, token, noBrandTitle, noBrandGrid);

await batchUpdate(spreadsheetId, token, buildBrandRequests(acoolaId, acoolaData.grid.length, acoolaTitle));
await valuesUpdate(spreadsheetId, token, acoolaTitle, acoolaData.grid);

await batchUpdate(spreadsheetId, token, buildBrandRequests(belberryId, belberryData.grid.length, belberryTitle));
await valuesUpdate(spreadsheetId, token, belberryTitle, belberryData.grid);

console.log(JSON.stringify({
  sheets: [dealsTitle, noBrandTitle, acoolaTitle, belberryTitle],
  deals: detailRows.length,
  noBrand: noBrandRows.length,
  acoolaMonths: brandMonthRows.filter((row) => row.brand === acoolaTitle).length,
  belberryMonths: brandMonthRows.filter((row) => row.brand === belberryTitle).length,
}, null, 2));
