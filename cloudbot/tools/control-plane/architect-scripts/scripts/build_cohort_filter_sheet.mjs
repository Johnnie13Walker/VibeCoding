import { createSign } from "node:crypto";
import { readFile } from "node:fs/promises";

const SHEET_URL = "https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit#gid=0";
const SA_PATH = process.env.MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON || process.env.GOOGLE_SERVICE_ACCOUNT_JSON || "/Users/pro2kuror/Downloads/finance-director-sheets-903611b799c3.json";
const DATA_PATH = "/tmp/sales_only_q1_2026_details.json";
const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SCOPE = "https://www.googleapis.com/auth/spreadsheets";

const COLORS = {
  page: { red: 0.965, green: 0.973, blue: 0.984 },
  white: { red: 1, green: 1, blue: 1 },
  navy: { red: 0.071, green: 0.129, blue: 0.2 },
  navySoft: { red: 0.898, green: 0.933, blue: 0.965 },
  text: { red: 0.129, green: 0.161, blue: 0.215 },
  muted: { red: 0.325, green: 0.4, blue: 0.49 },
  acoola: { red: 0.067, green: 0.463, blue: 0.431 },
  acoolaSoft: { red: 0.875, green: 0.961, blue: 0.937 },
  belberry: { red: 0.113, green: 0.306, blue: 0.847 },
  belberrySoft: { red: 0.89, green: 0.929, blue: 0.992 },
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
function mergeRequest(sheetId, startRow, endRow, startCol, endCol) {
  return {
    mergeCells: {
      range: { sheetId, startRowIndex: startRow, endRowIndex: endRow, startColumnIndex: startCol, endColumnIndex: endCol },
      mergeType: "MERGE_ALL",
    },
  };
}
function styleRange(sheetId, startRow, endRow, startCol, endCol, userEnteredFormat, fields = "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy,numberFormat,borders)") {
  return {
    repeatCell: {
      range: { sheetId, startRowIndex: startRow, endRowIndex: endRow, startColumnIndex: startCol, endColumnIndex: endCol },
      cell: { userEnteredFormat },
      fields,
    },
  };
}
function borderStyle(color = COLORS.navySoft) {
  return {
    top: { style: "SOLID", color },
    bottom: { style: "SOLID", color },
    left: { style: "SOLID", color },
    right: { style: "SOLID", color },
  };
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
async function ensureSheet(spreadsheetId, token, sheets, title, rowCount = 200, columnCount = 24, hidden = false) {
  if (sheets.has(title)) return sheets.get(title);
  const result = await batchUpdate(spreadsheetId, token, [{ addSheet: { properties: { title, hidden, gridProperties: { rowCount, columnCount } } } }]);
  const createdSheetId = result.replies?.[0]?.addSheet?.properties?.sheetId;
  if (createdSheetId == null) throw new Error(`Не удалось создать вкладку "${title}"`);
  sheets.set(title, createdSheetId);
  return createdSheetId;
}

function toSourceRows(data) {
  return Object.entries(data.cohort_by_source || {})
    .map(([key, metrics]) => {
      const [month, brand, source] = key.split("|||");
      return {
        month,
        brand,
        source,
        obr: Number(metrics.obr || 0),
        lead: Number(metrics.lead || 0),
        kp: Number(metrics.kp || 0),
        contract: Number(metrics.contract || 0),
        sale: Number(metrics.sale || 0),
        revenue: Number(metrics.revenue || 0),
      };
    })
    .sort((a, b) => a.month.localeCompare(b.month) || a.brand.localeCompare(b.brand, "ru") || a.source.localeCompare(b.source, "ru"));
}

function distinctMonths(rows) {
  return Array.from(new Set(rows.map((row) => row.month))).sort();
}

function sourceList(rows, brand = "") {
  const filtered = brand ? rows.filter((row) => row.brand === brand) : rows;
  const map = new Map();
  for (const row of filtered) {
    const source = String(row.source || "Без источника").trim() || "Без источника";
    const bucket = map.get(source) || { source, obr: 0, lead: 0, kp: 0, contract: 0, sale: 0, revenue: 0 };
    bucket.obr += Number(row.obr || 0);
    bucket.lead += Number(row.lead || 0);
    bucket.kp += Number(row.kp || 0);
    bucket.contract += Number(row.contract || 0);
    bucket.sale += Number(row.sale || 0);
    bucket.revenue += Number(row.revenue || 0);
    map.set(source, bucket);
  }
  return Array.from(map.values()).sort((a, b) => b.obr - a.obr || b.lead - a.lead || a.source.localeCompare(b.source, "ru"));
}

function sourceMetricFormula(helperTitle, selHeaderRange, selCheckboxRange, metricCol, sourceCell, brand = "") {
  const helper = quoteSheetTitle(helperTitle);
  const monthMatch = `ISNUMBER(MATCH(${helper}!$A$2:$A;FILTER(${selHeaderRange};${selCheckboxRange}=TRUE);0))`;
  const brandCondition = brand ? `;${helper}!$B$2:$B="${brand}"` : "";
  return `=IF($${sourceCell}="";;IF(COUNTIF(${selCheckboxRange};TRUE)=0;0;IFERROR(SUM(FILTER(${helper}!$${metricCol}$2:$${metricCol};${monthMatch}${brandCondition};${helper}!$C$2:$C=$${sourceCell}));0)))`;
}

function sumMetricFormula(helperTitle, selHeaderRange, selCheckboxRange, metricCol, brand = "") {
  const helper = quoteSheetTitle(helperTitle);
  const monthMatch = `ISNUMBER(MATCH(${helper}!$A$2:$A;FILTER(${selHeaderRange};${selCheckboxRange}=TRUE);0))`;
  const brandCondition = brand ? `;${helper}!$B$2:$B="${brand}"` : "";
  return `=IF(COUNTIF(${selCheckboxRange};TRUE)=0;0;IFERROR(SUM(FILTER(${helper}!$${metricCol}$2:$${metricCol};${monthMatch}${brandCondition}));0))`;
}

function conversionFormula(numeratorCell, denominatorCell) {
  return `=IFERROR(${numeratorCell}/${denominatorCell};0)`;
}

const spreadsheetId = extractSheetId(SHEET_URL);
const sa = await loadJson(SA_PATH);
const data = await loadJson(DATA_PATH);
const sourceRows = toSourceRows(data);
const months = distinctMonths(sourceRows);
const helperTitle = "RAW · cohort_source";
const dashboardTitle = "Когортный фильтр";

const overallSources = sourceList(sourceRows);
const acoolaSources = sourceList(sourceRows, "Acoola Team");
const belberrySources = sourceList(sourceRows, "Belberry");
const overallSourceCount = Math.max(1, overallSources.length);
const acoolaSourceCount = Math.max(1, acoolaSources.length);
const belberrySourceCount = Math.max(1, belberrySources.length);

const overallStart = 17;
const acoolaStart = overallStart + overallSourceCount + 6;
const belberryStart = acoolaStart + acoolaSourceCount + 6;
const totalRows = belberryStart + belberrySourceCount + 8;
const totalCols = 22;

const token = await fetchAccessToken(sa);
const metadata = await fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}`, token);
const sheets = new Map((metadata.sheets || []).map((sheet) => [sheet.properties.title, sheet.properties.sheetId]));
const helperId = await ensureSheet(spreadsheetId, token, sheets, helperTitle, Math.max(200, sourceRows.length + 10), 10, true);
const dashboardId = await ensureSheet(spreadsheetId, token, sheets, dashboardTitle, Math.max(140, totalRows), totalCols, false);

const helperGrid = makeGrid(Math.max(sourceRows.length + 1, 2), 9);
putRow(helperGrid, 0, 0, ["Месяц", "Бренд", "Источник", "Обращения", "Лиды", "КП", "Договоры", "Продажи", "Выручка"]);
sourceRows.forEach((row, index) => {
  putRow(helperGrid, index + 1, 0, [`'${row.month}`, row.brand, row.source, row.obr, row.lead, row.kp, row.contract, row.sale, row.revenue]);
});

const grid = makeGrid(totalRows, totalCols);
putRow(grid, 0, 0, ["Когортный анализ · фильтр периода"]);
putRow(grid, 1, 0, ["Выбирай один или несколько месяцев. Все объёмы суммируются, конверсии пересчитываются от суммарной базы выбранных месяцев."]);
putRow(grid, 3, 0, ["Выбор месяцев"]);
putRow(grid, 4, 0, ["Период"]);
months.forEach((month, index) => {
  grid[4][1 + index] = `'${month}`;
  grid[5][1 + index] = true;
});
putRow(grid, 5, 0, ["Включить"]);
const selectorEndCol = colLetter(2 + months.length - 1);
const selectorHeaderRange = `$B$5:$${selectorEndCol}$5`;
const selectorCheckboxRange = `$B$6:$${selectorEndCol}$6`;
putRow(grid, 6, 0, [`=IF(COUNTIF(${selectorCheckboxRange};TRUE)=0;"Ничего не выбрано";"Выбрано: "&TEXTJOIN(", ";TRUE;FILTER(${selectorHeaderRange};${selectorCheckboxRange}=TRUE)))`]);

const blocks = [
  { title: "Общая сводка", col: 0, brand: "" },
  { title: "Acoola Team", col: 7, brand: "Acoola Team" },
  { title: "Belberry", col: 14, brand: "Belberry" },
];

for (const block of blocks) {
  const c = block.col;
  putRow(grid, 8, c, [block.title]);
  putRow(grid, 9, c, ["Обращения", "Лиды", "КП", "Договоры", "Продажи", "Выручка"]);
  grid[10][c + 0] = sumMetricFormula(helperTitle, selectorHeaderRange, selectorCheckboxRange, "D", block.brand);
  grid[10][c + 1] = sumMetricFormula(helperTitle, selectorHeaderRange, selectorCheckboxRange, "E", block.brand);
  grid[10][c + 2] = sumMetricFormula(helperTitle, selectorHeaderRange, selectorCheckboxRange, "F", block.brand);
  grid[10][c + 3] = sumMetricFormula(helperTitle, selectorHeaderRange, selectorCheckboxRange, "G", block.brand);
  grid[10][c + 4] = sumMetricFormula(helperTitle, selectorHeaderRange, selectorCheckboxRange, "H", block.brand);
  grid[10][c + 5] = sumMetricFormula(helperTitle, selectorHeaderRange, selectorCheckboxRange, "I", block.brand);
  putRow(grid, 12, c, ["CR обр→лид", "CR лид→КП", "CR КП→договор", "CR договор→продажа", "CR обр→продажа"]);
  grid[13][c + 0] = conversionFormula(`${colLetter(c + 2)}11`, `${colLetter(c + 1)}11`);
  grid[13][c + 1] = conversionFormula(`${colLetter(c + 3)}11`, `${colLetter(c + 2)}11`);
  grid[13][c + 2] = conversionFormula(`${colLetter(c + 4)}11`, `${colLetter(c + 3)}11`);
  grid[13][c + 3] = conversionFormula(`${colLetter(c + 5)}11`, `${colLetter(c + 4)}11`);
  grid[13][c + 4] = conversionFormula(`${colLetter(c + 5)}11`, `${colLetter(c + 1)}11`);
}

function buildSourceSection(startRow, title, brand = "", sources = []) {
  putRow(grid, startRow, 0, [title]);
  putRow(grid, startRow + 1, 0, ["Источник", "Обращения", "Лиды", "КП", "Договоры", "Продажи", "Выручка", "CR обр→лид", "CR лид→КП", "CR КП→договор", "CR договор→продажа", "CR обр→продажа"]);
  const formulaStart = startRow + 2;
  const sectionSources = sources.length ? sources : [{ source: "Нет данных" }];
  sectionSources.forEach((item, index) => {
    const row = formulaStart + index;
    const r = row + 1;
    grid[row][0] = item.source;
    grid[row][1] = sourceMetricFormula(helperTitle, selectorHeaderRange, selectorCheckboxRange, "D", `A${r}`, brand);
    grid[row][2] = sourceMetricFormula(helperTitle, selectorHeaderRange, selectorCheckboxRange, "E", `A${r}`, brand);
    grid[row][3] = sourceMetricFormula(helperTitle, selectorHeaderRange, selectorCheckboxRange, "F", `A${r}`, brand);
    grid[row][4] = sourceMetricFormula(helperTitle, selectorHeaderRange, selectorCheckboxRange, "G", `A${r}`, brand);
    grid[row][5] = sourceMetricFormula(helperTitle, selectorHeaderRange, selectorCheckboxRange, "H", `A${r}`, brand);
    grid[row][6] = sourceMetricFormula(helperTitle, selectorHeaderRange, selectorCheckboxRange, "I", `A${r}`, brand);
    grid[row][7] = `=IF(A${r}="";;IFERROR(C${r}/B${r};0))`;
    grid[row][8] = `=IF(A${r}="";;IFERROR(D${r}/C${r};0))`;
    grid[row][9] = `=IF(A${r}="";;IFERROR(E${r}/D${r};0))`;
    grid[row][10] = `=IF(A${r}="";;IFERROR(F${r}/E${r};0))`;
    grid[row][11] = `=IF(A${r}="";;IFERROR(F${r}/B${r};0))`;
  });
}

buildSourceSection(overallStart, "Источники · общая сводка", "", overallSources);
buildSourceSection(acoolaStart, "Источники · Acoola Team", "Acoola Team", acoolaSources);
buildSourceSection(belberryStart, "Источники · Belberry", "Belberry", belberrySources);

const requests = [
  { updateCells: { range: { sheetId: helperId }, fields: "userEnteredValue,userEnteredFormat,note,textFormatRuns,dataValidation" } },
  { updateSheetProperties: { properties: { sheetId: helperId, hidden: true, gridProperties: { frozenRowCount: 1 } }, fields: "hidden,gridProperties.frozenRowCount" } },
  { updateDimensionProperties: { range: { sheetId: helperId, dimension: "COLUMNS", startIndex: 0, endIndex: 9 }, properties: { pixelSize: 140 }, fields: "pixelSize" } },

  { updateCells: { range: { sheetId: dashboardId }, fields: "userEnteredValue,userEnteredFormat,note,textFormatRuns,dataValidation" } },
  { updateSheetProperties: { properties: { sheetId: dashboardId, gridProperties: { frozenRowCount: 6 } }, fields: "gridProperties.frozenRowCount" } },
  { updateDimensionProperties: { range: { sheetId: dashboardId, dimension: "ROWS", startIndex: 0, endIndex: 1 }, properties: { pixelSize: 42 }, fields: "pixelSize" } },
  { updateDimensionProperties: { range: { sheetId: dashboardId, dimension: "COLUMNS", startIndex: 0, endIndex: totalCols }, properties: { pixelSize: 118 }, fields: "pixelSize" } },
  styleRange(dashboardId, 0, totalRows, 0, totalCols, {
    backgroundColor: COLORS.page,
    textFormat: { foregroundColor: COLORS.text, fontFamily: "Arial", fontSize: 11 },
    verticalAlignment: "MIDDLE",
    wrapStrategy: "WRAP",
  }),
  mergeRequest(dashboardId, 0, 1, 0, totalCols),
  mergeRequest(dashboardId, 1, 2, 0, totalCols),
  mergeRequest(dashboardId, 3, 4, 0, totalCols),
  mergeRequest(dashboardId, 6, 7, 0, totalCols),
  styleRange(dashboardId, 0, 1, 0, totalCols, {
    backgroundColor: COLORS.navy,
    textFormat: { foregroundColor: COLORS.white, fontFamily: "Arial", fontSize: 19, bold: true },
    horizontalAlignment: "LEFT",
    verticalAlignment: "MIDDLE",
  }),
  styleRange(dashboardId, 1, 2, 0, totalCols, {
    backgroundColor: COLORS.navySoft,
    textFormat: { foregroundColor: COLORS.text, bold: true },
    wrapStrategy: "WRAP",
  }),
  styleRange(dashboardId, 3, 4, 0, totalCols, {
    backgroundColor: COLORS.neutralSoft,
    textFormat: { foregroundColor: COLORS.muted, bold: true, fontSize: 12 },
  }),
  styleRange(dashboardId, 4, 6, 0, 1 + months.length, {
    backgroundColor: COLORS.white,
    textFormat: { foregroundColor: COLORS.text, bold: true },
    horizontalAlignment: "CENTER",
    borders: borderStyle(),
  }),
  {
    setDataValidation: {
      range: { sheetId: dashboardId, startRowIndex: 5, endRowIndex: 6, startColumnIndex: 1, endColumnIndex: 1 + months.length },
      rule: { condition: { type: "BOOLEAN" }, strict: true, showCustomUi: true },
    },
  },
  styleRange(dashboardId, 6, 7, 0, totalCols, {
    backgroundColor: COLORS.neutralSoft,
    textFormat: { foregroundColor: COLORS.muted, italic: true, bold: true },
  }),

  mergeRequest(dashboardId, 8, 9, 0, 6),
  mergeRequest(dashboardId, 8, 9, 7, 13),
  mergeRequest(dashboardId, 8, 9, 14, 20),
  styleRange(dashboardId, 8, 9, 0, 6, {
    backgroundColor: COLORS.navy,
    textFormat: { foregroundColor: COLORS.white, bold: true, fontSize: 13 },
  }),
  styleRange(dashboardId, 8, 9, 7, 13, {
    backgroundColor: COLORS.acoola,
    textFormat: { foregroundColor: COLORS.white, bold: true, fontSize: 13 },
  }),
  styleRange(dashboardId, 8, 9, 14, 20, {
    backgroundColor: COLORS.belberry,
    textFormat: { foregroundColor: COLORS.white, bold: true, fontSize: 13 },
  }),
  styleRange(dashboardId, 9, 11, 0, 6, {
    backgroundColor: COLORS.white,
    textFormat: { foregroundColor: COLORS.muted, bold: true },
    horizontalAlignment: "CENTER",
    borders: borderStyle(),
  }),
  styleRange(dashboardId, 9, 11, 7, 13, {
    backgroundColor: COLORS.white,
    textFormat: { foregroundColor: COLORS.muted, bold: true },
    horizontalAlignment: "CENTER",
    borders: borderStyle(),
  }),
  styleRange(dashboardId, 9, 11, 14, 20, {
    backgroundColor: COLORS.white,
    textFormat: { foregroundColor: COLORS.muted, bold: true },
    horizontalAlignment: "CENTER",
    borders: borderStyle(),
  }),
  styleRange(dashboardId, 10, 11, 0, 6, { numberFormat: { type: "NUMBER", pattern: "# ##0" }, horizontalAlignment: "CENTER", borders: borderStyle() }, "userEnteredFormat(numberFormat,horizontalAlignment,borders)"),
  styleRange(dashboardId, 10, 11, 7, 13, { numberFormat: { type: "NUMBER", pattern: "# ##0" }, horizontalAlignment: "CENTER", borders: borderStyle() }, "userEnteredFormat(numberFormat,horizontalAlignment,borders)"),
  styleRange(dashboardId, 10, 11, 14, 20, { numberFormat: { type: "NUMBER", pattern: "# ##0" }, horizontalAlignment: "CENTER", borders: borderStyle() }, "userEnteredFormat(numberFormat,horizontalAlignment,borders)"),
  styleRange(dashboardId, 12, 14, 0, 5, {
    backgroundColor: COLORS.white,
    textFormat: { foregroundColor: COLORS.muted, bold: true },
    horizontalAlignment: "CENTER",
    borders: borderStyle(),
  }),
  styleRange(dashboardId, 12, 14, 7, 12, {
    backgroundColor: COLORS.white,
    textFormat: { foregroundColor: COLORS.muted, bold: true },
    horizontalAlignment: "CENTER",
    borders: borderStyle(),
  }),
  styleRange(dashboardId, 12, 14, 14, 19, {
    backgroundColor: COLORS.white,
    textFormat: { foregroundColor: COLORS.muted, bold: true },
    horizontalAlignment: "CENTER",
    borders: borderStyle(),
  }),
  styleRange(dashboardId, 13, 14, 0, 5, { numberFormat: { type: "PERCENT", pattern: "0.0%" }, horizontalAlignment: "CENTER", borders: borderStyle() }, "userEnteredFormat(numberFormat,horizontalAlignment,borders)"),
  styleRange(dashboardId, 13, 14, 7, 12, { numberFormat: { type: "PERCENT", pattern: "0.0%" }, horizontalAlignment: "CENTER", borders: borderStyle() }, "userEnteredFormat(numberFormat,horizontalAlignment,borders)"),
  styleRange(dashboardId, 13, 14, 14, 19, { numberFormat: { type: "PERCENT", pattern: "0.0%" }, horizontalAlignment: "CENTER", borders: borderStyle() }, "userEnteredFormat(numberFormat,horizontalAlignment,borders)"),
];

for (const [startRow, sourceCount, titleColor] of [
  [overallStart, overallSourceCount, COLORS.navy],
  [acoolaStart, acoolaSourceCount, COLORS.acoola],
  [belberryStart, belberrySourceCount, COLORS.belberry],
]) {
  const dataEndRow = startRow + 2 + sourceCount;
  requests.push(mergeRequest(dashboardId, startRow, startRow + 1, 0, 12));
  requests.push(styleRange(dashboardId, startRow, startRow + 1, 0, 12, {
    backgroundColor: titleColor,
    textFormat: { foregroundColor: COLORS.white, bold: true, fontSize: 13 },
  }));
  requests.push(styleRange(dashboardId, startRow + 1, startRow + 2, 0, 12, {
    backgroundColor: COLORS.neutralSoft,
    textFormat: { foregroundColor: COLORS.muted, bold: true },
    horizontalAlignment: "CENTER",
    borders: borderStyle(),
  }));
  requests.push(styleRange(dashboardId, startRow + 2, dataEndRow, 0, 7, {
    backgroundColor: COLORS.white,
    numberFormat: { type: "NUMBER", pattern: "# ##0" },
    borders: borderStyle(),
  }, "userEnteredFormat(backgroundColor,numberFormat,borders)"));
  requests.push(styleRange(dashboardId, startRow + 2, dataEndRow, 7, 12, {
    backgroundColor: COLORS.white,
    numberFormat: { type: "PERCENT", pattern: "0.0%" },
    horizontalAlignment: "CENTER",
    borders: borderStyle(),
  }, "userEnteredFormat(backgroundColor,numberFormat,horizontalAlignment,borders)"));
}

await batchUpdate(spreadsheetId, token, requests);
await valuesUpdate(spreadsheetId, token, helperTitle, helperGrid);
await valuesUpdate(spreadsheetId, token, dashboardTitle, grid);

console.log(JSON.stringify({
  sheet: dashboardTitle,
  helperSheet: helperTitle,
  months,
  overallSourceCount,
  acoolaSourceCount,
  belberrySourceCount,
}, null, 2));
