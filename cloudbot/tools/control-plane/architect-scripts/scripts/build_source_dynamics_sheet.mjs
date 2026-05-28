import { createSign } from "node:crypto";
import { readFile } from "node:fs/promises";

const SHEET_URL = "https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit#gid=0";
const SA_PATH = process.env.MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON || process.env.GOOGLE_SERVICE_ACCOUNT_JSON || "/Users/pro2kuror/Downloads/finance-director-sheets-903611b799c3.json";
const DATA_PATH = "/tmp/true_events_q1_2026.json";
const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SCOPE = "https://www.googleapis.com/auth/spreadsheets";
const DASHBOARD_TITLE = "Динамика источников 2026";
const HELPER_TITLE = "RAW · source_trends_2026";

const MONTHS_2026 = Array.from({ length: 12 }, (_, index) => `2026-${String(index + 1).padStart(2, "0")}`);
const MONTH_LABELS = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"];
const METRIC = "lead";
const METRIC_LABEL = "Лиды";
const COLORS = {
  page: { red: 0.965, green: 0.973, blue: 0.984 },
  white: { red: 1, green: 1, blue: 1 },
  navy: { red: 0.071, green: 0.129, blue: 0.2 },
  slate: { red: 0.31, green: 0.36, blue: 0.43 },
  header: { red: 0.91, green: 0.95, blue: 0.98 },
  growing: { red: 0.86, green: 0.95, blue: 0.89 },
  falling: { red: 0.99, green: 0.9, blue: 0.88 },
  stable: { red: 0.94, green: 0.95, blue: 0.97 },
  anomaly: { red: 1, green: 0.93, blue: 0.74 },
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

function fmtPct(value) {
  if (value == null || !Number.isFinite(value)) return "";
  return `${(value * 100).toFixed(1).replace(".", ",")}%`;
}

function sourceRows(data) {
  return Object.entries(data.event_by_source || {}).map(([key, metrics]) => {
    const [month, brand, source] = key.split("|||");
    return {
      month,
      brand,
      source: source || "Без источника",
      lead: Number(metrics.lead || 0),
      kp: Number(metrics.kp || 0),
      contract: Number(metrics.contract || 0),
      sale: Number(metrics.sale || 0),
      revenue: Number(metrics.revenue || 0),
    };
  });
}

function aggregateSources(rows) {
  const monthTotals = new Map(MONTHS_2026.map((month) => [month, 0]));
  const bySource = new Map();
  for (const row of rows) {
    if (!MONTHS_2026.includes(row.month)) continue;
    monthTotals.set(row.month, (monthTotals.get(row.month) || 0) + Number(row[METRIC] || 0));
    const bucket = bySource.get(row.source) || {
      source: row.source,
      months: Object.fromEntries(MONTHS_2026.map((month) => [month, 0])),
      lead: 0,
      kp: 0,
      contract: 0,
      sale: 0,
      revenue: 0,
      brands: new Set(),
    };
    bucket.months[row.month] += Number(row[METRIC] || 0);
    bucket.lead += row.lead;
    bucket.kp += row.kp;
    bucket.contract += row.contract;
    bucket.sale += row.sale;
    bucket.revenue += row.revenue;
    bucket.brands.add(row.brand || "Без бренда");
    bySource.set(row.source, bucket);
  }
  return { monthTotals, sources: Array.from(bySource.values()) };
}

function aggregateSourcesForBrand(rows, brand) {
  const filtered = brand ? rows.filter((row) => row.brand === brand) : rows;
  return aggregateSources(filtered);
}

function sourceStatus(values) {
  const active = values.map((value, index) => ({ value, index })).filter((item) => item.value > 0);
  if (active.length < 2) return { label: "без динамики", color: COLORS.stable, lastMom: null };
  const first = active[0].value;
  const prev = active[active.length - 2].value;
  const last = active[active.length - 1].value;
  const lastMom = prev > 0 ? (last - prev) / prev : null;
  if (lastMom != null && lastMom > 0.1) return { label: "растёт", color: COLORS.growing, lastMom };
  if (lastMom != null && lastMom < -0.1) return { label: "проседает", color: COLORS.falling, lastMom };
  const totalChange = first > 0 ? (last - first) / first : 0;
  if (totalChange > 0.25) return { label: "растёт", color: COLORS.growing, lastMom };
  if (totalChange < -0.25) return { label: "проседает", color: COLORS.falling, lastMom };
  return { label: "без динамики", color: COLORS.stable, lastMom };
}

function anomalies(values) {
  const result = [];
  for (let index = 1; index < values.length; index += 1) {
    const prev = values[index - 1];
    const current = values[index];
    if (prev > 0) {
      const delta = (current - prev) / prev;
      if (delta >= 1) result.push(`${MONTH_LABELS[index]} всплеск ${fmtPct(delta)}`);
      if (delta <= -0.7) result.push(`${MONTH_LABELS[index]} провал ${fmtPct(delta)}`);
    } else if (prev === 0 && current >= 5) {
      result.push(`${MONTH_LABELS[index]} старт с ${current}`);
    }
  }
  return result;
}

function buildExecutiveLines(rows) {
  const growing = rows.filter((row) => row.status === "растёт").sort((a, b) => b.total - a.total);
  const falling = rows.filter((row) => row.status === "проседает").sort((a, b) => b.total - a.total);
  const stable = rows.filter((row) => row.status === "без динамики").sort((a, b) => b.total - a.total);
  const anomalyRows = rows.filter((row) => row.anomalyText).sort((a, b) => b.total - a.total);
  const problemRows = rows.filter((row) => row.isProblem).sort((a, b) => b.total - a.total);
  const top = rows.slice().sort((a, b) => b.total - a.total).slice(0, 3).map((row) => `${row.source} (${row.total})`).join(", ") || "нет данных";
  return [
    `Основной объём за период дают: ${top}.`,
    growing[0] ? `Растёт: ${growing.slice(0, 3).map((row) => `${row.source} (${row.total})`).join(", ")}.` : "Растущих источников по текущему периоду нет.",
    falling[0] ? `Проседает: ${falling.slice(0, 3).map((row) => `${row.source} (${row.total})`).join(", ")}.` : "Крупных проседающих источников по текущему периоду нет.",
    anomalyRows[0] ? `Аномалии: ${anomalyRows.slice(0, 3).map((row) => `${row.source}: ${row.anomalyText}`).join("; ")}.` : "Аномальных всплесков или провалов не найдено.",
    problemRows[0] ? `Риск данных: есть немаппированные/неясные источники — ${problemRows.map((row) => `${row.source} (${row.total})`).join(", ")}.` : "Критичных проблем маппинга источников в текущем срезе нет.",
    stable[0] ? `Без выраженной динамики: ${stable.slice(0, 3).map((row) => row.source).join(", ")}.` : "",
  ].filter(Boolean);
}

function prepareSourceMetrics(rows, monthTotals) {
  return rows
    .map((row) => {
      const values = MONTHS_2026.map((month) => Number(row.months[month] || 0));
      const total = values.reduce((acc, value) => acc + value, 0);
      const status = sourceStatus(values);
      const shares = MONTHS_2026.map((month, index) => {
        const monthTotal = monthTotals.get(month) || 0;
        return monthTotal ? values[index] / monthTotal : 0;
      });
      const averageShare = shares.reduce((acc, value) => acc + value, 0) / shares.length;
      const anomalyText = anomalies(values).join("; ");
      const isProblem = ["", "Без источника", "Не выяснено"].includes(row.source);
      return {
        ...row,
        values,
        shares,
        total,
        status: status.label,
        statusColor: status.color,
        lastMom: status.lastMom,
        averageShare,
        anomalyText,
        isProblem,
      };
    })
    .sort((a, b) => b.total - a.total || a.source.localeCompare(b.source, "ru"));
}

function buildGrids(data) {
  const rows = sourceRows(data);
  const sections = [
    {
      title: "Источники · общая сводка",
      ...aggregateSourcesForBrand(rows, ""),
    },
    {
      title: "Источники · Acoola Team",
      ...aggregateSourcesForBrand(rows, "Acoola Team"),
    },
    {
      title: "Источники · Belberry",
      ...aggregateSourcesForBrand(rows, "Belberry"),
    },
  ].map((section) => ({
    ...section,
    metrics: prepareSourceMetrics(section.sources, section.monthTotals),
  }));
  const totalMetricRows = sections.reduce((acc, section) => acc + section.metrics.length + 1, 0);
  const cols = 15;
  const grid = makeGrid(Math.max(140, 12 + totalMetricRows + sections.length * 4), cols);
  const row = (() => {
    let index = 0;
    return (values = [], col = 0) => {
      putRow(grid, index, col, values);
      index += 1;
      return index - 1;
    };
  })();

  const headerRow = row(["ДИНАМИКА ИСТОЧНИКОВ 2026"]);
  row(["Метрика", METRIC_LABEL, "", "Период", "Январь-декабрь 2026", "", "Обновлено", data.meta?.updated_at || ""]);
  row(["Логика", "Источник берётся из Bitrix24 SOURCE_ID, промапленного через crm.status.list. Месяц = месяц первого входа сделки в лид-стадию в воронке продаж."]);
  row([]);
  const legendRow = row(["Легенда", "растёт", "проседает", "без динамики"]);
  row([]);

  const sectionRanges = [];
  sections.forEach((section) => {
    const titleRow = row([section.title]);
    const headerRow = row(["Источник", "Статус", ...MONTH_LABELS, "Итого"]);
    const startRow = row([]);
    section.metrics.forEach((item, index) => {
      putRow(grid, startRow + index, 0, [
        item.source,
        item.status,
        ...item.values,
        item.total,
      ]);
    });
    for (let index = 1; index < section.metrics.length; index += 1) row([]);
    const totalValues = MONTHS_2026.map((month) => Number(section.monthTotals.get(month) || 0));
    const totalRow = row(["Итого", "", ...totalValues, totalValues.reduce((acc, value) => acc + value, 0)]);
    sectionRanges.push({
      title: section.title,
      titleRow,
      headerRow,
      startRow,
      totalRow,
      endRow: totalRow + 1,
      metrics: section.metrics,
      totalValues,
    });
    row([]);
    row([]);
  });
  const helperGrid = makeGrid(1, 1);
  putRow(helperGrid, 0, 0, ["Не используется"]);

  return {
    grid,
    helperGrid,
    metrics: sections[0]?.metrics ?? [],
    sectionRanges,
    ranges: {
      headerRow,
      legendRow,
      volumeHeaderRow: sectionRanges[0]?.headerRow ?? 0,
      volumeStartRow: sectionRanges[0]?.startRow ?? 0,
      volumeEndRow: sectionRanges[0]?.endRow ?? 0,
    },
    monthTotals: sections[0]?.monthTotals ?? new Map(),
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

function buildRequests(sheetId, helperSheetId, charts, built) {
  const { ranges, metrics, grid, helperGrid, sectionRanges } = built;
  const requests = [
    { updateCells: { range: { sheetId }, fields: "userEnteredValue,userEnteredFormat,textFormatRuns,dataValidation,note" } },
    { unmergeCells: { range: { sheetId, startRowIndex: 0, endRowIndex: grid.length, startColumnIndex: 0, endColumnIndex: 18 } } },
    { updateSheetProperties: { properties: { sheetId, hidden: false, gridProperties: { frozenRowCount: ranges.volumeHeaderRow + 1, frozenColumnCount: 0, rowCount: grid.length, columnCount: grid[0].length } }, fields: "hidden,gridProperties.frozenRowCount,gridProperties.frozenColumnCount,gridProperties.rowCount,gridProperties.columnCount" } },
    { updateSheetProperties: { properties: { sheetId: helperSheetId, hidden: true, gridProperties: { rowCount: helperGrid.length, columnCount: helperGrid[0].length } }, fields: "hidden,gridProperties.rowCount,gridProperties.columnCount" } },
    styleRange(sheetId, 0, grid.length, 0, grid[0].length, { backgroundColor: COLORS.page, textFormat: { fontFamily: "Arial", fontSize: 10, foregroundColor: { red: 0.13, green: 0.16, blue: 0.22 } }, verticalAlignment: "MIDDLE", wrapStrategy: "WRAP" }),
  ];

  for (const chart of charts) requests.push({ deleteEmbeddedObject: { objectId: chart.chartId } });

  for (const rowIndex of [ranges.headerRow]) {
    requests.push({ mergeCells: { range: { sheetId, startRowIndex: rowIndex, endRowIndex: rowIndex + 1, startColumnIndex: rowIndex === ranges.headerRow ? 0 : 0, endColumnIndex: rowIndex === ranges.headerRow ? 18 : 18 }, mergeType: "MERGE_ALL" } });
  }
  requests.push({ mergeCells: { range: { sheetId, startRowIndex: 2, endRowIndex: 3, startColumnIndex: 1, endColumnIndex: 18 }, mergeType: "MERGE_ALL" } });
  for (const section of sectionRanges) {
    requests.push({ mergeCells: { range: { sheetId, startRowIndex: section.titleRow, endRowIndex: section.titleRow + 1, startColumnIndex: 0, endColumnIndex: 15 }, mergeType: "MERGE_ALL" } });
  }

  requests.push(styleRange(sheetId, ranges.headerRow, ranges.headerRow + 1, 0, 18, { backgroundColor: COLORS.navy, textFormat: { bold: true, fontSize: 16, foregroundColor: { red: 1, green: 1, blue: 1 } }, horizontalAlignment: "LEFT" }));
  requests.push(styleRange(sheetId, ranges.legendRow, ranges.legendRow + 1, 0, 5, { backgroundColor: COLORS.header, textFormat: { bold: true }, horizontalAlignment: "CENTER" }));
  requests.push(styleRange(sheetId, ranges.legendRow, ranges.legendRow + 1, 1, 2, { backgroundColor: COLORS.growing, textFormat: { bold: true }, horizontalAlignment: "CENTER" }));
  requests.push(styleRange(sheetId, ranges.legendRow, ranges.legendRow + 1, 2, 3, { backgroundColor: COLORS.falling, textFormat: { bold: true }, horizontalAlignment: "CENTER" }));
  requests.push(styleRange(sheetId, ranges.legendRow, ranges.legendRow + 1, 3, 4, { backgroundColor: COLORS.stable, textFormat: { bold: true }, horizontalAlignment: "CENTER" }));

  sectionRanges.forEach((section) => {
    requests.push(styleRange(sheetId, section.titleRow, section.titleRow + 1, 0, 15, { backgroundColor: COLORS.slate, textFormat: { bold: true, fontSize: 12, foregroundColor: { red: 1, green: 1, blue: 1 } }, horizontalAlignment: "LEFT" }));
    requests.push(styleRange(sheetId, section.headerRow, section.headerRow + 1, 0, 15, { backgroundColor: COLORS.header, textFormat: { bold: true }, horizontalAlignment: "CENTER" }));
    requests.push(styleRange(sheetId, section.startRow, section.totalRow, 0, 15, { backgroundColor: COLORS.white, horizontalAlignment: "CENTER" }));
    requests.push(styleRange(sheetId, section.totalRow, section.totalRow + 1, 0, 15, { backgroundColor: COLORS.header, textFormat: { bold: true }, horizontalAlignment: "CENTER" }));
    section.metrics.forEach((item, index) => {
      const rowIndex = section.startRow + index;
      requests.push(styleRange(sheetId, rowIndex, rowIndex + 1, 1, 2, { backgroundColor: item.statusColor, textFormat: { bold: true }, horizontalAlignment: "CENTER" }));
      if (item.isProblem) {
        requests.push(styleRange(sheetId, rowIndex, rowIndex + 1, 0, 1, { backgroundColor: COLORS.problem, textFormat: { bold: true }, horizontalAlignment: "LEFT" }));
      }
    });
  });
  [160, 110, ...Array(12).fill(78), 88].forEach((pixelSize, index) => {
    requests.push({ updateDimensionProperties: { range: { sheetId, dimension: "COLUMNS", startIndex: index, endIndex: index + 1 }, properties: { pixelSize }, fields: "pixelSize" } });
  });
  requests.push({ updateDimensionProperties: { range: { sheetId, dimension: "ROWS", startIndex: ranges.headerRow, endIndex: ranges.headerRow + 1 }, properties: { pixelSize: 44 }, fields: "pixelSize" } });

  const border = { style: "SOLID", color: { red: 0.78, green: 0.82, blue: 0.87 } };
  for (const section of sectionRanges) {
    requests.push({
      updateBorders: {
        range: { sheetId, startRowIndex: section.headerRow, endRowIndex: section.endRow, startColumnIndex: 0, endColumnIndex: 15 },
        top: border,
        bottom: border,
        left: border,
        right: border,
        innerHorizontal: { style: "SOLID", color: { red: 0.88, green: 0.9, blue: 0.93 } },
        innerVertical: { style: "SOLID", color: { red: 0.88, green: 0.9, blue: 0.93 } },
      },
    });
  }

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

const chartsMetadata = await fetchJson(
  `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}?fields=sheets(properties(title),charts(chartId))`,
  token,
);
const charts = (chartsMetadata.sheets || []).find((sheet) => sheet.properties?.title === DASHBOARD_TITLE)?.charts || [];
await batchUpdate(spreadsheetId, token, buildRequests(sheetId, helperSheetId, charts, built));
await valuesClear(spreadsheetId, token, `${quoteSheetTitle(DASHBOARD_TITLE)}!A1:R120`);
await valuesClear(spreadsheetId, token, `${quoteSheetTitle(HELPER_TITLE)}!A1:R120`);
await valuesUpdate(spreadsheetId, token, DASHBOARD_TITLE, built.grid);
await valuesUpdate(spreadsheetId, token, HELPER_TITLE, built.helperGrid);

console.log(JSON.stringify({
  sheet: DASHBOARD_TITLE,
  helper: HELPER_TITLE,
  sources: built.metrics.length,
  total: built.metrics.reduce((acc, row) => acc + row.total, 0),
  metric: METRIC,
}, null, 2));
