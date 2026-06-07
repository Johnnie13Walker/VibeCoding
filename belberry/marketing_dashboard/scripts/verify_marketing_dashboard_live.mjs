import { createSign } from "node:crypto";
import { readFile } from "node:fs/promises";
import { formatPeriodLabel, latestMonth, monthsFromCohortByBrand } from "./marketing_dashboard_period.mjs";

const SHEET_URL = "https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit#gid=0";
const SA_PATH = process.env.MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON || process.env.GOOGLE_SERVICE_ACCOUNT_JSON || "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json";
const COHORT_PATH = "/tmp/cohort_slice_3.json";
const EVENTS_PATH = "/tmp/true_events_q1_2026.json";
const WINS_PATH = "/tmp/wins_ytd_2026.json";
const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly";

const VISIBLE_TABS = [
  "CEO Dashboard",
  "Сделки",
  "Продажи YTD 2026 · сделки",
  "Продажи YTD 2026 · услуги",
  "Когортный фильтр",
  "Событийный фильтр",
  "Динамика источников 2026",
  "Спам по источникам",
  "Качество данных",
  "Методология",
  "Шаблон расходов",
];

const HIDDEN_TABS = [
  "Динамика по месяцам",
  "Источники по месяцам",
  "Acoola Team",
  "Belberry",
  "События по месяцам",
  "RAW · cohort_source",
  "RAW · event_brand",
  "RAW · event_sales",
  "RAW · source_trends_2026",
  "RAW · spam_sources_2026",
  "Без бренда",
  "RAW · ceo_charts",
];

const RANGES = [
  ["ceo", "'CEO Dashboard'!A1:N90"],
  ["cohortFilter", "'Когортный фильтр'!A1:V130"],
  ["eventFilter", "'Событийный фильтр'!A1:V130"],
  ["deals", "'Сделки'!A1:H2000"],
  ["quality", "'Качество данных'!A1:I120"],
  ["noBrand", "'Без бренда'!A1:H400"],
  ["acoola", "'Acoola Team'!A1:J20"],
  ["belberry", "'Belberry'!A1:J20"],
  ["monthly", "'Динамика по месяцам'!A1:Q40"],
  ["sources", "'Источники по месяцам'!A1:S80"],
  ["eventsMonthly", "'События по месяцам'!A1:Q40"],
  ["sourceDynamics", "'Динамика источников 2026'!A1:R220"],
  ["spamSources", "'Спам по источникам'!A1:R180"],
  ["rawSourceTrends", "'RAW · source_trends_2026'!A1:G20"],
  ["rawSpamSources", "'RAW · spam_sources_2026'!A1:H220"],
  ["winsDeals", "'Продажи YTD 2026 · сделки'!A1:P400"],
  ["winsServices", "'Продажи YTD 2026 · услуги'!A1:R400"],
  ["expenses", "'Шаблон расходов'!A1:H80"],
  ["methodology", "'Методология'!A1:F40"],
  ["rawCohortSource", "'RAW · cohort_source'!A1:I90"],
  ["rawEventBrand", "'RAW · event_brand'!A1:G20"],
  ["rawEventSales", "'RAW · event_sales'!A1:E30"],
];

const LAYOUT_EXPECTATIONS = {
  "CEO Dashboard": { visible: true, frozenRows: 3, minRowHeights: [[0, 44], [1, 36], [2, 24]] },
  "Сделки": { visible: true, frozenRows: 3, filter: { startRowIndex: 2, startColumnIndex: 0, endColumnIndex: 8 }, minRowHeights: [[0, 42], [1, 34], [2, 34]] },
  "Продажи YTD 2026 · сделки": { visible: true, frozenRows: 3, minRowHeights: [[0, 44], [1, 40], [2, 20]] },
  "Продажи YTD 2026 · услуги": { visible: true, frozenRows: 3, minRowHeights: [[0, 44], [1, 40], [2, 20]] },
  "Когортный фильтр": { visible: true, frozenRows: 6, minRowHeights: [[0, 44], [1, 50], [2, 20], [3, 32], [4, 28], [5, 28]] },
  "Событийный фильтр": { visible: true, frozenRows: 6, minRowHeights: [[0, 44], [1, 50], [2, 20], [3, 32], [4, 28], [5, 28]] },
  "Динамика источников 2026": { visible: true, frozenRows: 8, minRowHeights: [[0, 44], [1, 40], [2, 54], [3, 20], [4, 28], [5, 28], [6, 32]] },
  "Спам по источникам": { visible: true, frozenRows: 8, minRowHeights: [[0, 44], [1, 40], [2, 54], [3, 20], [4, 28], [5, 28], [6, 32]] },
  "Качество данных": { visible: true, frozenRows: 10, minRowHeights: [[0, 42], [1, 36], [2, 54], [3, 20], [8, 32], [9, 32]] },
  "Методология": { visible: true, frozenRows: 4, minRowHeights: [[0, 42], [1, 36], [2, 62], [3, 20]] },
  "Шаблон расходов": { visible: true, frozenRows: 8, minRowHeights: [[0, 42], [1, 36], [2, 54], [3, 54], [4, 20], [5, 32], [6, 32], [7, 32]] },
};

function base64url(input) {
  return Buffer.from(input).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function extractSheetId(url) {
  const match = String(url || "").match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
  return match ? match[1] : "";
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

async function fetchJson(url, token) {
  const res = await fetch(url, { headers: { authorization: `Bearer ${token}` } });
  const payload = await res.json();
  if (!res.ok) throw new Error(`Sheets API error: ${res.status} ${JSON.stringify(payload)}`);
  return payload;
}

async function fetchLayoutMetadata(spreadsheetId, token) {
  const params = new URLSearchParams({
    includeGridData: "true",
    fields: "sheets(properties(title,hidden,gridProperties(rowCount,columnCount,frozenRowCount,frozenColumnCount)),basicFilter,data(rowMetadata(hiddenByUser,pixelSize),columnMetadata(hiddenByUser,pixelSize)))",
  });
  return fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}?${params}`, token);
}

async function batchGetValues(spreadsheetId, token) {
  const params = new URLSearchParams({
    valueRenderOption: "UNFORMATTED_VALUE",
    dateTimeRenderOption: "FORMATTED_STRING",
  });
  for (const [, range] of RANGES) params.append("ranges", range);
  const payload = await fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values:batchGet?${params}`, token);
  return new Map(RANGES.map(([name], index) => [name, payload.valueRanges?.[index]?.values || []]));
}

function asNumber(value) {
  if (typeof value === "number") return value;
  const text = String(value ?? "")
    .replace(/\u00a0/g, "")
    .replace(/\s/g, "")
    .replace(/₽|%/g, "")
    .replace(",", ".")
    .replace(/[^\d.-]/g, "");
  return text ? Number(text) : 0;
}

function cell(grid, row1, col1) {
  return grid[row1 - 1]?.[col1 - 1] ?? "";
}

function countRowsWithValue(grid, startRow1, col1) {
  return grid.slice(startRow1 - 1).filter((row) => String(row[col1 - 1] ?? "").trim()).length;
}

function countRowsUntilBlank(grid, startRow1, col1) {
  let count = 0;
  for (const row of grid.slice(startRow1 - 1)) {
    if (!String(row[col1 - 1] ?? "").trim()) break;
    count += 1;
  }
  return count;
}

function countSourceRowsUntilTotal(grid, startRow1, col1) {
  let count = 0;
  for (const row of grid.slice(startRow1 - 1)) {
    const value = String(row[col1 - 1] ?? "").trim();
    if (!value || value === "Итого") break;
    count += 1;
  }
  return count;
}

function sumSheetRows(grid, startRow1, columns) {
  return grid.slice(startRow1 - 1).reduce((acc, row) => {
    for (const [name, col1] of Object.entries(columns)) acc[name] += asNumber(row[col1 - 1]);
    return acc;
  }, Object.fromEntries(Object.keys(columns).map((name) => [name, 0])));
}

function sumSheetRowsRange(grid, startRow1, endRow1, columns) {
  return grid.slice(startRow1 - 1, endRow1).reduce((acc, row) => {
    for (const [name, col1] of Object.entries(columns)) acc[name] += asNumber(row[col1 - 1]);
    return acc;
  }, Object.fromEntries(Object.keys(columns).map((name) => [name, 0])));
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

function sumEventRows(rows) {
  return rows.reduce((acc, row) => {
    acc.lead += Number(row.lead || 0);
    acc.kp += Number(row.kp || 0);
    acc.contract += Number(row.contract || 0);
    acc.sale += Number(row.sale || 0);
    acc.revenue += Number(row.revenue || 0);
    return acc;
  }, { lead: 0, kp: 0, contract: 0, sale: 0, revenue: 0 });
}

function addMetrics(target, row) {
  target.obr += Number(row.obr || 0);
  target.lead += Number(row.lead || 0);
  target.kp += Number(row.kp || 0);
  target.contract += Number(row.contract || 0);
  target.sale += Number(row.sale || 0);
  target.revenue += Number(row.revenue || 0);
}

function cohortSourceRows(cohort) {
  return Object.entries(cohort.cohort_by_source || {}).map(([key, metrics]) => {
    const [month, brand, source] = key.split("|||");
    return { month, brand, source, ...metrics };
  });
}

function eventSourceRows(events) {
  return Object.entries(events.event_by_source || {}).map(([key, metrics]) => {
    const [month, brand, source] = key.split("|||");
    return { month, brand, source, ...metrics };
  });
}

function cohortBrandRows(cohort) {
  return Object.entries(cohort.cohort_by_brand || {}).map(([key, metrics]) => {
    const [month, brand] = key.split("|||");
    return { month, brand, ...metrics };
  });
}

function eventTotalsByBrand(events) {
  const map = new Map();
  for (const row of events.event_rows || []) {
    const bucket = map.get(row.brand) || { lead: 0, kp: 0, contract: 0, sale: 0, revenue: 0 };
    bucket.lead += Number(row.lead || 0);
    bucket.kp += Number(row.kp || 0);
    bucket.contract += Number(row.contract || 0);
    bucket.sale += Number(row.sale || 0);
    bucket.revenue += Number(row.revenue || 0);
    map.set(row.brand, bucket);
  }
  return map;
}

function buildQualitySummary(cohort, wins) {
  const detailRows = cohort.detail_rows || [];
  const detailById = new Map(detailRows.map((row) => [String(row.id), row]));
  const issueMap = new Map();
  const ensureIssue = (row) => {
    const id = String(row.id || row.deal_id);
    if (!issueMap.has(id)) {
      const detail = detailById.get(id) || {};
      issueMap.set(id, {
        id,
        brand: detail.brand || row.brand || "",
        source: detail.source || row.source || "",
        problems: new Set(),
        severity: 2,
      });
    }
    return issueMap.get(id);
  };

  for (const row of detailRows) {
    const issue = ensureIssue(row);
    const brand = String(row.brand || "").trim();
    const source = String(row.source || "").trim();
    if (!brand || brand === "Без бренда") {
      issue.severity = 1;
      issue.problems.add("Без бренда");
    }
    if (!source || source === "Без источника") {
      issue.severity = 1;
      issue.problems.add("Без источника");
    }
    if (source === "Не выяснено") issue.problems.add("Не выяснено");
    if ((row.kp && !row.lead) || (row.contract && !row.kp) || (row.sale && !row.contract)) {
      issue.problems.add("Аномалия стадий");
    }
  }

  for (const row of wins.deal_rows || []) {
    const brand = String(row.brand || "").trim();
    const source = String(row.source || "").trim();
    if (source === "Не выяснено" || source === "Без источника" || !source || !brand || brand === "Без бренда") {
      const issue = ensureIssue({ ...row, id: row.deal_id });
      issue.severity = 1;
      issue.problems.add("Продажа с проблемной атрибуцией");
    }
  }

  const rows = Array.from(issueMap.values()).filter((row) => row.problems.size);
  return {
    noSource: rows.filter((row) => row.problems.has("Без источника")).length,
    unclear: rows.filter((row) => row.problems.has("Не выяснено")).length,
    noBrand: rows.filter((row) => row.problems.has("Без бренда")).length,
    stage: rows.filter((row) => row.problems.has("Аномалия стадий")).length,
    wonAttr: rows.filter((row) => row.problems.has("Продажа с проблемной атрибуцией")).length,
    total: rows.length,
  };
}

function expectedCohortTotals(cohort) {
  const totals = { obr: 0, lead: 0, kp: 0, contract: 0, sale: 0, revenue: 0 };
  for (const metrics of Object.values(cohort.dashboard_by_brand || {})) addMetrics(totals, metrics);
  return totals;
}

function brandCohort(cohort, brand) {
  return cohort.dashboard_by_brand?.[brand] || { obr: 0, lead: 0, kp: 0, contract: 0, sale: 0, revenue: 0 };
}

function brandMonthTotals(cohort, brand) {
  return sumRows(cohortBrandRows(cohort).filter((row) => row.brand === brand));
}

function comparable(value) {
  return Math.round(asNumber(value) * 100) / 100;
}

const checks = [];
function expectEqual(label, actual, expected) {
  const ok = comparable(actual) === comparable(expected);
  checks.push({ ok, label, actual: comparable(actual), expected: comparable(expected) });
}

function expectAtMost(label, actual, expectedMax) {
  const ok = comparable(actual) <= comparable(expectedMax);
  checks.push({ ok, label, actual: comparable(actual), expected: `<= ${comparable(expectedMax)}` });
}

function expectGreater(label, actual, expectedMin) {
  const ok = comparable(actual) > comparable(expectedMin);
  checks.push({ ok, label, actual: comparable(actual), expected: `> ${comparable(expectedMin)}` });
}

function expectAtLeast(label, actual, expectedMin) {
  const ok = comparable(actual) >= comparable(expectedMin);
  checks.push({ ok, label, actual: comparable(actual), expected: `>= ${comparable(expectedMin)}` });
}

function expectText(label, actual, expected) {
  const ok = String(actual ?? "").trim() === expected;
  checks.push({ ok, label, actual: String(actual ?? "").trim(), expected });
}

function expectIncludes(label, actual, expected) {
  const ok = String(actual ?? "").includes(expected);
  checks.push({ ok, label, actual: String(actual ?? ""), expected });
}

function expectNotIncludes(label, actual, unexpected) {
  const ok = !String(actual ?? "").includes(unexpected);
  checks.push({ ok, label, actual: String(actual ?? ""), expected: `не содержит ${unexpected}` });
}

function expectRuDate(label, value) {
  const text = String(value ?? "").trim();
  const ok = /^\d{2}\.\d{2}\.\d{4}$/.test(text);
  checks.push({ ok, label, actual: text, expected: "ДД.ММ.ГГГГ" });
}

function expectNoIsoDateTime(label, valuesToCheck) {
  const bad = valuesToCheck.map((value) => String(value ?? "")).filter((value) => /\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}/.test(value));
  checks.push({ ok: bad.length === 0, label, actual: bad.slice(0, 5).join("; "), expected: "без YYYY-MM-DD HH:MM" });
}

function expectLayoutEqual(label, actual, expected) {
  const ok = actual === expected;
  checks.push({ ok, label, actual, expected });
}

function isManagerName(value) {
  const parts = String(value ?? "").trim().split(/\s+/).filter(Boolean);
  return parts.length === 2 && !parts.some((part) => part === "—" || /^\d+$/.test(part));
}

function expectManagerFormat(label, value) {
  checks.push({ ok: isManagerName(value), label, actual: String(value ?? "").trim(), expected: "Фамилия Имя" });
}

function hasNumericId(value) {
  return /^\d+$/.test(String(value ?? "").trim());
}

function checkMetricBlock(prefix, grid, row1, startCol1, expected, fields, step = 1) {
  fields.forEach((field, index) => {
    expectEqual(`${prefix}: ${field}`, cell(grid, row1, startCol1 + index * step), expected[field]);
  });
}

function findRowByFirstCell(grid, label) {
  const index = (grid || []).findIndex((row) => String(row?.[0] ?? "").trim() === label);
  return index >= 0 ? index + 1 : 0;
}

function checkMetricRow(prefix, grid, label, expected, fields, startCol1 = 2) {
  const row1 = findRowByFirstCell(grid, label);
  expectEqual(`${prefix}: строка найдена`, row1 > 0 ? 1 : 0, 1);
  if (row1 > 0) checkMetricBlock(prefix, grid, row1, startCol1, expected, fields);
}

function sourceTotalsBySource(rows) {
  const map = new Map();
  for (const row of rows) {
    const source = String(row.source || "Без источника").trim() || "Без источника";
    const bucket = map.get(source) || { source, obr: 0 };
    bucket.obr += Number(row.obr || 0);
    map.set(source, bucket);
  }
  return Array.from(map.values()).sort((a, b) => b.obr - a.obr || a.source.localeCompare(b.source, "ru"));
}

function cohortSourceTotalsBySource(rows, brand = "") {
  const map = new Map();
  for (const row of rows) {
    if (brand && row.brand !== brand) continue;
    const source = String(row.source || "Без источника").trim() || "Без источника";
    const bucket = map.get(source) || { source, obr: 0, lead: 0 };
    bucket.obr += Number(row.obr || 0);
    bucket.lead += Number(row.lead || 0);
    map.set(source, bucket);
  }
  return Array.from(map.values()).sort((a, b) => b.obr - a.obr || b.lead - a.lead || a.source.localeCompare(b.source, "ru"));
}

function eventSourceTotalsBySource(rows, brand = "") {
  const map = new Map();
  for (const row of rows) {
    if (brand && row.brand !== brand) continue;
    const source = String(row.source || "Без источника").trim() || "Без источника";
    const bucket = map.get(source) || { source, lead: 0 };
    bucket.lead += Number(row.lead || 0);
    map.set(source, bucket);
  }
  return Array.from(map.values()).sort((a, b) => b.lead - a.lead || a.source.localeCompare(b.source, "ru"));
}

function eventSalesTotalsBySource(rows, brand = "") {
  const map = new Map();
  for (const row of rows) {
    if (brand && row.brand !== brand) continue;
    const source = String(row.source || "Без источника").trim() || "Без источника";
    const bucket = map.get(source) || { source, sale: 0, revenue: 0 };
    bucket.sale += Number(row.sale || row.count || 1);
    bucket.revenue += Number(row.revenue ?? row.amount ?? 0);
    map.set(source, bucket);
  }
  return Array.from(map.values()).sort((a, b) => b.sale - a.sale || b.revenue - a.revenue || a.source.localeCompare(b.source, "ru"));
}

function eventLeadMonthTotals(rows, brand = "") {
  const totals = Object.fromEntries(Array.from({ length: 12 }, (_, index) => [`2026-${String(index + 1).padStart(2, "0")}`, 0]));
  for (const row of rows) {
    if (brand && row.brand !== brand) continue;
    if (Object.prototype.hasOwnProperty.call(totals, row.month)) totals[row.month] += Number(row.lead || 0);
  }
  return totals;
}

function spamSourceTotalsBySource(rows, brand = "") {
  const map = new Map();
  for (const row of rows) {
    if (brand && row.brand !== brand) continue;
    const source = String(row.source || "Без источника").trim() || "Без источника";
    const bucket = map.get(source) || { source, spam: 0 };
    bucket.spam += 1;
    map.set(source, bucket);
  }
  return Array.from(map.values()).sort((a, b) => b.spam - a.spam || a.source.localeCompare(b.source, "ru"));
}

function spamMonthTotals(rows, brand = "") {
  const totals = Object.fromEntries(Array.from({ length: 12 }, (_, index) => [`2026-${String(index + 1).padStart(2, "0")}`, 0]));
  for (const row of rows) {
    if (brand && row.brand !== brand) continue;
    if (Object.prototype.hasOwnProperty.call(totals, row.month)) totals[row.month] += 1;
  }
  return totals;
}

function checkSourceDynamicsTotal(prefix, grid, title, expectedMonthTotals) {
  const titleRow = findRowByFirstCell(grid, title);
  expectEqual(`${prefix} / блок найден`, titleRow > 0 ? 1 : 0, 1);
  if (titleRow <= 0) return;
  const headerRow = titleRow + 1;
  const startRow = titleRow + 2;
  const sourceCount = countSourceRowsUntilTotal(grid, startRow, 1);
  const totalRow = startRow + sourceCount;
  expectText(`${prefix} / строка итого`, cell(grid, totalRow, 1), "Итого");
  const monthKeys = Array.from({ length: 12 }, (_, index) => `2026-${String(index + 1).padStart(2, "0")}`);
  monthKeys.forEach((month, index) => {
    expectEqual(`${prefix} / итог ${month}`, cell(grid, totalRow, 3 + index), expectedMonthTotals[month]);
  });
  expectEqual(`${prefix} / итог год`, cell(grid, totalRow, 15), monthKeys.reduce((acc, month) => acc + Number(expectedMonthTotals[month] || 0), 0));
  expectText(`${prefix} / колонка итого`, cell(grid, headerRow, 15), "Итого");
}

function checkSourceSectionLayout(prefix, grid, title, expectedSources) {
  const titleRow = findRowByFirstCell(grid, title);
  expectEqual(`${prefix} / блок найден`, titleRow > 0 ? 1 : 0, 1);
  if (titleRow <= 0) return 0;
  expectText(`${prefix} / заголовок источника`, cell(grid, titleRow + 1, 1), "Источник");
  const rowCount = countRowsUntilBlank(grid, titleRow + 2, 1);
  expectEqual(`${prefix} / строк источников`, rowCount, Math.max(1, expectedSources.length));
  if (expectedSources.length) {
    expectText(`${prefix} / первый источник`, cell(grid, titleRow + 2, 1), expectedSources[0].source);
  }
  return titleRow;
}

function monthTotals2026(rows) {
  const totals = Object.fromEntries(Array.from({ length: 12 }, (_, index) => [`2026-${String(index + 1).padStart(2, "0")}`, 0]));
  for (const row of rows) {
    if (Object.prototype.hasOwnProperty.call(totals, row.month)) totals[row.month] += Number(row.obr || 0);
  }
  return totals;
}

const spreadsheetId = extractSheetId(SHEET_URL);
const [sa, cohort, events, wins] = await Promise.all([
  loadJson(SA_PATH),
  loadJson(COHORT_PATH),
  loadJson(EVENTS_PATH),
  loadJson(WINS_PATH),
]);

const cohortTotals = expectedCohortTotals(cohort);
const spamFilter = cohort.meta?.spam_filter || {};
const telemarketingOverride = cohort.meta?.telemarketing_source_override || {};
const acoola = brandCohort(cohort, "Acoola Team");
const belberry = brandCohort(cohort, "Belberry");
const cohortMonths = monthsFromCohortByBrand(cohort.cohort_by_brand || {});
const expectedPeriodLabel = formatPeriodLabel(cohortMonths);
const expectedLatestMonth = latestMonth(cohortMonths);
const noBrandRows = (cohort.detail_rows || []).filter((row) => !row.brand || row.brand === "Без бренда");
const sourceRows = cohortSourceRows(cohort);
const sourceRowsWithoutNoBrand = sourceRows.filter((row) => row.brand !== "Без бренда");
const sourceTotals = sourceTotalsBySource(sourceRows);
const cohortSourceTotals = cohortSourceTotalsBySource(sourceRows);
const acoolaCohortSourceTotals = cohortSourceTotalsBySource(sourceRows, "Acoola Team");
const belberryCohortSourceTotals = cohortSourceTotalsBySource(sourceRows, "Belberry");
const eventSourceRowsForDynamics = eventSourceRows(events);
const eventSourceTotals = eventSourceTotalsBySource(eventSourceRowsForDynamics);
const acoolaEventSourceTotals = eventSourceTotalsBySource(eventSourceRowsForDynamics, "Acoola Team");
const belberryEventSourceTotals = eventSourceTotalsBySource(eventSourceRowsForDynamics, "Belberry");
const eventSalesRows = events.sales_rows || [];
const eventSalesSourceTotals = eventSalesTotalsBySource(eventSalesRows);
const acoolaEventSalesSourceTotals = eventSalesTotalsBySource(eventSalesRows, "Acoola Team");
const belberryEventSalesSourceTotals = eventSalesTotalsBySource(eventSalesRows, "Belberry");
const eventLeadTotals = eventLeadMonthTotals(eventSourceRowsForDynamics);
const acoolaEventLeadTotals = eventLeadMonthTotals(eventSourceRowsForDynamics, "Acoola Team");
const belberryEventLeadTotals = eventLeadMonthTotals(eventSourceRowsForDynamics, "Belberry");
const spamSourceRows = cohort.spam_source_rows || [];
const spamSourceTotals = spamSourceTotalsBySource(spamSourceRows);
const acoolaSpamSourceTotals = spamSourceTotalsBySource(spamSourceRows, "Acoola Team");
const belberrySpamSourceTotals = spamSourceTotalsBySource(spamSourceRows, "Belberry");
const spamMonthTotalValues = spamMonthTotals(spamSourceRows);
const acoolaSpamMonthTotals = spamMonthTotals(spamSourceRows, "Acoola Team");
const belberrySpamMonthTotals = spamMonthTotals(spamSourceRows, "Belberry");
const eventTotals = sumEventRows(events.event_rows || []);
const eventByBrand = eventTotalsByBrand(events);
const qualitySummary = buildQualitySummary(cohort, wins);
const dealRows = wins.deal_rows || [];
const serviceRows = wins.service_rows || [];
const spamDealIds = new Set((spamFilter.spam_deal_ids || []).map((value) => String(value)));

const token = await fetchAccessToken(sa);
const metadata = await fetchJson(
  `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}?fields=sheets(properties(title,hidden),basicFilter)`,
  token,
);
const layoutMetadata = await fetchLayoutMetadata(spreadsheetId, token);
const actualTabs = new Map((metadata.sheets || []).map((sheet) => [sheet.properties.title, Boolean(sheet.properties.hidden)]));
const sheetMeta = new Map((metadata.sheets || []).map((sheet) => [sheet.properties.title, sheet]));
const layoutByTitle = new Map((layoutMetadata.sheets || []).map((sheet) => [sheet.properties.title, sheet]));
const values = await batchGetValues(spreadsheetId, token);

for (const title of VISIBLE_TABS) expectEqual(`вкладка видима: ${title}`, actualTabs.get(title) === false ? 1 : 0, 1);
for (const title of HIDDEN_TABS) expectEqual(`вкладка скрыта: ${title}`, actualTabs.get(title) === true ? 1 : 0, 1);

expectText("Спам-фильтр / поле причины отказа", spamFilter.rejection_reason_field, "UF_CRM_1771495464");
expectEqual("Спам-фильтр / найденные sales-кандидаты", spamFilter.spam_deals_found, spamDealIds.size);
expectEqual("Спам-фильтр / строки для вкладки по источникам", spamSourceRows.length, spamFilter.spam_deals_found);
expectEqual("Спам-фильтр / created не исключает обращения", Number(spamFilter.created_deals_before || 0) - Number(spamFilter.created_deals_after || 0), 0);
expectEqual("Спам-фильтр / sales-only не исключает обращения", Number(spamFilter.sales_only_created_before || 0) - Number(spamFilter.sales_only_created_after || 0), 0);
expectEqual("Спам-фильтр / event candidates не исключает обращения", Number(spamFilter.event_candidates_before || 0) - Number(spamFilter.event_candidates_after || 0), 0);
expectEqual("Спам-фильтр / cohort leads delta", Number(spamFilter.cohort_leads_before || 0) - Number(spamFilter.cohort_leads_after || 0), spamFilter.cohort_leads_excluded);
expectEqual("Спам-фильтр / event leads delta", Number(spamFilter.event_leads_before || 0) - Number(spamFilter.event_leads_after || 0), spamFilter.event_leads_excluded);
const spamCohortIds = new Set((cohort.detail_rows || []).filter((row) => spamDealIds.has(String(row.id))).map((row) => String(row.id)));
expectEqual("Спам-фильтр / spam ids остаются обращениями", spamCohortIds.size, (cohort.detail_rows || []).filter((row) => spamDealIds.has(String(row.id))).length);
expectEqual("Спам-фильтр / spam ids отсутствуют в продажах", dealRows.filter((row) => spamDealIds.has(String(row.deal_id))).length, 0);
expectNoIsoDateTime("Формат дат / сделки без времени", (cohort.detail_rows || []).map((row) => row.created_at));
expectNoIsoDateTime("Формат дат / продажи без времени", [...dealRows.map((row) => row.won_at), ...serviceRows.map((row) => row.won_at)]);
expectNoIsoDateTime("Формат дат / спам без времени", spamSourceRows.map((row) => row.created_at));
if ((cohort.detail_rows || []).length) expectRuDate("Формат дат / первая дата обращения", cohort.detail_rows[0].created_at);
if (dealRows.length) expectRuDate("Формат дат / первая дата УСПЕХ", dealRows[0].won_at);
if (spamSourceRows.length) expectRuDate("Формат дат / первая дата спама", spamSourceRows[0].created_at);

for (const [title, expected] of Object.entries(LAYOUT_EXPECTATIONS)) {
  const sheet = layoutByTitle.get(title);
  expectLayoutEqual(`${title} / layout: вкладка существует`, sheet ? 1 : 0, 1);
  if (!sheet) continue;
  const props = sheet.properties || {};
  const grid = props.gridProperties || {};
  const basicFilter = sheet.basicFilter?.range || null;
  const rowMetadata = sheet.data?.[0]?.rowMetadata || [];
  const hiddenRows = rowMetadata.filter((row) => row?.hiddenByUser).length;
  const hiddenCols = (sheet.data?.[0]?.columnMetadata || []).filter((col) => col?.hiddenByUser).length;
  expectLayoutEqual(`${title} / layout: видимость`, Boolean(props.hidden), expected.visible ? false : true);
  expectLayoutEqual(`${title} / layout: frozen rows`, Number(grid.frozenRowCount || 0), expected.frozenRows);
  expectLayoutEqual(`${title} / layout: hidden rows`, hiddenRows, 0);
  expectLayoutEqual(`${title} / layout: hidden columns`, hiddenCols, 0);
  for (const [rowIndex, minPixelSize] of expected.minRowHeights || []) {
    expectAtLeast(`${title} / layout: высота строки ${rowIndex + 1}`, Number(rowMetadata[rowIndex]?.pixelSize || 0), minPixelSize);
  }
  if (expected.filter) {
    expectLayoutEqual(`${title} / layout: filter start row`, Number(basicFilter?.startRowIndex ?? -1), expected.filter.startRowIndex);
    expectLayoutEqual(`${title} / layout: filter start col`, Number(basicFilter?.startColumnIndex ?? -1), expected.filter.startColumnIndex);
    expectLayoutEqual(`${title} / layout: filter end col`, Number(basicFilter?.endColumnIndex ?? -1), expected.filter.endColumnIndex);
  } else {
    expectLayoutEqual(`${title} / layout: без лишнего basic filter`, basicFilter ? 1 : 0, 0);
  }
}

const ceo = values.get("ceo");
expectIncludes("CEO Dashboard: период", cell(ceo, 2, 2), expectedPeriodLabel);
checkMetricBlock("CEO Dashboard / когорта", ceo, 7, 1, cohortTotals, ["obr", "lead", "kp", "contract", "sale", "revenue"], 2);
checkMetricBlock("CEO Dashboard / событийный слой", ceo, 13, 1, eventTotals, ["lead", "kp", "contract", "sale", "revenue"], 2);
expectEqual("CEO Dashboard / без бренда", cell(ceo, 9, 11), noBrandRows.length);
checkMetricRow("CEO Dashboard / Acoola", ceo, "Acoola Team", acoola, ["obr", "lead", "kp", "contract", "sale", "revenue"]);
checkMetricRow("CEO Dashboard / Belberry", ceo, "Belberry", belberry, ["obr", "lead", "kp", "contract", "sale", "revenue"]);
checkMetricRow("CEO Dashboard / Итого бренды", ceo, "Итого", cohortTotals, ["obr", "lead", "kp", "contract", "sale", "revenue"]);

const cohortFilter = values.get("cohortFilter");
const cohortSelectorMonthCol = (cohortFilter[4] || []).findIndex((value) => String(value ?? "").trim() === expectedLatestMonth) + 1;
expectEqual("Когортный фильтр / последний месяц есть в селекторе", cohortSelectorMonthCol > 0 ? 1 : 0, 1);
if (cohortSelectorMonthCol > 0) expectEqual("Когортный фильтр / последний месяц включён", cell(cohortFilter, 6, cohortSelectorMonthCol) === true ? 1 : 0, 1);
checkMetricBlock("Когортный фильтр / общая сводка", cohortFilter, 11, 1, cohortTotals, ["obr", "lead", "kp", "contract", "sale", "revenue"]);
checkMetricBlock("Когортный фильтр / Acoola", cohortFilter, 11, 8, acoola, ["obr", "lead", "kp", "contract", "sale", "revenue"]);
checkMetricBlock("Когортный фильтр / Belberry", cohortFilter, 11, 15, belberry, ["obr", "lead", "kp", "contract", "sale", "revenue"]);
const cohortOverallSourceRow = checkSourceSectionLayout("Когортный фильтр / источники общая сводка", cohortFilter, "Источники · общая сводка", cohortSourceTotals);
const cohortAcoolaSourceRow = checkSourceSectionLayout("Когортный фильтр / источники Acoola", cohortFilter, "Источники · Acoola Team", acoolaCohortSourceTotals);
const cohortBelberrySourceRow = checkSourceSectionLayout("Когортный фильтр / источники Belberry", cohortFilter, "Источники · Belberry", belberryCohortSourceTotals);
if (cohortOverallSourceRow && cohortAcoolaSourceRow) expectGreater("Когортный фильтр / Acoola ниже общей сводки", cohortAcoolaSourceRow, cohortOverallSourceRow);
if (cohortAcoolaSourceRow && cohortBelberrySourceRow) expectGreater("Когортный фильтр / Belberry ниже Acoola", cohortBelberrySourceRow, cohortAcoolaSourceRow);

const eventFilter = values.get("eventFilter");
const acoolaEvents = eventByBrand.get("Acoola Team") || {};
const belberryEvents = eventByBrand.get("Belberry") || {};
const eventSelectorMonthCol = (eventFilter[4] || []).findIndex((value) => String(value ?? "").trim() === expectedLatestMonth) + 1;
expectEqual("Событийный фильтр / последний месяц есть в селекторе", eventSelectorMonthCol > 0 ? 1 : 0, 1);
if (eventSelectorMonthCol > 0) expectEqual("Событийный фильтр / последний месяц включён", cell(eventFilter, 6, eventSelectorMonthCol) === true ? 1 : 0, 1);
checkMetricBlock("Событийный фильтр / общая сводка", eventFilter, 11, 1, eventTotals, ["lead", "kp", "contract", "sale", "revenue"]);
checkMetricBlock("Событийный фильтр / Acoola", eventFilter, 11, 8, acoolaEvents, ["lead", "kp", "contract", "sale", "revenue"]);
checkMetricBlock("Событийный фильтр / Belberry", eventFilter, 11, 15, belberryEvents, ["lead", "kp", "contract", "sale", "revenue"]);
const eventOverallSourceRow = checkSourceSectionLayout("Событийный фильтр / продажи по источникам общая сводка", eventFilter, "Продажи по источникам · общая сводка", eventSalesSourceTotals);
const eventAcoolaSourceRow = checkSourceSectionLayout("Событийный фильтр / продажи по источникам Acoola", eventFilter, "Продажи по источникам · Acoola Team", acoolaEventSalesSourceTotals);
const eventBelberrySourceRow = checkSourceSectionLayout("Событийный фильтр / продажи по источникам Belberry", eventFilter, "Продажи по источникам · Belberry", belberryEventSalesSourceTotals);
if (eventOverallSourceRow && eventAcoolaSourceRow) expectGreater("Событийный фильтр / Acoola ниже общей сводки", eventAcoolaSourceRow, eventOverallSourceRow);
if (eventAcoolaSourceRow && eventBelberrySourceRow) expectGreater("Событийный фильтр / Belberry ниже Acoola", eventBelberrySourceRow, eventAcoolaSourceRow);

expectEqual("Сделки / строк", countRowsWithValue(values.get("deals"), 4, 3), cohort.detail_rows.length);
expectEqual("Без бренда / строк", countRowsWithValue(values.get("noBrand"), 4, 3), noBrandRows.length);
for (const [index, row] of values.get("deals").slice(3).entries()) {
  if (!String(row[2] ?? "").trim()) continue;
  expectManagerFormat(`Сделки / менеджер / строка ${index + 4}`, row[5]);
}
for (const [index, row] of values.get("noBrand").slice(3).entries()) {
  if (!String(row[2] ?? "").trim()) continue;
  expectManagerFormat(`Без бренда / менеджер / строка ${index + 4}`, row[5]);
}
const dealsFilter = sheetMeta.get("Сделки")?.basicFilter?.range || {};
expectEqual("Сделки / фильтр начинается со строки заголовков", Number(dealsFilter.startRowIndex ?? -1), 2);
expectEqual("Сделки / фильтр захватывает 8 колонок", Number(dealsFilter.endColumnIndex ?? -1), 8);

checkMetricBlock("Acoola Team hidden / итог", values.get("acoola"), 4, 2, brandMonthTotals(cohort, "Acoola Team"), ["obr", "lead", "kp", "contract", "sale"], 2);
expectEqual("Acoola Team hidden / выручка", cell(values.get("acoola"), 5, 2), acoola.revenue);
checkMetricBlock("Belberry hidden / итог", values.get("belberry"), 4, 2, brandMonthTotals(cohort, "Belberry"), ["obr", "lead", "kp", "contract", "sale"], 2);
expectEqual("Belberry hidden / выручка", cell(values.get("belberry"), 5, 2), belberry.revenue);

const monthly = values.get("monthly");
expectEqual("Динамика по месяцам / обращения всего", cell(monthly, 6, 5), cohortTotals.obr);
expectEqual("Динамика по месяцам / лиды всего", cell(monthly, 7, 5), cohortTotals.lead);
expectEqual("Динамика по месяцам / КП всего", cell(monthly, 8, 5), cohortTotals.kp);
expectEqual("Динамика по месяцам / договоры всего", cell(monthly, 9, 5), cohortTotals.contract);
expectEqual("Динамика по месяцам / продажи всего", cell(monthly, 10, 5), cohortTotals.sale);
expectEqual("Динамика по месяцам / выручка всего", cell(monthly, 11, 5), cohortTotals.revenue);

const sources = values.get("sources");
expectEqual("Источники по месяцам / обращения всего", cell(sources, 6, 5), cohortTotals.obr);
expectEqual("Источники по месяцам / лиды всего", cell(sources, 7, 5), cohortTotals.lead);
expectEqual("Источники по месяцам / КП всего", cell(sources, 8, 5), cohortTotals.kp);
expectEqual("Источники по месяцам / договоры всего", cell(sources, 9, 5), cohortTotals.contract);
expectEqual("Источники по месяцам / продажи всего", cell(sources, 10, 5), cohortTotals.sale);
expectEqual("Источники по месяцам / выручка всего", cell(sources, 11, 5), cohortTotals.revenue);

const sourceDynamics = values.get("sourceDynamics");
expectIncludes("Динамика источников 2026 / заголовок", cell(sourceDynamics, 1, 1), "ДИНАМИКА ИСТОЧНИКОВ 2026");
expectText("Динамика источников 2026 / метрика", cell(sourceDynamics, 2, 2), "Лиды");
expectIncludes("Динамика источников 2026 / логика событийная", cell(sourceDynamics, 3, 2), "первая встреча проведена");
expectIncludes("Динамика источников 2026 / исключение нет связи", cell(sourceDynamics, 3, 2), "Вход: нет связи");
expectIncludes("Динамика источников 2026 / телемаркетинг override", cell(sourceDynamics, 3, 2), "отдела телемаркетинга");
expectEqual("Динамика источников 2026 / есть общая сводка", findRowByFirstCell(sourceDynamics, "Источники · общая сводка") > 0 ? 1 : 0, 1);
expectEqual("Динамика источников 2026 / есть Acoola Team", findRowByFirstCell(sourceDynamics, "Источники · Acoola Team") > 0 ? 1 : 0, 1);
expectEqual("Динамика источников 2026 / есть Belberry", findRowByFirstCell(sourceDynamics, "Источники · Belberry") > 0 ? 1 : 0, 1);
checkSourceDynamicsTotal("Динамика источников 2026 / общая сводка", sourceDynamics, "Источники · общая сводка", eventLeadTotals);
checkSourceDynamicsTotal("Динамика источников 2026 / Acoola Team", sourceDynamics, "Источники · Acoola Team", acoolaEventLeadTotals);
checkSourceDynamicsTotal("Динамика источников 2026 / Belberry", sourceDynamics, "Источники · Belberry", belberryEventLeadTotals);
const sourceDynamicsHeaderRow = findRowByFirstCell(sourceDynamics, "Источник");
expectEqual("Динамика источников 2026 / таблица источников найдена", sourceDynamicsHeaderRow > 0 ? 1 : 0, 1);
const sourceDynamicsStartRow = sourceDynamicsHeaderRow + 1;
expectEqual("Динамика источников 2026 / строк источников", countSourceRowsUntilTotal(sourceDynamics, sourceDynamicsStartRow, 1), eventSourceTotals.length);
const acoolaSourceDynamicsTitleRow = findRowByFirstCell(sourceDynamics, "Источники · Acoola Team");
const belberrySourceDynamicsTitleRow = findRowByFirstCell(sourceDynamics, "Источники · Belberry");
if (acoolaSourceDynamicsTitleRow > 0) {
  expectEqual("Динамика источников 2026 / Acoola строк источников", countSourceRowsUntilTotal(sourceDynamics, acoolaSourceDynamicsTitleRow + 2, 1), acoolaEventSourceTotals.length);
}
if (belberrySourceDynamicsTitleRow > 0) {
  expectEqual("Динамика источников 2026 / Belberry строк источников", countSourceRowsUntilTotal(sourceDynamics, belberrySourceDynamicsTitleRow + 2, 1), belberryEventSourceTotals.length);
}
expectText("Динамика источников 2026 / колонка после итога пустая", cell(sourceDynamics, sourceDynamicsHeaderRow, 16), "");
expectEqual("Динамика источников 2026 / нет блока Управленческий вывод", findRowByFirstCell(sourceDynamics, "Управленческий вывод"), 0);
expectEqual("Динамика источников 2026 / нет блока График динамики основных источников", findRowByFirstCell(sourceDynamics, "График динамики основных источников"), 0);
expectEqual("Динамика источников 2026 / нет блока Доля источника в общем объёме месяца", findRowByFirstCell(sourceDynamics, "Доля источника в общем объёме месяца"), 0);
expectEqual("Динамика источников 2026 / нет блока Динамика месяц к месяцу", findRowByFirstCell(sourceDynamics, "Динамика месяц к месяцу"), 0);
expectEqual("Динамика источников 2026 / нет блока Проблемы маппинга и аномалии", findRowByFirstCell(sourceDynamics, "Проблемы маппинга и аномалии"), 0);
expectNotIncludes("Динамика источников 2026 / заголовок таблицы без Аномалии", sourceDynamics[sourceDynamicsHeaderRow - 1]?.join(" "), "Аномалии");
expectNotIncludes("Динамика источников 2026 / легенда без аномалий", sourceDynamics.flat().join(" "), "аномалия");
if (eventSourceTotals.length) {
  const topSource = eventSourceTotals[0];
  expectText("Динамика источников 2026 / топ-источник", cell(sourceDynamics, sourceDynamicsStartRow, 1), topSource.source);
  expectEqual("Динамика источников 2026 / топ-источник итог", cell(sourceDynamics, sourceDynamicsStartRow, 15), topSource.lead);
}
const rawSourceTrends = values.get("rawSourceTrends");
expectText("RAW source_trends_2026 / helper отключён", cell(rawSourceTrends, 1, 1), "Не используется");

const spamSources = values.get("spamSources");
expectIncludes("Спам по источникам / заголовок", cell(spamSources, 1, 1), "СПАМ ПО ИСТОЧНИКАМ");
expectText("Спам по источникам / метрика", cell(spamSources, 2, 2), "Спамные лиды");
expectText("Спам по источникам / поле причины отказа", cell(spamSources, 4, 2), "UF_CRM_1771495464");
expectEqual("Спам по источникам / есть общая сводка", findRowByFirstCell(spamSources, "Спам · общая сводка") > 0 ? 1 : 0, 1);
expectEqual("Спам по источникам / есть Акула", findRowByFirstCell(spamSources, "Спам · Акула") > 0 ? 1 : 0, 1);
expectEqual("Спам по источникам / есть Белбери", findRowByFirstCell(spamSources, "Спам · Белбери") > 0 ? 1 : 0, 1);
checkSourceDynamicsTotal("Спам по источникам / общая сводка", spamSources, "Спам · общая сводка", spamMonthTotalValues);
checkSourceDynamicsTotal("Спам по источникам / Акула", spamSources, "Спам · Акула", acoolaSpamMonthTotals);
checkSourceDynamicsTotal("Спам по источникам / Белбери", spamSources, "Спам · Белбери", belberrySpamMonthTotals);
const spamSourcesHeaderRow = findRowByFirstCell(spamSources, "Источник");
expectEqual("Спам по источникам / таблица источников найдена", spamSourcesHeaderRow > 0 ? 1 : 0, 1);
const spamSourcesStartRow = spamSourcesHeaderRow + 1;
expectEqual("Спам по источникам / строк источников", countSourceRowsUntilTotal(spamSources, spamSourcesStartRow, 1), spamSourceTotals.length);
if (spamSourceTotals.length) {
  const topSpamSource = spamSourceTotals[0];
  expectText("Спам по источникам / топ-источник", cell(spamSources, spamSourcesStartRow, 1), topSpamSource.source);
  expectEqual("Спам по источникам / топ-источник итог", cell(spamSources, spamSourcesStartRow, 15), topSpamSource.spam);
}
const acoolaSpamTitleRow = findRowByFirstCell(spamSources, "Спам · Акула");
const belberrySpamTitleRow = findRowByFirstCell(spamSources, "Спам · Белбери");
if (acoolaSpamTitleRow > 0) {
  expectEqual("Спам по источникам / Акула строк источников", countSourceRowsUntilTotal(spamSources, acoolaSpamTitleRow + 2, 1), acoolaSpamSourceTotals.length);
}
if (belberrySpamTitleRow > 0) {
  expectEqual("Спам по источникам / Белбери строк источников", countSourceRowsUntilTotal(spamSources, belberrySpamTitleRow + 2, 1), belberrySpamSourceTotals.length);
}
expectEqual("Спам по источникам / бренды не превышают общий итог", Number(cell(spamSources, acoolaSpamTitleRow + 2 + acoolaSpamSourceTotals.length, 15) || 0) + Number(cell(spamSources, belberrySpamTitleRow + 2 + belberrySpamSourceTotals.length, 15) || 0) <= spamSourceRows.length ? 1 : 0, 1);
const rawSpamSources = values.get("rawSpamSources");
expectText("RAW spam_sources_2026 / ID", cell(rawSpamSources, 1, 1), "ID");
expectEqual("RAW spam_sources_2026 / строк", Math.max((rawSpamSources || []).length - 1, 0), spamSourceRows.length);

const eventsMonthly = values.get("eventsMonthly");
expectEqual("События по месяцам / лиды всего", cell(eventsMonthly, 7, 5), eventTotals.lead);
expectEqual("События по месяцам / КП всего", cell(eventsMonthly, 8, 5), eventTotals.kp);
expectEqual("События по месяцам / договоры всего", cell(eventsMonthly, 9, 5), eventTotals.contract);
expectEqual("События по месяцам / продажи всего", cell(eventsMonthly, 10, 5), eventTotals.sale);
expectEqual("События по месяцам / выручка всего", cell(eventsMonthly, 11, 5), eventTotals.revenue);

const quality = values.get("quality");
expectEqual("Качество данных / без источника", cell(quality, 6, 2), qualitySummary.noSource);
expectEqual("Качество данных / не выяснено", cell(quality, 6, 5), qualitySummary.unclear);
expectEqual("Качество данных / без бренда", cell(quality, 6, 8), qualitySummary.noBrand);
expectEqual("Качество данных / аномалии стадий", cell(quality, 7, 2), qualitySummary.stage);
expectEqual("Качество данных / продажи с проблемной атрибуцией", cell(quality, 7, 5), qualitySummary.wonAttr);
expectEqual("Качество данных / всего проблемных сделок", cell(quality, 7, 8), qualitySummary.total);

const winsDeals = values.get("winsDeals");
const winsServices = values.get("winsServices");
expectText("Продажи YTD сделки / строка 3 пустая", cell(winsDeals, 3, 1), "");
expectText("Продажи YTD услуги / строка 3 пустая", cell(winsServices, 3, 1), "");
expectText("Продажи YTD сделки / Общая сводка строка 4", cell(winsDeals, 4, 1), "Общая сводка");
expectText("Продажи YTD услуги / Общая сводка строка 4", cell(winsServices, 4, 1), "Общая сводка");
expectNoIsoDateTime("Формат дат / лист Продажи YTD сделки", (winsDeals || []).flat());
expectNoIsoDateTime("Формат дат / лист Продажи YTD услуги", (winsServices || []).flat());
if (dealRows.length) expectRuDate("Формат дат / лист Продажи YTD сделки первая дата", cell(winsDeals, 13, 1));
const winsDealsAcoolaRow = findRowByFirstCell(winsDeals, "Acoola Team");
const winsDealsBelberryRow = findRowByFirstCell(winsDeals, "Belberry");
const winsServicesAcoolaRow = findRowByFirstCell(winsServices, "Acoola Team");
const winsServicesBelberryRow = findRowByFirstCell(winsServices, "Belberry");
expectGreater("Продажи YTD сделки / Belberry ниже Acoola", winsDealsBelberryRow, winsDealsAcoolaRow);
expectGreater("Продажи YTD услуги / Belberry ниже Acoola", winsServicesBelberryRow, winsServicesAcoolaRow);
expectText("Продажи YTD сделки / справа от Acoola нет второго блока", cell(winsDeals, winsDealsAcoolaRow, 8), "");
expectText("Продажи YTD услуги / справа от Acoola нет второго блока", cell(winsServices, winsServicesAcoolaRow, 9), "");
expectEqual("Продажи YTD сделки / всего сделок", sumSheetRowsRange(winsDeals, 6, 8, { count: 2 }).count, dealRows.length);
expectEqual("Продажи YTD услуги / всего услуг", sumSheetRowsRange(winsServices, 6, 8, { count: 3 }).count, serviceRows.length);
for (const [index, row] of winsDeals.entries()) {
  if (index < 11) continue;
  if (hasNumericId(row[2])) expectManagerFormat(`Продажи YTD сделки / Acoola / менеджер / строка ${index + 1}`, row[4]);
}
for (const [index, row] of winsServices.entries()) {
  if (index < 11) continue;
  if (hasNumericId(row[2])) expectManagerFormat(`Продажи YTD услуги / Acoola / менеджер / строка ${index + 1}`, row[4]);
}

const expenses = values.get("expenses");
expectEqual("Шаблон расходов / строк источников", countRowsWithValue(expenses, 9, 1), sourceRowsWithoutNoBrand.length);
expectIncludes("Методология / заголовок", cell(values.get("methodology"), 1, 1), "Методология");
expectIncludes("Методология / телемаркетинг лид", cell(values.get("methodology"), 13, 2), "первая встреча");
expectIncludes("Методология / телемаркетинг override", cell(values.get("methodology"), 24, 2), "встреча");
expectIncludes("Методология / source id телемаркетинг", cell(values.get("methodology"), 25, 2), "Не выяснено");
expectIncludes("Методология / спам нет связи", cell(values.get("methodology"), 26, 2), "Вход: нет связи");
expectIncludes("Метаданные / телемаркетинг override", telemarketingOverride.source_name || "", "Телемаркетинг");

const rawCohort = values.get("rawCohortSource");
const rawCohortSums = sumSheetRows(rawCohort, 2, { obr: 4, lead: 5, kp: 6, contract: 7, sale: 8, revenue: 9 });
expectEqual("RAW cohort_source / строк", countRowsWithValue(rawCohort, 2, 1), sourceRows.length);
for (const field of ["obr", "lead", "kp", "contract", "sale", "revenue"]) {
  expectEqual(`RAW cohort_source / суммы: ${field}`, rawCohortSums[field], cohortTotals[field]);
}

const rawEventBrand = values.get("rawEventBrand");
const rawEventSums = sumSheetRows(rawEventBrand, 2, { lead: 3, kp: 4, contract: 5, sale: 6, revenue: 7 });
expectEqual("RAW event_brand / строк", countRowsWithValue(rawEventBrand, 2, 1), (events.event_rows || []).length);
for (const field of ["lead", "kp", "contract", "sale", "revenue"]) {
  expectEqual(`RAW event_brand / суммы: ${field}`, rawEventSums[field], eventTotals[field]);
}

const rawEventSales = values.get("rawEventSales");
const rawEventSalesSums = sumSheetRows(rawEventSales, 2, { sale: 4, revenue: 5 });
expectEqual("RAW event_sales / продажи", rawEventSalesSums.sale, eventTotals.sale);
expectEqual("RAW event_sales / выручка", rawEventSalesSums.revenue, eventTotals.revenue);

const failed = checks.filter((check) => !check.ok);
const result = {
  status: failed.length ? "FAIL" : "OK",
  checked: checks.length,
  failed: failed.length,
  period: cohort.meta?.period,
  updated_at: cohort.meta?.updated_at,
  totals: {
    cohort: cohortTotals,
    event: eventTotals,
    wins: { deals: dealRows.length, services: serviceRows.length },
    quality: qualitySummary,
  },
  failed_checks: failed,
};

console.log(JSON.stringify(result, null, 2));
if (failed.length) process.exit(1);
