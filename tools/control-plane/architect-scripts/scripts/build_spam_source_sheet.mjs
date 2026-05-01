import { createSign } from "node:crypto";
import { readFile } from "node:fs/promises";

const SHEET_URL = "https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit#gid=0";
const SA_PATH = process.env.MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON || process.env.GOOGLE_SERVICE_ACCOUNT_JSON || "/Users/pro2kuror/Downloads/finance-director-sheets-903611b799c3.json";
const DATA_PATH = "/tmp/cohort_slice_3.json";
const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SCOPE = "https://www.googleapis.com/auth/spreadsheets";
const DASHBOARD_TITLE = "Спам по источникам";
const HELPER_TITLE = "RAW · spam_sources_2026";

const MONTHS_2026 = Array.from({ length: 12 }, (_, index) => `2026-${String(index + 1).padStart(2, "0")}`);
const MONTH_LABELS = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"];
const COLORS = {
  page: { red: 0.965, green: 0.973, blue: 0.984 },
  white: { red: 1, green: 1, blue: 1 },
  navy: { red: 0.071, green: 0.129, blue: 0.2 },
  slate: { red: 0.31, green: 0.36, blue: 0.43 },
  header: { red: 0.91, green: 0.95, blue: 0.98 },
  growing: { red: 0.86, green: 0.95, blue: 0.89 },
  falling: { red: 0.99, green: 0.9, blue: 0.88 },
  stable: { red: 0.94, green: 0.95, blue: 0.97 },
  problem: { red: 0.99, green: 0.94, blue: 0.94 },
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
  if (!res.ok) throw new Error(`Sheets API error: ${res.status} ${JSON.stringify(payload)}`);
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

async function valuesClear(spreadsheetId, token, range) {
  const res = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}:clear`, {
    method: "POST",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: "{}",
  });
  const payload = await res.json();
  if (!res.ok) throw new Error(`Values clear error: ${res.status} ${JSON.stringify(payload)}`);
  return payload;
}

async function ensureSheet(spreadsheetId, token, sheets, title, rowCount, columnCount, hidden = false) {
  if (sheets.has(title)) return sheets.get(title);
  const result = await batchUpdate(spreadsheetId, token, [{ addSheet: { properties: { title, hidden, gridProperties: { rowCount, columnCount } } } }]);
  const sheetId = result.replies?.[0]?.addSheet?.properties?.sheetId;
  if (sheetId == null) throw new Error(`Не удалось создать вкладку "${title}"`);
  sheets.set(title, sheetId);
  return sheetId;
}

function sourceStatus(values) {
  const active = values.map((value, index) => ({ value, index })).filter((item) => item.value > 0);
  if (active.length < 2) return { label: "без динамики", color: COLORS.stable };
  const first = active[0].value;
  const prev = active[active.length - 2].value;
  const last = active[active.length - 1].value;
  const lastMom = prev > 0 ? (last - prev) / prev : null;
  if (lastMom != null && lastMom > 0.1) return { label: "растёт", color: COLORS.growing };
  if (lastMom != null && lastMom < -0.1) return { label: "проседает", color: COLORS.falling };
  const totalChange = first > 0 ? (last - first) / first : 0;
  if (totalChange > 0.25) return { label: "растёт", color: COLORS.growing };
  if (totalChange < -0.25) return { label: "проседает", color: COLORS.falling };
  return { label: "без динамики", color: COLORS.stable };
}

function aggregateRows(rows, brand = "") {
  const filtered = brand ? rows.filter((row) => row.brand === brand) : rows;
  const monthTotals = new Map(MONTHS_2026.map((month) => [month, 0]));
  const bySource = new Map();
  for (const row of filtered) {
    if (!MONTHS_2026.includes(row.month)) continue;
    const source = String(row.source || "Без источника").trim() || "Без источника";
    monthTotals.set(row.month, (monthTotals.get(row.month) || 0) + 1);
    const bucket = bySource.get(source) || {
      source,
      months: Object.fromEntries(MONTHS_2026.map((month) => [month, 0])),
    };
    bucket.months[row.month] += 1;
    bySource.set(source, bucket);
  }
  const sources = Array.from(bySource.values())
    .map((row) => {
      const values = MONTHS_2026.map((month) => Number(row.months[month] || 0));
      const total = values.reduce((acc, value) => acc + value, 0);
      const status = sourceStatus(values);
      return {
        ...row,
        values,
        total,
        status: status.label,
        statusColor: status.color,
        isProblem: ["", "Без источника", "Не выяснено"].includes(row.source),
      };
    })
    .sort((a, b) => b.total - a.total || a.source.localeCompare(b.source, "ru"));
  return { sources, monthTotals };
}

function buildGrids(data) {
  const rows = data.spam_source_rows || [];
  const sections = [
    { title: "Спам · общая сводка", ...aggregateRows(rows) },
    { title: "Спам · Акула", ...aggregateRows(rows, "Acoola Team") },
    { title: "Спам · Белбери", ...aggregateRows(rows, "Belberry") },
  ];
  const totalMetricRows = sections.reduce((acc, section) => acc + section.sources.length + 1, 0);
  const cols = 15;
  const grid = makeGrid(Math.max(90, 12 + totalMetricRows + sections.length * 4), cols);
  const row = (() => {
    let index = 0;
    const writer = (values = [], col = 0) => {
      putRow(grid, index, col, values);
      index += 1;
      return index - 1;
    };
    writer.peek = () => index;
    return writer;
  })();

  const headerRow = row(["СПАМ ПО ИСТОЧНИКАМ"]);
  row(["Метрика", "Спамные лиды", "", "Период", "Январь-декабрь 2026", "", "Обновлено", data.meta?.updated_at || ""]);
  row(["Логика", "Учитываются только сделки sales/report-контура, у которых причина отказа в Bitrix24 равна «Спам» без учёта регистра и лишних пробелов. Месяц = месяц создания сделки."]);
  row(["Поле причины отказа", data.meta?.spam_filter?.rejection_reason_field || ""]);
  const legendRow = row(["Легенда", "растёт", "проседает", "без динамики"]);
  row([]);

  const sectionRanges = [];
  for (const section of sections) {
    const titleRow = row([section.title]);
    const tableHeaderRow = row(["Источник", "Статус", ...MONTH_LABELS, "Итого"]);
    const startRow = row.peek();
    section.sources.forEach((item) => {
      row([item.source, item.status, ...item.values, item.total]);
    });
    const totalValues = MONTHS_2026.map((month) => Number(section.monthTotals.get(month) || 0));
    const totalRow = row(["Итого", "", ...totalValues, totalValues.reduce((acc, value) => acc + value, 0)]);
    sectionRanges.push({ title: section.title, titleRow, tableHeaderRow, startRow, totalRow, endRow: totalRow + 1, metrics: section.sources, totalValues });
    row([]);
    row([]);
  }

  const helperGrid = makeGrid(Math.max(rows.length + 1, 2), 8);
  putRow(helperGrid, 0, 0, ["ID", "Месяц", "Бренд", "Источник", "Причина отказа", "Создано", "Название", "URL"]);
  rows.forEach((item, index) => {
    putRow(helperGrid, index + 1, 0, [item.id, item.month, item.brand, item.source, item.rejection_reason, item.created_at, item.title, item.url]);
  });

  return {
    grid,
    helperGrid,
    sectionRanges,
    ranges: {
      headerRow,
      legendRow,
      firstTableHeaderRow: sectionRanges[0]?.tableHeaderRow ?? 0,
    },
    totals: {
      overall: sectionRanges[0]?.totalValues.reduce((acc, value) => acc + value, 0) ?? 0,
      acoola: sectionRanges[1]?.totalValues.reduce((acc, value) => acc + value, 0) ?? 0,
      belberry: sectionRanges[2]?.totalValues.reduce((acc, value) => acc + value, 0) ?? 0,
    },
  };
}

function styleRange(sheetId, startRow, endRow, startCol, endCol, format, fields = "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy,numberFormat)") {
  return {
    repeatCell: {
      range: { sheetId, startRowIndex: startRow, endRowIndex: endRow, startColumnIndex: startCol, endColumnIndex: endCol },
      cell: { userEnteredFormat: format },
      fields,
    },
  };
}

function buildRequests(sheetId, helperSheetId, built) {
  const { grid, helperGrid, ranges, sectionRanges } = built;
  const requests = [
    { updateCells: { range: { sheetId }, fields: "userEnteredValue,userEnteredFormat,textFormatRuns,dataValidation,note" } },
    { unmergeCells: { range: { sheetId, startRowIndex: 0, endRowIndex: grid.length, startColumnIndex: 0, endColumnIndex: 18 } } },
    { updateSheetProperties: { properties: { sheetId, hidden: false, gridProperties: { frozenRowCount: ranges.firstTableHeaderRow + 1, frozenColumnCount: 0, rowCount: grid.length, columnCount: grid[0].length } }, fields: "hidden,gridProperties.frozenRowCount,gridProperties.frozenColumnCount,gridProperties.rowCount,gridProperties.columnCount" } },
    { updateSheetProperties: { properties: { sheetId: helperSheetId, hidden: true, gridProperties: { rowCount: helperGrid.length, columnCount: helperGrid[0].length } }, fields: "hidden,gridProperties.rowCount,gridProperties.columnCount" } },
    styleRange(sheetId, 0, grid.length, 0, grid[0].length, { backgroundColor: COLORS.page, textFormat: { fontFamily: "Arial", fontSize: 10, foregroundColor: { red: 0.13, green: 0.16, blue: 0.22 } }, verticalAlignment: "MIDDLE", wrapStrategy: "WRAP" }),
    { mergeCells: { range: { sheetId, startRowIndex: ranges.headerRow, endRowIndex: ranges.headerRow + 1, startColumnIndex: 0, endColumnIndex: 15 }, mergeType: "MERGE_ALL" } },
    { mergeCells: { range: { sheetId, startRowIndex: 2, endRowIndex: 3, startColumnIndex: 1, endColumnIndex: 15 }, mergeType: "MERGE_ALL" } },
    styleRange(sheetId, ranges.headerRow, ranges.headerRow + 1, 0, 15, { backgroundColor: COLORS.navy, textFormat: { bold: true, fontSize: 16, foregroundColor: { red: 1, green: 1, blue: 1 } }, horizontalAlignment: "LEFT" }),
    styleRange(sheetId, ranges.legendRow, ranges.legendRow + 1, 0, 4, { backgroundColor: COLORS.header, textFormat: { bold: true }, horizontalAlignment: "CENTER" }),
    styleRange(sheetId, ranges.legendRow, ranges.legendRow + 1, 1, 2, { backgroundColor: COLORS.growing, textFormat: { bold: true }, horizontalAlignment: "CENTER" }),
    styleRange(sheetId, ranges.legendRow, ranges.legendRow + 1, 2, 3, { backgroundColor: COLORS.falling, textFormat: { bold: true }, horizontalAlignment: "CENTER" }),
    styleRange(sheetId, ranges.legendRow, ranges.legendRow + 1, 3, 4, { backgroundColor: COLORS.stable, textFormat: { bold: true }, horizontalAlignment: "CENTER" }),
  ];

  sectionRanges.forEach((section) => {
    requests.push({ mergeCells: { range: { sheetId, startRowIndex: section.titleRow, endRowIndex: section.titleRow + 1, startColumnIndex: 0, endColumnIndex: 15 }, mergeType: "MERGE_ALL" } });
    requests.push(styleRange(sheetId, section.titleRow, section.titleRow + 1, 0, 15, { backgroundColor: COLORS.slate, textFormat: { bold: true, fontSize: 12, foregroundColor: { red: 1, green: 1, blue: 1 } }, horizontalAlignment: "LEFT" }));
    requests.push(styleRange(sheetId, section.tableHeaderRow, section.tableHeaderRow + 1, 0, 15, { backgroundColor: COLORS.header, textFormat: { bold: true }, horizontalAlignment: "CENTER" }));
    requests.push(styleRange(sheetId, section.startRow, section.totalRow, 0, 15, { backgroundColor: COLORS.white, horizontalAlignment: "CENTER" }));
    requests.push(styleRange(sheetId, section.totalRow, section.totalRow + 1, 0, 15, { backgroundColor: COLORS.header, textFormat: { bold: true }, horizontalAlignment: "CENTER" }));
    section.metrics.forEach((item, index) => {
      const rowIndex = section.startRow + index;
      requests.push(styleRange(sheetId, rowIndex, rowIndex + 1, 1, 2, { backgroundColor: item.statusColor, textFormat: { bold: true }, horizontalAlignment: "CENTER" }));
      if (item.isProblem) requests.push(styleRange(sheetId, rowIndex, rowIndex + 1, 0, 1, { backgroundColor: COLORS.problem, textFormat: { bold: true }, horizontalAlignment: "LEFT" }));
    });
    requests.push({
      updateBorders: {
        range: { sheetId, startRowIndex: section.tableHeaderRow, endRowIndex: section.endRow, startColumnIndex: 0, endColumnIndex: 15 },
        top: { style: "SOLID", color: { red: 0.78, green: 0.82, blue: 0.87 } },
        bottom: { style: "SOLID", color: { red: 0.78, green: 0.82, blue: 0.87 } },
        left: { style: "SOLID", color: { red: 0.78, green: 0.82, blue: 0.87 } },
        right: { style: "SOLID", color: { red: 0.78, green: 0.82, blue: 0.87 } },
        innerHorizontal: { style: "SOLID", color: { red: 0.88, green: 0.9, blue: 0.93 } },
        innerVertical: { style: "SOLID", color: { red: 0.88, green: 0.9, blue: 0.93 } },
      },
    });
  });

  [190, 110, ...Array(12).fill(78), 88].forEach((pixelSize, index) => {
    requests.push({ updateDimensionProperties: { range: { sheetId, dimension: "COLUMNS", startIndex: index, endIndex: index + 1 }, properties: { pixelSize }, fields: "pixelSize" } });
  });
  requests.push({ updateDimensionProperties: { range: { sheetId, dimension: "ROWS", startIndex: ranges.headerRow, endIndex: ranges.headerRow + 1 }, properties: { pixelSize: 44 }, fields: "pixelSize" } });
  return requests;
}

const spreadsheetId = extractSheetId(SHEET_URL);
const [sa, data] = await Promise.all([loadJson(SA_PATH), loadJson(DATA_PATH)]);
const built = buildGrids(data);
const token = await fetchAccessToken(sa);
const metadata = await fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}`, token);
const sheets = new Map((metadata.sheets || []).map((sheet) => [sheet.properties.title, sheet.properties.sheetId]));
const sheetId = await ensureSheet(spreadsheetId, token, sheets, DASHBOARD_TITLE, built.grid.length, built.grid[0].length, false);
const helperSheetId = await ensureSheet(spreadsheetId, token, sheets, HELPER_TITLE, built.helperGrid.length, built.helperGrid[0].length, true);

await batchUpdate(spreadsheetId, token, buildRequests(sheetId, helperSheetId, built));
await valuesClear(spreadsheetId, token, `${quoteSheetTitle(DASHBOARD_TITLE)}!A1:R140`);
await valuesClear(spreadsheetId, token, `${quoteSheetTitle(HELPER_TITLE)}!A1:H500`);
await valuesUpdate(spreadsheetId, token, DASHBOARD_TITLE, built.grid);
await valuesUpdate(spreadsheetId, token, HELPER_TITLE, built.helperGrid);

console.log(JSON.stringify({
  sheet: DASHBOARD_TITLE,
  helper: HELPER_TITLE,
  total: built.totals.overall,
  acoola: built.totals.acoola,
  belberry: built.totals.belberry,
}, null, 2));
