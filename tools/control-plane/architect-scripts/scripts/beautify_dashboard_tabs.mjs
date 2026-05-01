import { createSign } from "node:crypto";
import { readFile } from "node:fs/promises";

const SHEET_URL = "https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit#gid=0";
const SA_PATH = process.env.MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON || process.env.GOOGLE_SERVICE_ACCOUNT_JSON || "/Users/pro2kuror/Downloads/finance-director-sheets-903611b799c3.json";
const COHORT_PATH = "/tmp/sales_only_q1_2026_details.json";
const EVENTS_PATH = "/tmp/true_events_q1_2026.json";
const WINS_PATH = "/tmp/wins_ytd_2026.json";
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
  warningSoft: { red: 0.992, green: 0.945, blue: 0.863 },
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
function setSectionHeader(grid, row, colStart, width, title) {
  putRow(grid, row, colStart, [title]);
  for (let i = 1; i < width; i += 1) grid[row][colStart + i] = "";
}
function brandConfig(brand) {
  if (brand === "Acoola Team") return { accent: COLORS.acoola, soft: COLORS.acoolaSoft };
  if (brand === "Belberry") return { accent: COLORS.belberry, soft: COLORS.belberrySoft };
  return { accent: COLORS.navy, soft: COLORS.warningSoft };
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

function styleRange(sheetId, startRow, endRow, startCol, endCol, userEnteredFormat) {
  return {
    repeatCell: {
      range: { sheetId, startRowIndex: startRow, endRowIndex: endRow, startColumnIndex: startCol, endColumnIndex: endCol },
      cell: { userEnteredFormat },
      fields: "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)",
    },
  };
}
function centerRange(sheetId, startRow, endRow, startCol, endCol) {
  return {
    repeatCell: {
      range: { sheetId, startRowIndex: startRow, endRowIndex: endRow, startColumnIndex: startCol, endColumnIndex: endCol },
      cell: { userEnteredFormat: { horizontalAlignment: "CENTER", verticalAlignment: "MIDDLE" } },
      fields: "userEnteredFormat(horizontalAlignment,verticalAlignment)",
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

function setFrozenRows(sheetId, frozenRowCount) {
  return {
    updateSheetProperties: {
      properties: { sheetId, gridProperties: { frozenRowCount } },
      fields: "gridProperties.frozenRowCount",
    },
  };
}

function visualGuardRequests(sheetId, cfg) {
  const requests = [];
  const { totalCols, frozenRows, rowHeights = [], serviceRows = [], tableHeaderRows = [], formatRows = [], filter = null } = cfg;
  requests.push(setFrozenRows(sheetId, frozenRows));
  requests.push(styleRange(sheetId, 0, 1, 0, totalCols, {
    backgroundColor: COLORS.navy,
    textFormat: { foregroundColor: COLORS.white, fontSize: 18, bold: true },
    horizontalAlignment: "CENTER",
    verticalAlignment: "MIDDLE",
    wrapStrategy: "WRAP",
  }));
  for (const [startRow, endRow, px] of rowHeights) requests.push(setRowHeight(sheetId, startRow, endRow, px));
  for (const [startRow, endRow] of serviceRows) {
    requests.push(styleRange(sheetId, startRow, endRow, 0, totalCols, {
      verticalAlignment: "MIDDLE",
      wrapStrategy: "WRAP",
    }));
  }
  for (const [startRow, endRow] of tableHeaderRows) {
    requests.push(styleRange(sheetId, startRow, endRow, 0, totalCols, {
      horizontalAlignment: "CENTER",
      verticalAlignment: "MIDDLE",
      wrapStrategy: "WRAP",
    }));
  }
  for (const item of formatRows) {
    const [startRow, endRow, maybeStartCol, maybeEndCol, maybeFormat] = item;
    const startCol = typeof maybeFormat === "object" ? maybeStartCol : 0;
    const endCol = typeof maybeFormat === "object" ? maybeEndCol : totalCols;
    const format = typeof maybeFormat === "object" ? maybeFormat : maybeStartCol;
    requests.push(styleRange(sheetId, startRow, endRow, startCol, endCol, format));
  }
  if (filter) {
    requests.push({
      setBasicFilter: {
        filter: {
          range: {
            sheetId,
            startRowIndex: filter.startRowIndex,
            endRowIndex: filter.endRowIndex,
            startColumnIndex: filter.startColumnIndex,
            endColumnIndex: filter.endColumnIndex,
          },
        },
      },
    });
  }
  return requests;
}

function rowsByBrandFromCohort(data) {
  const rows = [];
  for (const [key, metrics] of Object.entries(data.cohort_by_brand || {})) {
    const [month, brand] = key.split("|||");
    rows.push({
      month,
      brand,
      obr: Number(metrics.obr || 0),
      lead: Number(metrics.lead || 0),
      kp: Number(metrics.kp || 0),
      contract: Number(metrics.contract || 0),
      sale: Number(metrics.sale || 0),
      revenue: Number(metrics.revenue || 0),
    });
  }
  return rows.sort((a, b) => a.month.localeCompare(b.month));
}
function rowsByBrandFromEvents(data, cohortRows) {
  const obrMap = new Map(cohortRows.map((row) => [`${row.month}|||${row.brand}`, Number(row.obr || 0)]));
  return [...(data.event_rows || [])].map((row) => ({
    month: row.month,
    brand: row.brand,
    obr: obrMap.get(`${row.month}|||${row.brand}`) || 0,
    lead: Number(row.lead || 0),
    kp: Number(row.kp || 0),
    contract: Number(row.contract || 0),
    sale: Number(row.sale || 0),
    revenue: Number(row.revenue || 0),
  })).sort((a, b) => a.month.localeCompare(b.month));
}

function buildComparisonRows(metricsByBrand) {
  const acoola = metricsByBrand.get("Acoola Team") || { obr: 0, lead: 0, kp: 0, contract: 0, sale: 0, revenue: 0 };
  const belberry = metricsByBrand.get("Belberry") || { obr: 0, lead: 0, kp: 0, contract: 0, sale: 0, revenue: 0 };
  const noBrand = metricsByBrand.get("Без бренда") || { obr: 0, lead: 0, kp: 0, contract: 0, sale: 0, revenue: 0 };
  const total = {
    obr: acoola.obr + belberry.obr + noBrand.obr,
    lead: acoola.lead + belberry.lead + noBrand.lead,
    kp: acoola.kp + belberry.kp + noBrand.kp,
    contract: acoola.contract + belberry.contract + noBrand.contract,
    sale: acoola.sale + belberry.sale + noBrand.sale,
    revenue: acoola.revenue + belberry.revenue + noBrand.revenue,
  };
  return [
    ["Метрика", "Acoola Team", "Belberry", "Без бренда", "Всего"],
    ["Обращения", fmtInt(acoola.obr), fmtInt(belberry.obr), fmtInt(noBrand.obr), fmtInt(total.obr)],
    ["Лиды", fmtInt(acoola.lead), fmtInt(belberry.lead), fmtInt(noBrand.lead), fmtInt(total.lead)],
    ["КП", fmtInt(acoola.kp), fmtInt(belberry.kp), fmtInt(noBrand.kp), fmtInt(total.kp)],
    ["Договоры", fmtInt(acoola.contract), fmtInt(belberry.contract), fmtInt(noBrand.contract), fmtInt(total.contract)],
    ["Продажи", fmtInt(acoola.sale), fmtInt(belberry.sale), fmtInt(noBrand.sale), fmtInt(total.sale)],
    ["Выручка", fmtInt(acoola.revenue), fmtInt(belberry.revenue), fmtInt(noBrand.revenue), fmtInt(total.revenue)],
  ];
}

function buildMonthlyBrandGrid(title, subtitle, brandRowsMap, noBrandRows = []) {
  const grid = makeGrid(32, 17);
  putRow(grid, 0, 0, [title]);
  putRow(grid, 1, 0, [subtitle]);
  putRow(grid, 3, 0, ["Общая сводка"]);

  const metricsByBrand = new Map([
    ["Acoola Team", sumRows(brandRowsMap.get("Acoola Team") || [])],
    ["Belberry", sumRows(brandRowsMap.get("Belberry") || [])],
    ["Без бренда", sumRows(noBrandRows)],
  ]);
  const summary = buildComparisonRows(metricsByBrand);
  summary.forEach((row, idx) => putRow(grid, 4 + idx, 0, row));

  const brandLayouts = [
    { brand: "Acoola Team", col: 0 },
    { brand: "Belberry", col: 9 },
  ];
  for (const { brand, col } of brandLayouts) {
    const rows = brandRowsMap.get(brand) || [];
    const total = sumRows(rows);
    const start = 13;
    setSectionHeader(grid, start, col, 8, brand);
    putRow(grid, start + 1, col, ["Месяц", "Обращения", "Лиды", "КП", "Договоры", "Продажи", "Выручка", "CR обр → продажа"]);
    rows.forEach((row, idx) => {
      putRow(grid, start + 2 + idx, col, [
        row.month,
        fmtInt(row.obr),
        fmtInt(row.lead),
        fmtInt(row.kp),
        fmtInt(row.contract),
        fmtInt(row.sale),
        fmtInt(row.revenue),
        fmtPct(row.sale, row.obr),
      ]);
    });
    putRow(grid, start + 2 + rows.length, col, ["Итого", fmtInt(total.obr), fmtInt(total.lead), fmtInt(total.kp), fmtInt(total.contract), fmtInt(total.sale), fmtInt(total.revenue), fmtPct(total.sale, total.obr)]);
  }

  putRow(grid, 22, 0, ["Без бренда"]);
  putRow(grid, 23, 0, ["Месяц", "Обращения", "Лиды", "КП", "Договоры", "Продажи", "Выручка"]);
  if (noBrandRows.length) {
    noBrandRows.forEach((row, idx) => putRow(grid, 24 + idx, 0, [row.month, fmtInt(row.obr), fmtInt(row.lead), fmtInt(row.kp), fmtInt(row.contract), fmtInt(row.sale), fmtInt(row.revenue)]));
  } else {
    putRow(grid, 24, 0, ["Нет строк"]);
  }
  return grid;
}

function buildSourceBlocks(rows) {
  const total = sumRows(rows);
  const byMonth = new Map();
  for (const row of rows) {
    if (!byMonth.has(row.month)) byMonth.set(row.month, []);
    byMonth.get(row.month).push(row);
  }
  const output = [];
  output.push(["Итого за период", "", fmtInt(total.obr), fmtInt(total.lead), fmtInt(total.kp), fmtInt(total.contract), fmtInt(total.sale), fmtInt(total.revenue), fmtPct(total.sale, total.obr)]);
  for (const [month, monthRows] of [...byMonth.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    const monthTotal = sumRows(monthRows);
    output.push([month, "Итого месяца", fmtInt(monthTotal.obr), fmtInt(monthTotal.lead), fmtInt(monthTotal.kp), fmtInt(monthTotal.contract), fmtInt(monthTotal.sale), fmtInt(monthTotal.revenue), fmtPct(monthTotal.sale, monthTotal.obr)]);
    monthRows
      .sort((a, b) => a.source.localeCompare(b.source, "ru"))
      .forEach((row) => {
        output.push([row.month, row.source, fmtInt(row.obr), fmtInt(row.lead), fmtInt(row.kp), fmtInt(row.contract), fmtInt(row.sale), fmtInt(row.revenue), fmtPct(row.sale, row.obr)]);
      });
  }
  return output;
}

function buildSourcesGrid(sourceRows) {
  const grid = makeGrid(72, 19);
  putRow(grid, 0, 0, ["Источники по месяцам · Когортный слой"]);
  putRow(grid, 1, 0, ["Сделка относится к месяцу её создания. Источник не пересчитывается при переносах между воронками."]);
  putRow(grid, 3, 0, ["Общая сводка"]);

  const group = new Map();
  for (const brand of ["Acoola Team", "Belberry", "Без бренда"]) {
    group.set(brand, sourceRows.filter((row) => row.brand === brand));
  }
  const metricsByBrand = new Map([...group.entries()].map(([brand, rows]) => [brand, sumRows(rows)]));
  buildComparisonRows(metricsByBrand).forEach((row, idx) => putRow(grid, 4 + idx, 0, row));

  const sections = [
    { brand: "Acoola Team", col: 0 },
    { brand: "Belberry", col: 10 },
  ];
  for (const { brand, col } of sections) {
    const rows = buildSourceBlocks(group.get(brand));
    setSectionHeader(grid, 13, col, 9, brand);
    putRow(grid, 14, col, ["Месяц", "Источник", "Обращения", "Лиды", "КП", "Договоры", "Продажи", "Выручка", "CR обр → продажа"]);
    rows.forEach((row, idx) => putRow(grid, 15 + idx, col, row));
  }

  const noBrand = group.get("Без бренда");
  putRow(grid, 50, 0, ["Без бренда"]);
  putRow(grid, 51, 0, ["Месяц", "Источник", "Обращения", "Лиды", "КП", "Договоры", "Продажи", "Выручка", "CR обр → продажа"]);
  if (noBrand.length) {
    buildSourceBlocks(noBrand).forEach((row, idx) => putRow(grid, 52 + idx, 0, row));
  } else {
    putRow(grid, 52, 0, ["Нет строк"]);
  }
  return grid;
}

function buildWinsSummaryRows(dealRows, serviceRows) {
  const byBrandDeals = new Map();
  const byBrandServices = new Map();
  for (const brand of ["Acoola Team", "Belberry", "Без бренда"]) {
    byBrandDeals.set(brand, dealRows.filter((row) => row.brand === brand));
    byBrandServices.set(brand, serviceRows.filter((row) => row.brand === brand));
  }
  return [
    ["Бренд", "Сделок", "Строк услуг", "Выручка"],
    ...["Acoola Team", "Belberry", "Без бренда"].map((brand) => [
      brand,
      fmtInt(byBrandDeals.get(brand).length),
      fmtInt(byBrandServices.get(brand).length),
      fmtInt(byBrandDeals.get(brand).reduce((acc, row) => acc + Number(row.deal_amount || 0), 0)),
    ]),
  ];
}

function buildWinsDealsGrid(wins) {
  const acoolaRows = wins.deal_rows.filter((row) => row.brand === "Acoola Team");
  const belberryRows = wins.deal_rows.filter((row) => row.brand === "Belberry");
  const noBrandRows = wins.deal_rows.filter((row) => row.brand === "Без бренда");
  const rowCount = Math.max(34, 13 + acoolaRows.length + belberryRows.length + noBrandRows.length + 8);
  const grid = makeGrid(rowCount, 8);
  const sections = [];
  putRow(grid, 0, 0, ["Продажи YTD 2026 · уникальные сделки"]);
  putRow(grid, 1, 0, ["Событийный слой по дате первого входа в УСПЕХ. Одна строка = одна выигранная сделка."]);
  putRow(grid, 3, 0, ["Общая сводка"]);
  buildWinsSummaryRows(wins.deal_rows, wins.service_rows).forEach((row, idx) => putRow(grid, 4 + idx, 0, row));

  let cursor = 10;
  for (const [brand, rows] of [["Acoola Team", acoolaRows], ["Belberry", belberryRows]]) {
    setSectionHeader(grid, cursor, 0, 7, brand);
    putRow(grid, cursor + 1, 0, ["Дата УСПЕХ", "Сделка", "ID", "Источник", "Менеджер", "Отдел", "Сумма"]);
    rows.forEach((row, idx) => putRow(grid, cursor + 2 + idx, 0, [
      row.won_at,
      `=HYPERLINK("${row.url}";"${String(row.title).replace(/"/g, '""')}")`,
      row.deal_id,
      row.source,
      row.manager,
      row.category,
      fmtInt(row.deal_amount),
    ]));
    sections.push({ brand, startCol: 0, endCol: 7, titleRow: cursor + 1, headerRow: cursor + 2, dataRowStart: cursor + 3, dataRowEnd: cursor + 3 + rows.length, totalRow: null, centerFromCol: 0 });
    cursor += rows.length + 4;
  }
  const noBrandTitleRow = cursor;
  putRow(grid, noBrandTitleRow, 0, ["Без бренда"]);
  putRow(grid, noBrandTitleRow + 1, 0, ["Дата УСПЕХ", "Сделка", "ID", "Источник", "Менеджер", "Отдел", "Сумма"]);
  noBrandRows.forEach((row, idx) => putRow(grid, noBrandTitleRow + 2 + idx, 0, [
    row.won_at,
    `=HYPERLINK("${row.url}";"${String(row.title).replace(/"/g, '""')}")`,
    row.deal_id,
    row.source,
    row.manager,
    row.category,
    fmtInt(row.deal_amount),
  ]));
  grid.brandSections = sections;
  grid.noBrandSection = { startCol: 0, endCol: 7, titleRow: noBrandTitleRow + 1, headerRow: noBrandTitleRow + 2, dataRowStart: noBrandTitleRow + 3, dataRowEnd: noBrandTitleRow + 3 + noBrandRows.length, centerFromCol: 0 };
  return grid;
}

function buildWinsServicesGrid(wins) {
  const acoolaRows = wins.service_rows.filter((row) => row.brand === "Acoola Team");
  const belberryRows = wins.service_rows.filter((row) => row.brand === "Belberry");
  const noBrandRows = wins.service_rows.filter((row) => row.brand === "Без бренда");
  const rowCount = Math.max(42, 13 + acoolaRows.length + belberryRows.length + noBrandRows.length + 8);
  const grid = makeGrid(rowCount, 9);
  const sections = [];
  putRow(grid, 0, 0, ["Продажи YTD 2026 · услуги внутри сделок"]);
  putRow(grid, 1, 0, ["Событийный слой по дате первого входа в УСПЕХ. Одна строка = одна услуга в выигранной сделке."]);
  putRow(grid, 3, 0, ["Общая сводка"]);
  buildWinsSummaryRows(wins.deal_rows, wins.service_rows).forEach((row, idx) => putRow(grid, 4 + idx, 0, row));

  let cursor = 10;
  for (const [brand, rows] of [["Acoola Team", acoolaRows], ["Belberry", belberryRows]]) {
    setSectionHeader(grid, cursor, 0, 8, brand);
    putRow(grid, cursor + 1, 0, ["Дата УСПЕХ", "Сделка", "ID", "Источник", "Менеджер", "Услуга", "Сумма строки", "Сумма сделки"]);
    rows.forEach((row, idx) => putRow(grid, cursor + 2 + idx, 0, [
      row.won_at,
      `=HYPERLINK("${row.url}";"${String(row.title).replace(/"/g, '""')}")`,
      row.deal_id,
      row.source,
      row.manager,
      row.service,
      fmtInt(row.service_amount),
      fmtInt(row.deal_amount),
    ]));
    sections.push({ brand, startCol: 0, endCol: 8, titleRow: cursor + 1, headerRow: cursor + 2, dataRowStart: cursor + 3, dataRowEnd: cursor + 3 + rows.length, totalRow: null, centerFromCol: 0 });
    cursor += rows.length + 4;
  }
  const noBrandTitleRow = cursor;
  putRow(grid, noBrandTitleRow, 0, ["Без бренда"]);
  putRow(grid, noBrandTitleRow + 1, 0, ["Дата УСПЕХ", "Сделка", "ID", "Источник", "Менеджер", "Услуга", "Сумма строки", "Сумма сделки"]);
  noBrandRows.forEach((row, idx) => putRow(grid, noBrandTitleRow + 2 + idx, 0, [
    row.won_at,
    `=HYPERLINK("${row.url}";"${String(row.title).replace(/"/g, '""')}")`,
    row.deal_id,
    row.source,
    row.manager,
    row.service,
    fmtInt(row.service_amount),
    fmtInt(row.deal_amount),
  ]));
  grid.brandSections = sections;
  grid.noBrandSection = { startCol: 0, endCol: 8, titleRow: noBrandTitleRow + 1, headerRow: noBrandTitleRow + 2, dataRowStart: noBrandTitleRow + 3, dataRowEnd: noBrandTitleRow + 3 + noBrandRows.length, centerFromCol: 0 };
  return grid;
}

function buildStyledRequests(sheetId, totalCols, options) {
  const {
    summaryRow = 4,
    summaryHeaderRow = 5,
    brandSections = [],
    noBrandSection = null,
    frozenRowCount = 3,
    rowCount = 120,
    columnWidths = [],
    rowHeights = [],
  } = options;
  const requests = [
    { updateCells: { range: { sheetId }, fields: "userEnteredValue,userEnteredFormat,textFormatRuns,dataValidation,note" } },
    { updateSheetProperties: { properties: { sheetId, gridProperties: { frozenRowCount, rowCount, columnCount: totalCols } }, fields: "gridProperties.frozenRowCount,gridProperties.rowCount,gridProperties.columnCount" } },
    styleRange(sheetId, 0, 1, 0, totalCols, { backgroundColor: COLORS.navy, textFormat: { foregroundColor: COLORS.white, fontSize: 18, bold: true }, horizontalAlignment: "CENTER", verticalAlignment: "MIDDLE" }),
    styleRange(sheetId, 1, 2, 0, totalCols, { backgroundColor: COLORS.navySoft, textFormat: { foregroundColor: COLORS.text, fontSize: 10, bold: true }, verticalAlignment: "MIDDLE" }),
    styleRange(sheetId, summaryRow - 1, summaryRow, 0, 5, { backgroundColor: COLORS.navy, textFormat: { foregroundColor: COLORS.white, bold: true }, horizontalAlignment: "CENTER", verticalAlignment: "MIDDLE" }),
    styleRange(sheetId, summaryHeaderRow - 1, summaryHeaderRow, 0, 5, { backgroundColor: COLORS.neutralSoft, textFormat: { foregroundColor: COLORS.muted, bold: true }, horizontalAlignment: "CENTER", verticalAlignment: "MIDDLE" }),
    centerRange(sheetId, summaryHeaderRow, summaryHeaderRow + 10, 1, 5),
    { autoResizeDimensions: { dimensions: { sheetId, dimension: "COLUMNS", startIndex: 0, endIndex: totalCols } } },
  ];

  for (const section of brandSections) {
    const cfg = brandConfig(section.brand);
    requests.push(styleRange(sheetId, section.titleRow - 1, section.titleRow, section.startCol, section.endCol, { backgroundColor: cfg.accent, textFormat: { foregroundColor: COLORS.white, bold: true, fontSize: 13 }, horizontalAlignment: "CENTER", verticalAlignment: "MIDDLE" }));
    requests.push(styleRange(sheetId, section.headerRow - 1, section.headerRow, section.startCol, section.endCol, { backgroundColor: cfg.soft, textFormat: { foregroundColor: COLORS.text, bold: true }, horizontalAlignment: "CENTER", verticalAlignment: "MIDDLE" }));
    if (section.totalRow) {
      requests.push(styleRange(sheetId, section.totalRow - 1, section.totalRow, section.startCol, section.endCol, { backgroundColor: COLORS.white, textFormat: { foregroundColor: COLORS.text, bold: true }, verticalAlignment: "MIDDLE" }));
    }
    if (section.dataRowStart && section.dataRowEnd && section.dataRowEnd > section.dataRowStart) {
      requests.push(styleRange(sheetId, section.dataRowStart - 1, section.dataRowEnd, section.startCol, section.endCol, { backgroundColor: COLORS.white, textFormat: { foregroundColor: COLORS.text }, verticalAlignment: "MIDDLE", wrapStrategy: "CLIP" }));
      requests.push(centerRange(sheetId, section.dataRowStart - 1, section.dataRowEnd, section.centerFromCol ?? section.numericStartCol ?? section.startCol + 1, section.endCol));
    }
  }

  if (noBrandSection) {
    requests.push(styleRange(sheetId, noBrandSection.titleRow - 1, noBrandSection.titleRow, noBrandSection.startCol, noBrandSection.endCol, { backgroundColor: COLORS.warningSoft, textFormat: { foregroundColor: COLORS.text, bold: true, fontSize: 12 }, horizontalAlignment: "CENTER", verticalAlignment: "MIDDLE" }));
    requests.push(styleRange(sheetId, noBrandSection.headerRow - 1, noBrandSection.headerRow, noBrandSection.startCol, noBrandSection.endCol, { backgroundColor: COLORS.neutralSoft, textFormat: { foregroundColor: COLORS.muted, bold: true }, horizontalAlignment: "CENTER", verticalAlignment: "MIDDLE" }));
    if (noBrandSection.dataRowStart && noBrandSection.dataRowEnd && noBrandSection.dataRowEnd > noBrandSection.dataRowStart) {
      requests.push(styleRange(sheetId, noBrandSection.dataRowStart - 1, noBrandSection.dataRowEnd, noBrandSection.startCol, noBrandSection.endCol, { backgroundColor: COLORS.white, textFormat: { foregroundColor: COLORS.text }, verticalAlignment: "MIDDLE", wrapStrategy: "CLIP" }));
      requests.push(centerRange(sheetId, noBrandSection.dataRowStart - 1, noBrandSection.dataRowEnd, noBrandSection.centerFromCol ?? noBrandSection.startCol + 1, noBrandSection.endCol));
    }
  }
  for (const item of columnWidths) requests.push(setColumnWidth(sheetId, item.startCol, item.endCol, item.px));
  for (const item of rowHeights) requests.push(setRowHeight(sheetId, item.startRow, item.endRow, item.px));
  return requests;
}

const spreadsheetId = extractSheetId(SHEET_URL);
const sa = await loadJson(SA_PATH);
const cohort = await loadJson(COHORT_PATH);
const events = await loadJson(EVENTS_PATH);
const wins = await loadJson(WINS_PATH);
const token = await fetchAccessToken(sa);
const metadata = await fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}`, token);
const sheets = new Map((metadata.sheets || []).map((sheet) => [sheet.properties.title, sheet.properties.sheetId]));

const cohortRows = rowsByBrandFromCohort(cohort);
const cohortMap = new Map(["Acoola Team", "Belberry", "Без бренда"].map((brand) => [brand, cohortRows.filter((row) => row.brand === brand)]));
const cohortSourceRows = Object.entries(cohort.cohort_by_source || {}).map(([key, metrics]) => {
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
});

const eventRows = rowsByBrandFromEvents(events, cohortRows);
const eventMap = new Map(["Acoola Team", "Belberry", "Без бренда"].map((brand) => [brand, eventRows.filter((row) => row.brand === brand)]));

const dynamicsGrid = buildMonthlyBrandGrid("Динамика по месяцам · Когортный слой", "Месяц строки = месяц создания сделки. Сводка сверху показывает общий объём по брендам и хвост без бренда.", cohortMap, cohortMap.get("Без бренда"));
const eventsGrid = buildMonthlyBrandGrid("События по месяцам · Событийный слой", "Месяц строки = месяц первого входа сделки в этап. Подходит для чтения фактических переходов по воронке.", eventMap, eventMap.get("Без бренда"));
const sourcesGrid = buildSourcesGrid(cohortSourceRows);
const dealsYtdGrid = buildWinsDealsGrid(wins);
const servicesYtdGrid = buildWinsServicesGrid(wins);

const sheetsToPaint = [
  {
    title: "Динамика по месяцам",
    grid: dynamicsGrid,
    cols: 17,
    requests: buildStyledRequests(sheets.get("Динамика по месяцам"), 17, {
      rowCount: dynamicsGrid.length,
      brandSections: [
        { brand: "Acoola Team", startCol: 0, endCol: 8, titleRow: 14, headerRow: 15, dataRowStart: 16, dataRowEnd: 19, totalRow: 19 },
        { brand: "Belberry", startCol: 9, endCol: 17, titleRow: 14, headerRow: 15, dataRowStart: 16, dataRowEnd: 19, totalRow: 19 },
      ],
      noBrandSection: { startCol: 0, endCol: 7, titleRow: 23, headerRow: 24, dataRowStart: 25, dataRowEnd: 26 },
    }),
  },
  {
    title: "События по месяцам",
    grid: eventsGrid,
    cols: 17,
    requests: buildStyledRequests(sheets.get("События по месяцам"), 17, {
      rowCount: eventsGrid.length,
      brandSections: [
        { brand: "Acoola Team", startCol: 0, endCol: 8, titleRow: 14, headerRow: 15, dataRowStart: 16, dataRowEnd: 19, totalRow: 19 },
        { brand: "Belberry", startCol: 9, endCol: 17, titleRow: 14, headerRow: 15, dataRowStart: 16, dataRowEnd: 19, totalRow: 19 },
      ],
      noBrandSection: { startCol: 0, endCol: 7, titleRow: 23, headerRow: 24, dataRowStart: 25, dataRowEnd: 26 },
    }),
  },
  {
    title: "Источники по месяцам",
    grid: sourcesGrid,
    cols: 19,
    requests: buildStyledRequests(sheets.get("Источники по месяцам"), 19, {
      rowCount: sourcesGrid.length,
      brandSections: [
        { brand: "Acoola Team", startCol: 0, endCol: 9, titleRow: 14, headerRow: 15, dataRowStart: 16, dataRowEnd: 34, totalRow: 16 },
        { brand: "Belberry", startCol: 10, endCol: 19, titleRow: 14, headerRow: 15, dataRowStart: 16, dataRowEnd: 40, totalRow: 16 },
      ],
      noBrandSection: { startCol: 0, endCol: 9, titleRow: 51, headerRow: 52, dataRowStart: 53, dataRowEnd: 56 },
    }),
  },
  {
    title: "Продажи YTD 2026 · сделки",
    grid: dealsYtdGrid,
    cols: 8,
    requests: buildStyledRequests(sheets.get("Продажи YTD 2026 · сделки"), 8, {
      rowCount: dealsYtdGrid.length,
      brandSections: dealsYtdGrid.brandSections,
      noBrandSection: dealsYtdGrid.noBrandSection,
      columnWidths: [
        { startCol: 0, endCol: 1, px: 116 },
        { startCol: 1, endCol: 2, px: 270 },
        { startCol: 2, endCol: 3, px: 86 },
        { startCol: 3, endCol: 4, px: 150 },
        { startCol: 4, endCol: 5, px: 120 },
        { startCol: 5, endCol: 6, px: 110 },
        { startCol: 6, endCol: 7, px: 110 },
        { startCol: 7, endCol: 8, px: 28 },
      ],
      rowHeights: [
        { startRow: 0, endRow: 1, px: 44 },
        { startRow: 1, endRow: 2, px: 28 },
        { startRow: 3, endRow: dealsYtdGrid.length, px: 30 },
      ],
    }),
  },
  {
    title: "Продажи YTD 2026 · услуги",
    grid: servicesYtdGrid,
    cols: 9,
    requests: buildStyledRequests(sheets.get("Продажи YTD 2026 · услуги"), 9, {
      rowCount: servicesYtdGrid.length,
      brandSections: servicesYtdGrid.brandSections,
      noBrandSection: servicesYtdGrid.noBrandSection,
      columnWidths: [
        { startCol: 0, endCol: 1, px: 116 },
        { startCol: 1, endCol: 2, px: 254 },
        { startCol: 2, endCol: 3, px: 86 },
        { startCol: 3, endCol: 4, px: 145 },
        { startCol: 4, endCol: 5, px: 120 },
        { startCol: 5, endCol: 6, px: 120 },
        { startCol: 6, endCol: 7, px: 116 },
        { startCol: 7, endCol: 8, px: 116 },
        { startCol: 8, endCol: 9, px: 28 },
      ],
      rowHeights: [
        { startRow: 0, endRow: 1, px: 44 },
        { startRow: 1, endRow: 2, px: 28 },
        { startRow: 3, endRow: servicesYtdGrid.length, px: 30 },
      ],
    }),
  },
];

for (const sheet of sheetsToPaint) {
  await batchUpdate(spreadsheetId, token, sheet.requests);
  await valuesUpdate(spreadsheetId, token, sheet.title, sheet.grid);
}

const visualGuardConfigs = [
  {
    title: "CEO Dashboard",
    totalCols: 14,
    frozenRows: 3,
    rowHeights: [[0, 1, 46], [1, 2, 38], [2, 3, 26]],
    serviceRows: [[1, 3]],
  },
  {
    title: "Сделки",
    totalCols: 8,
    frozenRows: 3,
    rowHeights: [[0, 1, 44], [1, 2, 36], [2, 3, 36]],
    serviceRows: [[1, 2]],
    tableHeaderRows: [[2, 3]],
    formatRows: [
      [1, 2, { backgroundColor: COLORS.white, textFormat: { foregroundColor: COLORS.text, bold: true }, verticalAlignment: "MIDDLE", wrapStrategy: "WRAP" }],
      [2, 3, { backgroundColor: COLORS.white, textFormat: { foregroundColor: COLORS.text, bold: true }, horizontalAlignment: "CENTER", verticalAlignment: "MIDDLE", wrapStrategy: "WRAP" }],
    ],
    filter: { startRowIndex: 2, endRowIndex: Math.max((cohort.detail_rows || []).length + 3, 4), startColumnIndex: 0, endColumnIndex: 8 },
  },
  {
    title: "Продажи YTD 2026 · сделки",
    totalCols: 8,
    frozenRows: 3,
    rowHeights: [[0, 1, 46], [1, 2, 44], [2, 3, 22], [3, 4, 28]],
    serviceRows: [[1, 3]],
    tableHeaderRows: [[4, 5], [11, 12]],
    formatRows: [
      [1, 3, { backgroundColor: COLORS.white, textFormat: { foregroundColor: COLORS.text }, verticalAlignment: "MIDDLE", wrapStrategy: "WRAP" }],
      [3, 4, 0, 5, { backgroundColor: COLORS.navy, textFormat: { foregroundColor: COLORS.white, bold: true }, horizontalAlignment: "LEFT", verticalAlignment: "MIDDLE", wrapStrategy: "WRAP" }],
    ],
  },
  {
    title: "Продажи YTD 2026 · услуги",
    totalCols: 9,
    frozenRows: 3,
    rowHeights: [[0, 1, 46], [1, 2, 44], [2, 3, 22], [3, 4, 28]],
    serviceRows: [[1, 3]],
    tableHeaderRows: [[4, 5], [11, 12]],
    formatRows: [
      [1, 3, { backgroundColor: COLORS.white, textFormat: { foregroundColor: COLORS.text }, verticalAlignment: "MIDDLE", wrapStrategy: "WRAP" }],
      [3, 4, 0, 5, { backgroundColor: COLORS.navy, textFormat: { foregroundColor: COLORS.white, bold: true }, horizontalAlignment: "LEFT", verticalAlignment: "MIDDLE", wrapStrategy: "WRAP" }],
    ],
  },
  {
    title: "Когортный фильтр",
    totalCols: 22,
    frozenRows: 6,
    rowHeights: [[0, 1, 46], [1, 2, 52], [2, 3, 22], [3, 4, 34], [4, 6, 30], [6, 7, 30]],
    serviceRows: [[1, 4], [6, 7]],
    tableHeaderRows: [[4, 6], [9, 10]],
  },
  {
    title: "Событийный фильтр",
    totalCols: 22,
    frozenRows: 6,
    rowHeights: [[0, 1, 46], [1, 2, 52], [2, 3, 22], [3, 4, 34], [4, 6, 30], [6, 7, 30]],
    serviceRows: [[1, 4], [6, 7]],
    tableHeaderRows: [[4, 6], [9, 10]],
  },
  {
    title: "Качество данных",
    totalCols: 9,
    frozenRows: 10,
    rowHeights: [[0, 1, 44], [1, 2, 38], [2, 3, 56], [3, 4, 22], [8, 10, 34]],
    serviceRows: [[1, 4]],
    tableHeaderRows: [[9, 10]],
  },
  {
    title: "Методология",
    totalCols: 6,
    frozenRows: 4,
    rowHeights: [[0, 1, 44], [1, 2, 38], [2, 3, 64], [3, 4, 22]],
    serviceRows: [[1, 4]],
  },
  {
    title: "Шаблон расходов",
    totalCols: 8,
    frozenRows: 8,
    rowHeights: [[0, 1, 44], [1, 2, 38], [2, 4, 56], [4, 5, 22], [5, 8, 34]],
    serviceRows: [[1, 5]],
    tableHeaderRows: [[7, 8]],
  },
  {
    title: "Динамика источников 2026",
    totalCols: 18,
    frozenRows: 8,
    rowHeights: [[0, 1, 46], [1, 2, 42], [2, 3, 56], [3, 4, 22], [4, 6, 30], [6, 8, 34]],
    serviceRows: [[1, 4]],
    tableHeaderRows: [[6, 8]],
  },
  {
    title: "Спам по источникам",
    totalCols: 18,
    frozenRows: 8,
    rowHeights: [[0, 1, 46], [1, 2, 42], [2, 3, 56], [3, 4, 22], [4, 6, 30], [6, 8, 34]],
    serviceRows: [[1, 4]],
    tableHeaderRows: [[6, 8]],
  },
];

const guardRequests = [];
for (const cfg of visualGuardConfigs) {
  const sheetId = sheets.get(cfg.title);
  if (!sheetId) continue;
  guardRequests.push(...visualGuardRequests(sheetId, cfg));
}
if (guardRequests.length) await batchUpdate(spreadsheetId, token, guardRequests);

console.log(JSON.stringify({
  painted: sheetsToPaint.map((sheet) => sheet.title),
  visualGuarded: visualGuardConfigs.map((cfg) => cfg.title).filter((title) => sheets.has(title)),
  cohortRows: cohortRows.length,
  sourceRows: cohortSourceRows.length,
  eventRows: eventRows.length,
  ytdDeals: wins.deal_rows.length,
  ytdServices: wins.service_rows.length,
}, null, 2));
