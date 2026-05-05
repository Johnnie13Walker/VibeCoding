import { createSign } from "node:crypto";
import { readFile } from "node:fs/promises";
import { formatPeriodLabel, monthsFromCohortByBrand } from "./marketing_dashboard_period.mjs";

const SHEET_URL = "https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit#gid=0";
const SA_PATH = process.env.MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON || process.env.GOOGLE_SERVICE_ACCOUNT_JSON || "/Users/pro2kuror/Downloads/finance-director-sheets-903611b799c3.json";
const DATA_PATH = "/tmp/cohort_slice_3.json";
const TRUE_EVENTS_PATH = "/tmp/true_events_q1_2026.json";
const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SCOPE = "https://www.googleapis.com/auth/spreadsheets";

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
async function loadJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}
async function loadOptionalJson(path) {
  try {
    return JSON.parse(await readFile(path, "utf8"));
  } catch {
    return null;
  }
}
function buildJwt({ client_email, private_key }, scope) {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "RS256", typ: "JWT" };
  const claim = { iss: client_email, scope, aud: TOKEN_URL, exp: now + 3600, iat: now };
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
    assertion: buildJwt(sa, SCOPE),
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
async function batchUpdate(sheetId, token, requests) {
  return fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${sheetId}:batchUpdate`, token, {
    method: "POST",
    body: JSON.stringify({ requests }),
  });
}
async function valuesUpdate(sheetId, token, range, values) {
  const res = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${sheetId}/values/${encodeURIComponent(range)}?valueInputOption=USER_ENTERED`, {
    method: "PUT",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify({ majorDimension: "ROWS", values }),
  });
  const payload = await res.json();
  if (!res.ok) throw new Error(`Values update error: ${res.status} ${JSON.stringify(payload)}`);
  return payload;
}
function pct(value) {
  return `${(value * 100).toFixed(1).replace(".", ",")}%`;
}
function fmtInt(value) {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(Number(value || 0));
}
function fmtMoney(value) {
  return `${fmtInt(value)} ₽`;
}
function formatMoscowTimestamp() {
  const fmt = new Intl.DateTimeFormat("ru-RU", {
    timeZone: "Europe/Moscow",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
  return fmt.format(new Date());
}
function brandSourceMetrics(data, brand) {
  const map = new Map();
  for (const [key, metrics] of Object.entries(data.cohort_by_source || {})) {
    const [, rowBrand, source] = key.split("|||");
    if (rowBrand !== brand) continue;
    const bucket = map.get(source) || { source, obr: 0, lead: 0, kp: 0, contract: 0, sale: 0, revenue: 0 };
    bucket.obr += Number(metrics.obr || 0);
    bucket.lead += Number(metrics.lead || 0);
    bucket.kp += Number(metrics.kp || 0);
    bucket.contract += Number(metrics.contract || 0);
    bucket.sale += Number(metrics.sale || 0);
    bucket.revenue += Number(metrics.revenue || 0);
    map.set(source, bucket);
  }
  return Array.from(map.values());
}
function brandMonthMetrics(data, brand) {
  const map = new Map();
  for (const [key, metrics] of Object.entries(data.cohort_by_brand || {})) {
    const [month, rowBrand] = key.split("|||");
    if (rowBrand !== brand) continue;
    map.set(month, {
      month,
      obr: Number(metrics.obr || 0),
      lead: Number(metrics.lead || 0),
      kp: Number(metrics.kp || 0),
      contract: Number(metrics.contract || 0),
      sale: Number(metrics.sale || 0),
      revenue: Number(metrics.revenue || 0),
    });
  }
  return Array.from(map.values()).sort((a, b) => a.month.localeCompare(b.month));
}
function eventMetricsByBrand(eventRows, brand) {
  return eventRows
    .filter((row) => row.brand === brand)
    .map((row) => ({
      month: row.month,
      lead: Number(row.lead || 0),
      kp: Number(row.kp || 0),
      contract: Number(row.contract || 0),
      sale: Number(row.sale || 0),
      revenue: Number(row.revenue || 0),
    }));
}
function pickMax(rows, scorer) {
  return rows.reduce((best, row) => (best == null || scorer(row) > scorer(best) ? row : best), null);
}
function stageBottleneck(row) {
  const options = [];
  if (row.obr > 0) options.push({ label: "обращение → лид", value: row.lead / row.obr });
  if (row.lead > 0) options.push({ label: "лид → КП", value: row.kp / row.lead });
  if (row.kp > 0) options.push({ label: "КП → договор", value: row.contract / row.kp });
  if (row.contract > 0) options.push({ label: "договор → продажа", value: row.sale / row.contract });
  return options.sort((a, b) => a.value - b.value)[0] || { label: "нет данных", value: 0 };
}
function buildBrandInsightLines(brand, totals, data, eventRows) {
  const sources = brandSourceMetrics(data, brand);
  const months = brandMonthMetrics(data, brand);
  const events = eventMetricsByBrand(eventRows, brand);
  const topVolume = pickMax(sources, (row) => row.obr) || { source: "нет данных", obr: 0 };
  const topSale = pickMax(sources, (row) => row.sale * 1_000_000_000 + row.revenue * 1_000 + row.contract) || { source: "нет данных", sale: 0, revenue: 0 };
  const topContract = pickMax(sources, (row) => row.contract * 1_000_000 + row.kp * 1_000 + row.lead) || { source: "нет данных", contract: 0 };
  const topMonth = pickMax(months, (row) => row.obr) || { month: "нет данных", obr: 0 };
  const topEventRevenueMonth = pickMax(events, (row) => row.revenue * 1_000 + row.sale) || { month: "нет данных", revenue: 0 };
  const bottleneck = stageBottleneck(totals);
  const lines = [];
  if (totals.obr > 0) {
    lines.push(`Основной объём обращений даёт ${topVolume.source}: ${fmtInt(topVolume.obr)} из ${fmtInt(totals.obr)} (${pct(topVolume.obr / totals.obr)}).`);
  }
  if (topSale.sale > 0) {
    if (topSale.source === "Не выяснено" || topSale.source === "Без источника") {
      lines.push(`Продажа в когорте пришла из «${topSale.source}»: ${fmtInt(topSale.sale)} шт. и ${fmtMoney(topSale.revenue)} выручки. Атрибуцию источника стоит дочистить.`);
    } else {
      lines.push(`Лучший продающий источник в когорте — ${topSale.source}: ${fmtInt(topSale.sale)} продажа и ${fmtMoney(topSale.revenue)} выручки.`);
    }
  } else {
    lines.push(`Продаж в когорте пока нет. До договора лучше остальных доводит ${topContract.source}: ${fmtInt(topContract.contract)} договора.`);
  }
  lines.push(`Главное узкое место — переход ${bottleneck.label}: ${pct(bottleneck.value)}.`);
  lines.push(`По когорте пик обращений был в ${topMonth.month} (${fmtInt(topMonth.obr)}), а по событийному слою пик выручки — в ${topEventRevenueMonth.month} (${fmtMoney(topEventRevenueMonth.revenue)}).`);
  return lines;
}
function findSource(rows, name) {
  return rows.find((row) => row.source === name) || { source: name, obr: 0, lead: 0, kp: 0, contract: 0, sale: 0, revenue: 0 };
}
function bestScaleSource(rows) {
  const excluded = new Set(["Не выяснено", "Без источника"]);
  const attributed = rows.filter((row) => !excluded.has(row.source));
  const withSales = attributed
    .filter((row) => row.sale > 0)
    .sort((a, b) => (b.sale - a.sale) || (b.revenue - a.revenue) || (b.obr - a.obr));
  if (withSales[0]) return withSales[0];
  const byVolume = attributed.sort((a, b) => (b.obr - a.obr) || (b.lead - a.lead) || (b.contract - a.contract));
  return byVolume[0] || rows.sort((a, b) => b.obr - a.obr)[0] || { source: "нет данных", obr: 0, lead: 0, sale: 0, revenue: 0 };
}
function buildActionLines(label, totals, sourceRows) {
  const unattributed = findSource(sourceRows, "Не выяснено").obr + findSource(sourceRows, "Без источника").obr;
  const scale = bestScaleSource(sourceRows);
  const bottleneck = stageBottleneck(totals);
  const lines = [];
  lines.push(`Масштабировать: ${scale.source} — ${fmtInt(scale.obr)} обращений, ${fmtInt(scale.lead)} лидов${scale.sale ? `, ${fmtInt(scale.sale)} продажи` : ""}.`);
  if (unattributed > 0) {
    lines.push(`Чинить: ${bottleneck.label} (${pct(bottleneck.value)}). Отдельно почистить атрибуцию: ${fmtInt(unattributed)} обращений без нормального источника.`);
  } else {
    lines.push(`Чинить: ${bottleneck.label} (${pct(bottleneck.value)}). Это главный текущий стоп-фактор для ${label}.`);
  }
  return lines;
}

const spreadsheetId = extractSheetId(SHEET_URL);
const sa = await loadJson(SA_PATH);
const data = await loadJson(DATA_PATH);
const trueEvents = await loadOptionalJson(TRUE_EVENTS_PATH);
const token = await fetchAccessToken(sa);
const metadata = await fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}`, token);
const sheets = new Map((metadata.sheets || []).map((sheet) => [sheet.properties.title, sheet.properties.sheetId]));

const title = "CEO Dashboard";
if (!sheets.has(title)) {
  const reply = await batchUpdate(spreadsheetId, token, [{ addSheet: { properties: { title, gridProperties: { rowCount: 80, columnCount: 16 } } } }]);
  const props = reply.replies?.[0]?.addSheet?.properties;
  if (props?.title) sheets.set(props.title, props.sheetId);
}
const sheetId = sheets.get(title);
const qualitySheetId = sheets.get("Качество данных") || 0;
const methodologySheetId = sheets.get("Методология") || 0;
const expensesSheetId = sheets.get("Шаблон расходов") || 0;
const chartSheetTitle = "RAW · ceo_charts";
if (!sheets.has(chartSheetTitle)) {
  const reply = await batchUpdate(spreadsheetId, token, [{ addSheet: { properties: { title: chartSheetTitle, hidden: true, gridProperties: { rowCount: 20, columnCount: 8 } } } }]);
  const props = reply.replies?.[0]?.addSheet?.properties;
  if (props?.title) sheets.set(props.title, props.sheetId);
}
const chartSheetId = sheets.get(chartSheetTitle);
const chartsMetadata = await fetchJson(
  `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}?fields=sheets(properties(sheetId,title),charts(chartId))`,
  token,
);
const existingDashboardCharts = (chartsMetadata.sheets || []).find((sheet) => sheet.properties?.title === title)?.charts || [];

const dashboardRowsAll = Object.entries(data.dashboard_by_brand || {})
  .map(([brand, metrics]) => ({ brand, ...metrics }));
const dashboardRows = dashboardRowsAll.filter((row) => row.brand !== "Без бренда");
const totals = dashboardRowsAll.reduce((acc, row) => {
  acc.obr += Number(row.obr || 0);
  acc.lead += Number(row.lead || 0);
  acc.kp += Number(row.kp || 0);
  acc.contract += Number(row.contract || 0);
  acc.sale += Number(row.sale || 0);
  acc.revenue += Number(row.revenue || 0);
  return acc;
}, { obr: 0, lead: 0, kp: 0, contract: 0, sale: 0, revenue: 0 });
const acoola = dashboardRows.find((row) => row.brand === "Acoola Team") || { obr: 0, lead: 0, kp: 0, contract: 0, sale: 0, revenue: 0 };
const belberry = dashboardRows.find((row) => row.brand === "Belberry") || { obr: 0, lead: 0, kp: 0, contract: 0, sale: 0, revenue: 0 };
const noBrand = dashboardRowsAll.find((row) => row.brand === "Без бренда") || { obr: 0, lead: 0, kp: 0, contract: 0, sale: 0, revenue: 0 };
const brandSectionTitle = noBrand.obr > 0
  ? 'Бренды: итог за период · Когортный слой (общий итог выше включает ещё строку "Без бренда")'
  : "Бренды: итог за период · Когортный слой";
const sourceAgg = new Map();
for (const [key, metrics] of Object.entries(data.cohort_by_source || {})) {
  const [cohortMonth, brand, source] = key.split("|||");
  const bucket = sourceAgg.get(source) || { source, obr: 0, lead: 0, kp: 0, contract: 0, sale: 0, revenue: 0 };
  bucket.obr += Number(metrics.obr || 0);
  bucket.lead += Number(metrics.lead || 0);
  bucket.kp += Number(metrics.kp || 0);
  bucket.contract += Number(metrics.contract || 0);
  bucket.sale += Number(metrics.sale || 0);
  bucket.revenue += Number(metrics.revenue || 0);
  bucket.months = bucket.months || new Set();
  bucket.months.add(cohortMonth);
  sourceAgg.set(source, bucket);
}
const allSources = Array.from(sourceAgg.values())
  .sort((a, b) => b.obr - a.obr || b.sale - a.sale || b.revenue - a.revenue || b.lead - a.lead || a.source.localeCompare(b.source, "ru"));
const cohortMonths = monthsFromCohortByBrand(data.cohort_by_brand || {});
const periodLabel = formatPeriodLabel(cohortMonths);
const updatedAt = formatMoscowTimestamp();
const acoolaSources = brandSourceMetrics(data, "Acoola Team");
const belberrySources = brandSourceMetrics(data, "Belberry");

const eventTotals = (trueEvents?.event_rows?.length ? trueEvents.event_rows : Object.entries(data.monthly_events || {}).map(([key, metrics]) => {
  const [month, brand] = key.split("|||");
  return { month, brand, ...metrics };
})).reduce((acc, row) => {
  const brand = row.brand;
  if (brand === "Без бренда") return acc;
  acc.lead += Number(row.lead || 0);
  acc.kp += Number(row.kp || 0);
  acc.contract += Number(row.contract || 0);
  acc.sale += Number(row.sale || 0);
  acc.revenue += Number(row.revenue || 0);
  return acc;
}, { lead: 0, kp: 0, contract: 0, sale: 0, revenue: 0 });
const eventRows = (trueEvents?.event_rows?.length ? trueEvents.event_rows : Object.entries(data.monthly_events || {}).map(([key, metrics]) => {
  const [month, brand] = key.split("|||");
  return { month, brand, ...metrics };
})).filter((row) => row.brand !== "Без бренда");
const acoolaInsights = buildBrandInsightLines("Acoola Team", acoola, data, eventRows);
const belberryInsights = buildBrandInsightLines("Belberry", belberry, data, eventRows);
const overallActions = buildActionLines("общего маркетинга", totals, allSources);
const acoolaActions = buildActionLines("Acoola Team", acoola, acoolaSources);
const belberryActions = buildActionLines("Belberry", belberry, belberrySources);
const asNum = (value) => Number(value || 0);
const cohortChartRows = [
  ["Месяц", "Acoola Team", "Belberry"],
  ...cohortMonths.map((month) => {
    const ac = data.cohort_by_brand?.[`${month}|||Acoola Team`] || {};
    const bb = data.cohort_by_brand?.[`${month}|||Belberry`] || {};
    return [month, asNum(ac.obr), asNum(bb.obr)];
  }),
];
const eventRevenueChartRows = [
  ["Месяц", "Acoola Team", "Belberry"],
  ...cohortMonths.map((month) => {
    const ac = eventRows.find((row) => row.brand === "Acoola Team" && row.month === month) || {};
    const bb = eventRows.find((row) => row.brand === "Belberry" && row.month === month) || {};
    return [month, asNum(ac.revenue), asNum(bb.revenue)];
  }),
];
const brandRows = [
  {
    brand: "Acoola Team",
    obr: asNum(acoola.obr),
    lead: asNum(acoola.lead),
    kp: asNum(acoola.kp),
    contract: asNum(acoola.contract),
    sale: asNum(acoola.sale),
    revenue: asNum(acoola.revenue),
    crLead: pct(asNum(acoola.obr) ? asNum(acoola.lead) / asNum(acoola.obr) : 0),
    crSale: pct(asNum(acoola.obr) ? asNum(acoola.sale) / asNum(acoola.obr) : 0),
    share: pct(totals.obr ? asNum(acoola.obr) / totals.obr : 0),
  },
  {
    brand: "Belberry",
    obr: asNum(belberry.obr),
    lead: asNum(belberry.lead),
    kp: asNum(belberry.kp),
    contract: asNum(belberry.contract),
    sale: asNum(belberry.sale),
    revenue: asNum(belberry.revenue),
    crLead: pct(asNum(belberry.obr) ? asNum(belberry.lead) / asNum(belberry.obr) : 0),
    crSale: pct(asNum(belberry.obr) ? asNum(belberry.sale) / asNum(belberry.obr) : 0),
    share: pct(totals.obr ? asNum(belberry.obr) / totals.obr : 0),
  },
];
if (noBrand.obr > 0) {
  brandRows.push({
    brand: "Без бренда",
    obr: asNum(noBrand.obr),
    lead: asNum(noBrand.lead),
    kp: asNum(noBrand.kp),
    contract: asNum(noBrand.contract),
    sale: asNum(noBrand.sale),
    revenue: asNum(noBrand.revenue),
    crLead: pct(asNum(noBrand.obr) ? asNum(noBrand.lead) / asNum(noBrand.obr) : 0),
    crSale: pct(asNum(noBrand.obr) ? asNum(noBrand.sale) / asNum(noBrand.obr) : 0),
    share: pct(totals.obr ? asNum(noBrand.obr) / totals.obr : 0),
  });
}
brandRows.push({
  brand: "Итого",
  obr: totals.obr,
  lead: totals.lead,
  kp: totals.kp,
  contract: totals.contract,
  sale: totals.sale,
  revenue: totals.revenue,
  crLead: pct(totals.obr ? totals.lead / totals.obr : 0),
  crSale: pct(totals.obr ? totals.sale / totals.obr : 0),
  share: "100,0%",
});

const values = [];
const row = (...cells) => {
  values.push(cells);
  return values.length - 1;
};

const headerRow = row("CEO DASHBOARD · МАРКЕТИНГ");
const infoRow = row("Период", periodLabel, "", "Контур", "Только сделки, проходившие воронку продаж", "", "", "", "Обновлено", updatedAt);
const noteRow = row("Логика", 'Когортный слой считает по месяцу создания сделки. Событийный слой считает по месяцу первого входа в этап. Источник не пересчитывается при переносах между воронками.');
row("");

const cohortHeaderRow = row("Когортный слой · управленческая сводка");
const cohortMetricLabelRow = row("Обращения", "", "Лиды", "", "КП", "", "Договоры", "", "Продажи", "", "Выручка", "", "", "");
const cohortMetricValueRow = row(fmtInt(totals.obr), "", fmtInt(totals.lead), "", fmtInt(totals.kp), "", fmtInt(totals.contract), "", fmtInt(totals.sale), "", fmtMoney(totals.revenue), "", "", "");
const cohortConvLabelRow = row("CR обр → лид", "", "CR лид → КП", "", "CR КП → договор", "", "CR договор → продажа", "", "CR обр → продажа", "", "Без бренда", "", "", "");
const cohortConvValueRow = row(
  pct(totals.obr ? totals.lead / totals.obr : 0), "",
  pct(totals.lead ? totals.kp / totals.lead : 0), "",
  pct(totals.kp ? totals.contract / totals.kp : 0), "",
  pct(totals.contract ? totals.sale / totals.contract : 0), "",
  pct(totals.obr ? totals.sale / totals.obr : 0), "",
  fmtInt(noBrand.obr), "", "", ""
);
row("");

const eventHeaderRow = row("Событийный слой · фактические переходы");
const eventMetricLabelRow = row("Лиды", "", "КП", "", "Договоры", "", "Продажи", "", "Выручка", "", "", "", "", "");
const eventMetricValueRow = row(fmtInt(eventTotals.lead), "", fmtInt(eventTotals.kp), "", fmtInt(eventTotals.contract), "", fmtInt(eventTotals.sale), "", fmtMoney(eventTotals.revenue), "", "", "", "", "");
row("");

const brandHeaderRow = row(brandSectionTitle);
const brandTableHeaderRow = row("Бренд", "Обращения", "Лиды", "КП", "Договоры", "Продажи", "Выручка", "CR обр → лид", "CR обр → продажа", "Доля обращений");
const brandTableStartRow = values.length;
for (const item of brandRows) {
  row(item.brand, fmtInt(item.obr), fmtInt(item.lead), fmtInt(item.kp), fmtInt(item.contract), fmtInt(item.sale), fmtMoney(item.revenue), item.crLead, item.crSale, item.share);
}
row("");

const insightsHeaderRow = row("Маркетинговые выводы по брендам");
const insightsTitleRow = row("Acoola Team", "", "", "", "", "", "", "Belberry", "", "", "", "", "", "");
const acoolaText = [...acoolaInsights];
const belberryText = [...belberryInsights];
const insightsBodyStartRow = values.length;
for (let i = 0; i < Math.max(acoolaText.length, belberryText.length); i += 1) {
  row(acoolaText[i] || "", "", "", "", "", "", "", belberryText[i] || "", "", "", "", "", "", "");
}
row("");

const actionsHeaderRow = row("Фокус на период · что масштабировать и что чинить");
const actionsTitleRow = row("Общий фокус", "", "", "", "", "Acoola Team", "", "", "", "Belberry", "", "", "", "");
const actionsBodyStartRow = values.length;
for (let i = 0; i < 2; i += 1) {
  row(overallActions[i] || "", "", "", "", "", acoolaActions[i] || "", "", "", "", belberryActions[i] || "", "", "", "", "");
}
row("");

const sourceHeaderRow = row(`Все источники: ${periodLabel.toLowerCase()} · Когортный слой`);
const sourceTableHeaderRow = row("Источник", "Обращения", "Лиды", "КП", "Договоры", "Продажи", "CR обр → лид", "CR обр → продажа", "Выручка");
const sourceTableStartRow = values.length;
for (const item of allSources) {
  row(item.source, fmtInt(item.obr), fmtInt(item.lead), fmtInt(item.kp), fmtInt(item.contract), fmtInt(item.sale), pct(item.obr ? item.lead / item.obr : 0), pct(item.obr ? item.sale / item.obr : 0), fmtMoney(item.revenue));
}
const sourceTotalRow = row("Итого", fmtInt(totals.obr), fmtInt(totals.lead), fmtInt(totals.kp), fmtInt(totals.contract), fmtInt(totals.sale), pct(totals.obr ? totals.lead / totals.obr : 0), pct(totals.obr ? totals.sale / totals.obr : 0), fmtMoney(totals.revenue));
row("");

const chartHeaderRow = row("Графики по месяцам");
const chartSpacerStartRow = values.length;
for (let i = 0; i < 16; i += 1) row("");

const navHeaderRow = row("Навигация");
row('=HYPERLINK("https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit#gid=1494202454";"Когортный фильтр")', "Главный когортный интерфейс");
row('=HYPERLINK("https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit#gid=1805015534";"Событийный фильтр")', "Главный событийный интерфейс");
row(`=HYPERLINK("https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit#gid=${qualitySheetId}";"Качество данных")`, "Очередь на правку и контроль проблемных сделок");
row(`=HYPERLINK("https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit#gid=${methodologySheetId}";"Методология")`, "Правила расчёта и трактовка метрик");
row(`=HYPERLINK("https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit#gid=${expensesSheetId}";"Шаблон расходов")`, "Шаблон для загрузки расходов по источникам");
row('=HYPERLINK("https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit#gid=2021554791";"Продажи YTD 2026 · сделки")', "Уникальные сделки по дате первого УСПЕХ");
row('=HYPERLINK("https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit#gid=77219014";"Продажи YTD 2026 · услуги")', "Услуги внутри выигранных сделок");
row('=HYPERLINK("https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit#gid=146952454";"Сделки")', "Детальный список sales-only сделок");

const requests = [
  { updateCells: { range: { sheetId }, fields: "userEnteredValue,userEnteredFormat,textFormatRuns,dataValidation,note" } },
  { unmergeCells: { range: { sheetId, startRowIndex: 0, endRowIndex: 120, startColumnIndex: 0, endColumnIndex: 14 } } },
  { updateSheetProperties: { properties: { sheetId, gridProperties: { frozenRowCount: 3, frozenColumnCount: 0 } }, fields: "gridProperties.frozenRowCount,gridProperties.frozenColumnCount" } },
  { repeatCell: { range: { sheetId }, cell: { userEnteredFormat: { backgroundColor: { red: 0.972, green: 0.976, blue: 0.98 }, textFormat: { foregroundColor: { red: 0.09, green: 0.13, blue: 0.18 }, fontFamily: "Arial", fontSize: 11 }, verticalAlignment: "MIDDLE", wrapStrategy: "WRAP" } }, fields: "userEnteredFormat(backgroundColor,textFormat,verticalAlignment,wrapStrategy)" } },
  { mergeCells: { range: { sheetId, startRowIndex: headerRow, endRowIndex: headerRow + 1, startColumnIndex: 0, endColumnIndex: 14 }, mergeType: "MERGE_ALL" } },
  { mergeCells: { range: { sheetId, startRowIndex: noteRow, endRowIndex: noteRow + 1, startColumnIndex: 1, endColumnIndex: 14 }, mergeType: "MERGE_ALL" } },
  { mergeCells: { range: { sheetId, startRowIndex: cohortHeaderRow, endRowIndex: cohortHeaderRow + 1, startColumnIndex: 0, endColumnIndex: 14 }, mergeType: "MERGE_ALL" } },
  { mergeCells: { range: { sheetId, startRowIndex: eventHeaderRow, endRowIndex: eventHeaderRow + 1, startColumnIndex: 0, endColumnIndex: 14 }, mergeType: "MERGE_ALL" } },
  { mergeCells: { range: { sheetId, startRowIndex: brandHeaderRow, endRowIndex: brandHeaderRow + 1, startColumnIndex: 0, endColumnIndex: 14 }, mergeType: "MERGE_ALL" } },
  { mergeCells: { range: { sheetId, startRowIndex: insightsHeaderRow, endRowIndex: insightsHeaderRow + 1, startColumnIndex: 0, endColumnIndex: 14 }, mergeType: "MERGE_ALL" } },
  { mergeCells: { range: { sheetId, startRowIndex: actionsHeaderRow, endRowIndex: actionsHeaderRow + 1, startColumnIndex: 0, endColumnIndex: 14 }, mergeType: "MERGE_ALL" } },
  { mergeCells: { range: { sheetId, startRowIndex: sourceHeaderRow, endRowIndex: sourceHeaderRow + 1, startColumnIndex: 0, endColumnIndex: 14 }, mergeType: "MERGE_ALL" } },
  { mergeCells: { range: { sheetId, startRowIndex: chartHeaderRow, endRowIndex: chartHeaderRow + 1, startColumnIndex: 0, endColumnIndex: 14 }, mergeType: "MERGE_ALL" } },
  { mergeCells: { range: { sheetId, startRowIndex: navHeaderRow, endRowIndex: navHeaderRow + 1, startColumnIndex: 0, endColumnIndex: 14 }, mergeType: "MERGE_ALL" } },
  { mergeCells: { range: { sheetId, startRowIndex: insightsTitleRow, endRowIndex: insightsTitleRow + 1, startColumnIndex: 0, endColumnIndex: 7 }, mergeType: "MERGE_ALL" } },
  { mergeCells: { range: { sheetId, startRowIndex: insightsTitleRow, endRowIndex: insightsTitleRow + 1, startColumnIndex: 7, endColumnIndex: 14 }, mergeType: "MERGE_ALL" } },
  { mergeCells: { range: { sheetId, startRowIndex: actionsTitleRow, endRowIndex: actionsTitleRow + 1, startColumnIndex: 0, endColumnIndex: 5 }, mergeType: "MERGE_ALL" } },
  { mergeCells: { range: { sheetId, startRowIndex: actionsTitleRow, endRowIndex: actionsTitleRow + 1, startColumnIndex: 5, endColumnIndex: 9 }, mergeType: "MERGE_ALL" } },
  { mergeCells: { range: { sheetId, startRowIndex: actionsTitleRow, endRowIndex: actionsTitleRow + 1, startColumnIndex: 9, endColumnIndex: 14 }, mergeType: "MERGE_ALL" } },
];

const cardRanges = [
  [0, 2], [2, 4], [4, 6], [6, 8], [8, 10], [10, 14],
];
for (const [startColumnIndex, endColumnIndex] of cardRanges) {
  requests.push({ mergeCells: { range: { sheetId, startRowIndex: cohortMetricLabelRow, endRowIndex: cohortMetricLabelRow + 1, startColumnIndex, endColumnIndex }, mergeType: "MERGE_ALL" } });
  requests.push({ mergeCells: { range: { sheetId, startRowIndex: cohortMetricValueRow, endRowIndex: cohortMetricValueRow + 1, startColumnIndex, endColumnIndex }, mergeType: "MERGE_ALL" } });
}
for (const [startColumnIndex, endColumnIndex] of [[0, 2], [2, 4], [4, 6], [6, 8], [8, 10], [10, 14]]) {
  requests.push({ mergeCells: { range: { sheetId, startRowIndex: eventMetricLabelRow, endRowIndex: eventMetricLabelRow + 1, startColumnIndex, endColumnIndex }, mergeType: "MERGE_ALL" } });
  requests.push({ mergeCells: { range: { sheetId, startRowIndex: eventMetricValueRow, endRowIndex: eventMetricValueRow + 1, startColumnIndex, endColumnIndex }, mergeType: "MERGE_ALL" } });
}
for (const [startColumnIndex, endColumnIndex] of [[0, 2], [2, 4], [4, 6], [6, 8], [8, 10], [10, 14]]) {
  requests.push({ mergeCells: { range: { sheetId, startRowIndex: cohortConvLabelRow, endRowIndex: cohortConvLabelRow + 1, startColumnIndex, endColumnIndex }, mergeType: "MERGE_ALL" } });
  requests.push({ mergeCells: { range: { sheetId, startRowIndex: cohortConvValueRow, endRowIndex: cohortConvValueRow + 1, startColumnIndex, endColumnIndex }, mergeType: "MERGE_ALL" } });
}
for (let offset = 0; offset < 2; offset += 1) {
  requests.push({ mergeCells: { range: { sheetId, startRowIndex: actionsBodyStartRow + offset, endRowIndex: actionsBodyStartRow + offset + 1, startColumnIndex: 0, endColumnIndex: 5 }, mergeType: "MERGE_ALL" } });
  requests.push({ mergeCells: { range: { sheetId, startRowIndex: actionsBodyStartRow + offset, endRowIndex: actionsBodyStartRow + offset + 1, startColumnIndex: 5, endColumnIndex: 9 }, mergeType: "MERGE_ALL" } });
  requests.push({ mergeCells: { range: { sheetId, startRowIndex: actionsBodyStartRow + offset, endRowIndex: actionsBodyStartRow + offset + 1, startColumnIndex: 9, endColumnIndex: 14 }, mergeType: "MERGE_ALL" } });
}
for (let offset = 0; offset < Math.max(acoolaText.length, belberryText.length); offset += 1) {
  requests.push({ mergeCells: { range: { sheetId, startRowIndex: insightsBodyStartRow + offset, endRowIndex: insightsBodyStartRow + offset + 1, startColumnIndex: 0, endColumnIndex: 7 }, mergeType: "MERGE_ALL" } });
  requests.push({ mergeCells: { range: { sheetId, startRowIndex: insightsBodyStartRow + offset, endRowIndex: insightsBodyStartRow + offset + 1, startColumnIndex: 7, endColumnIndex: 14 }, mergeType: "MERGE_ALL" } });
}

const setRowHeight = (start, end, size) => requests.push({ updateDimensionProperties: { range: { sheetId, dimension: "ROWS", startIndex: start, endIndex: end }, properties: { pixelSize: size }, fields: "pixelSize" } });
setRowHeight(headerRow, headerRow + 1, 48);
setRowHeight(infoRow, infoRow + 1, 28);
setRowHeight(noteRow, noteRow + 1, 34);
setRowHeight(cohortMetricValueRow, cohortMetricValueRow + 1, 36);
setRowHeight(cohortConvValueRow, cohortConvValueRow + 1, 32);
setRowHeight(eventMetricValueRow, eventMetricValueRow + 1, 36);
setRowHeight(insightsTitleRow, insightsTitleRow + 1, 30);
setRowHeight(insightsBodyStartRow, insightsBodyStartRow + 4, 42);
setRowHeight(actionsTitleRow, actionsTitleRow + 1, 30);
setRowHeight(actionsBodyStartRow, actionsBodyStartRow + 2, 42);
setRowHeight(chartHeaderRow, chartHeaderRow + 1, 32);
setRowHeight(chartSpacerStartRow, chartSpacerStartRow + 16, 22);

const sectionHeader = (start, end, color) => requests.push({
  repeatCell: {
    range: { sheetId, startRowIndex: start, endRowIndex: end, startColumnIndex: 0, endColumnIndex: 14 },
    cell: { userEnteredFormat: { backgroundColor: color, textFormat: { bold: true, foregroundColor: { red: 1, green: 1, blue: 1 }, fontSize: 13 }, horizontalAlignment: "LEFT", verticalAlignment: "MIDDLE" } },
    fields: "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
  },
});

sectionHeader(headerRow, headerRow + 1, { red: 0.09, green: 0.13, blue: 0.2 });
sectionHeader(cohortHeaderRow, cohortHeaderRow + 1, { red: 0.06, green: 0.44, blue: 0.41 });
sectionHeader(eventHeaderRow, eventHeaderRow + 1, { red: 0.74, green: 0.39, blue: 0.16 });
sectionHeader(brandHeaderRow, brandHeaderRow + 1, { red: 0.12, green: 0.3, blue: 0.44 });
sectionHeader(insightsHeaderRow, insightsHeaderRow + 1, { red: 0.12, green: 0.3, blue: 0.44 });
sectionHeader(actionsHeaderRow, actionsHeaderRow + 1, { red: 0.31, green: 0.36, blue: 0.43 });
sectionHeader(sourceHeaderRow, sourceHeaderRow + 1, { red: 0.09, green: 0.13, blue: 0.2 });
sectionHeader(chartHeaderRow, chartHeaderRow + 1, { red: 0.31, green: 0.36, blue: 0.43 });
sectionHeader(navHeaderRow, navHeaderRow + 1, { red: 0.31, green: 0.36, blue: 0.43 });

requests.push({
  repeatCell: {
    range: { sheetId, startRowIndex: infoRow, endRowIndex: infoRow + 1, startColumnIndex: 0, endColumnIndex: 14 },
    cell: { userEnteredFormat: { backgroundColor: { red: 0.92, green: 0.95, blue: 0.98 }, textFormat: { bold: true, foregroundColor: { red: 0.2, green: 0.26, blue: 0.33 } } } },
    fields: "userEnteredFormat(backgroundColor,textFormat)",
  },
});
requests.push({
  repeatCell: {
    range: { sheetId, startRowIndex: noteRow, endRowIndex: noteRow + 1, startColumnIndex: 0, endColumnIndex: 14 },
    cell: { userEnteredFormat: { backgroundColor: { red: 0.98, green: 0.98, blue: 0.94 }, textFormat: { foregroundColor: { red: 0.34, green: 0.36, blue: 0.24 } } } },
    fields: "userEnteredFormat(backgroundColor,textFormat)",
  },
});

const cardLabelRows = [cohortMetricLabelRow, cohortConvLabelRow, eventMetricLabelRow];
for (const start of cardLabelRows) {
  requests.push({
    repeatCell: {
      range: { sheetId, startRowIndex: start, endRowIndex: start + 1, startColumnIndex: 0, endColumnIndex: 14 },
      cell: { userEnteredFormat: { backgroundColor: { red: 0.89, green: 0.94, blue: 0.92 }, textFormat: { bold: true, foregroundColor: { red: 0.18, green: 0.25, blue: 0.22 } }, horizontalAlignment: "CENTER" } },
      fields: "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
    },
  });
}
for (const start of [cohortMetricValueRow, cohortConvValueRow, eventMetricValueRow]) {
  requests.push({
    repeatCell: {
      range: { sheetId, startRowIndex: start, endRowIndex: start + 1, startColumnIndex: 0, endColumnIndex: 14 },
      cell: { userEnteredFormat: { backgroundColor: { red: 1, green: 1, blue: 1 }, textFormat: { bold: true, fontSize: 14 }, horizontalAlignment: "CENTER" } },
      fields: "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
    },
  });
}

requests.push({
  repeatCell: {
    range: { sheetId, startRowIndex: brandTableHeaderRow, endRowIndex: brandTableHeaderRow + 1, startColumnIndex: 0, endColumnIndex: 10 },
    cell: { userEnteredFormat: { backgroundColor: { red: 0.9, green: 0.93, blue: 0.96 }, textFormat: { bold: true, foregroundColor: { red: 0.2, green: 0.26, blue: 0.33 } }, horizontalAlignment: "CENTER" } },
    fields: "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
  },
});
brandRows.forEach((item, index) => {
  let color = { red: 1, green: 1, blue: 1 };
  if (item.brand === "Acoola Team") color = { red: 0.92, green: 0.97, blue: 0.95 };
  if (item.brand === "Belberry") color = { red: 0.99, green: 0.95, blue: 0.91 };
  if (item.brand === "Без бренда") color = { red: 0.99, green: 0.94, blue: 0.94 };
  if (item.brand === "Итого") color = { red: 0.93, green: 0.95, blue: 0.98 };
  requests.push({
    repeatCell: {
      range: { sheetId, startRowIndex: brandTableStartRow + index, endRowIndex: brandTableStartRow + index + 1, startColumnIndex: 0, endColumnIndex: 10 },
      cell: { userEnteredFormat: { backgroundColor: color, textFormat: { bold: item.brand === "Итого" }, horizontalAlignment: "CENTER" } },
      fields: "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
    },
  });
});

requests.push({
  repeatCell: {
    range: { sheetId, startRowIndex: insightsTitleRow, endRowIndex: insightsTitleRow + 1, startColumnIndex: 0, endColumnIndex: 7 },
    cell: { userEnteredFormat: { backgroundColor: { red: 0.22, green: 0.49, blue: 0.45 }, textFormat: { bold: true, foregroundColor: { red: 1, green: 1, blue: 1 } }, horizontalAlignment: "LEFT" } },
    fields: "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
  },
});
requests.push({
  repeatCell: {
    range: { sheetId, startRowIndex: insightsTitleRow, endRowIndex: insightsTitleRow + 1, startColumnIndex: 7, endColumnIndex: 14 },
    cell: { userEnteredFormat: { backgroundColor: { red: 0.7, green: 0.43, blue: 0.2 }, textFormat: { bold: true, foregroundColor: { red: 1, green: 1, blue: 1 } }, horizontalAlignment: "LEFT" } },
    fields: "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
  },
});
requests.push({
  repeatCell: {
    range: { sheetId, startRowIndex: insightsBodyStartRow, endRowIndex: insightsBodyStartRow + Math.max(acoolaText.length, belberryText.length), startColumnIndex: 0, endColumnIndex: 14 },
    cell: { userEnteredFormat: { backgroundColor: { red: 1, green: 1, blue: 1 }, wrapStrategy: "WRAP", verticalAlignment: "TOP" } },
    fields: "userEnteredFormat(backgroundColor,wrapStrategy,verticalAlignment)",
  },
});
requests.push({
  repeatCell: {
    range: { sheetId, startRowIndex: actionsTitleRow, endRowIndex: actionsTitleRow + 1, startColumnIndex: 0, endColumnIndex: 14 },
    cell: { userEnteredFormat: { backgroundColor: { red: 0.91, green: 0.94, blue: 0.97 }, textFormat: { bold: true, foregroundColor: { red: 0.2, green: 0.26, blue: 0.33 } }, horizontalAlignment: "LEFT" } },
    fields: "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
  },
});
requests.push({
  repeatCell: {
    range: { sheetId, startRowIndex: actionsBodyStartRow, endRowIndex: actionsBodyStartRow + 2, startColumnIndex: 0, endColumnIndex: 14 },
    cell: { userEnteredFormat: { backgroundColor: { red: 1, green: 1, blue: 1 }, wrapStrategy: "WRAP", verticalAlignment: "TOP" } },
    fields: "userEnteredFormat(backgroundColor,wrapStrategy,verticalAlignment)",
  },
});
requests.push({
  repeatCell: {
    range: { sheetId, startRowIndex: chartSpacerStartRow, endRowIndex: chartSpacerStartRow + 16, startColumnIndex: 0, endColumnIndex: 14 },
    cell: { userEnteredFormat: { backgroundColor: { red: 1, green: 1, blue: 1 } } },
    fields: "userEnteredFormat(backgroundColor)",
  },
});

requests.push({
  repeatCell: {
    range: { sheetId, startRowIndex: sourceTableHeaderRow, endRowIndex: sourceTableHeaderRow + 1, startColumnIndex: 0, endColumnIndex: 9 },
    cell: { userEnteredFormat: { backgroundColor: { red: 0.91, green: 0.95, blue: 0.98 }, textFormat: { bold: true, foregroundColor: { red: 0.2, green: 0.26, blue: 0.33 } }, horizontalAlignment: "CENTER" } },
    fields: "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
  },
});
allSources.forEach((_, index) => {
  const even = index % 2 === 0;
  requests.push({
    repeatCell: {
      range: { sheetId, startRowIndex: sourceTableStartRow + index, endRowIndex: sourceTableStartRow + index + 1, startColumnIndex: 0, endColumnIndex: 9 },
      cell: { userEnteredFormat: { backgroundColor: even ? { red: 1, green: 1, blue: 1 } : { red: 0.97, green: 0.98, blue: 0.99 }, horizontalAlignment: "CENTER" } },
      fields: "userEnteredFormat(backgroundColor,horizontalAlignment)",
    },
  });
});
requests.push({
  repeatCell: {
    range: { sheetId, startRowIndex: sourceTotalRow, endRowIndex: sourceTotalRow + 1, startColumnIndex: 0, endColumnIndex: 9 },
    cell: { userEnteredFormat: { backgroundColor: { red: 0.92, green: 0.95, blue: 0.98 }, textFormat: { bold: true }, horizontalAlignment: "CENTER" } },
    fields: "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
  },
});

for (const range of [
  { startRowIndex: brandTableHeaderRow, endRowIndex: brandTableStartRow + brandRows.length, startColumnIndex: 0, endColumnIndex: 10 },
  { startRowIndex: sourceTableHeaderRow, endRowIndex: sourceTotalRow + 1, startColumnIndex: 0, endColumnIndex: 9 },
]) {
  requests.push({
    updateBorders: {
      range: { sheetId, ...range },
      top: { style: "SOLID", color: { red: 0.75, green: 0.79, blue: 0.84 } },
      bottom: { style: "SOLID", color: { red: 0.75, green: 0.79, blue: 0.84 } },
      left: { style: "SOLID", color: { red: 0.75, green: 0.79, blue: 0.84 } },
      right: { style: "SOLID", color: { red: 0.75, green: 0.79, blue: 0.84 } },
      innerHorizontal: { style: "SOLID", color: { red: 0.87, green: 0.89, blue: 0.92 } },
      innerVertical: { style: "SOLID", color: { red: 0.87, green: 0.89, blue: 0.92 } },
    },
  });
}

const columnWidths = [180, 118, 118, 118, 118, 118, 118, 118, 118, 118, 118, 118, 118, 118];
columnWidths.forEach((pixelSize, columnIndex) => {
  requests.push({
    updateDimensionProperties: {
      range: { sheetId, dimension: "COLUMNS", startIndex: columnIndex, endIndex: columnIndex + 1 },
      properties: { pixelSize },
      fields: "pixelSize",
    },
  });
});

const helperValues = cohortChartRows.map((row, index) => [...row, "", ...eventRevenueChartRows[index]]);
await valuesUpdate(spreadsheetId, token, `${quoteSheetTitle(chartSheetTitle)}!A1:G${helperValues.length}`, helperValues);

requests.push({
  updateSheetProperties: {
    properties: { sheetId: chartSheetId, hidden: true, gridProperties: { rowCount: 20, columnCount: 8 } },
    fields: "hidden,gridProperties.rowCount,gridProperties.columnCount",
  },
});
for (const chart of existingDashboardCharts) {
  requests.push({ deleteEmbeddedObject: { objectId: chart.chartId } });
}
requests.push({
  addChart: {
    chart: {
      spec: {
        title: "Когортные обращения по брендам",
        subtitle: periodLabel,
        fontName: "Arial",
        titleTextFormat: { fontSize: 15, bold: true },
        subtitleTextFormat: { fontSize: 10, foregroundColorStyle: { rgbColor: { red: 0.42, green: 0.46, blue: 0.53 } } },
        backgroundColorStyle: { rgbColor: { red: 1, green: 1, blue: 1 } },
        basicChart: {
          chartType: "LINE",
          legendPosition: "BOTTOM_LEGEND",
          headerCount: 1,
          lineSmoothing: false,
          axis: [
            { position: "BOTTOM_AXIS", title: "Месяц" },
            { position: "LEFT_AXIS", title: "Обращения" },
          ],
          domains: [{
            domain: {
              sourceRange: {
                sources: [{ sheetId: chartSheetId, startRowIndex: 0, endRowIndex: helperValues.length, startColumnIndex: 0, endColumnIndex: 1 }],
              },
            },
          }],
          series: [
            {
              series: { sourceRange: { sources: [{ sheetId: chartSheetId, startRowIndex: 0, endRowIndex: helperValues.length, startColumnIndex: 1, endColumnIndex: 2 }] } },
              targetAxis: "LEFT_AXIS",
              colorStyle: { rgbColor: { red: 0.22, green: 0.49, blue: 0.45 } },
            },
            {
              series: { sourceRange: { sources: [{ sheetId: chartSheetId, startRowIndex: 0, endRowIndex: helperValues.length, startColumnIndex: 2, endColumnIndex: 3 }] } },
              targetAxis: "LEFT_AXIS",
              colorStyle: { rgbColor: { red: 0.7, green: 0.43, blue: 0.2 } },
            },
          ],
        },
      },
      position: {
        overlayPosition: {
          anchorCell: { sheetId, rowIndex: chartSpacerStartRow, columnIndex: 0 },
          offsetXPixels: 0,
          offsetYPixels: 8,
          widthPixels: 520,
          heightPixels: 280,
        },
      },
    },
  },
});
requests.push({
  addChart: {
    chart: {
      spec: {
        title: "Событийная выручка по брендам",
        subtitle: periodLabel,
        fontName: "Arial",
        titleTextFormat: { fontSize: 15, bold: true },
        subtitleTextFormat: { fontSize: 10, foregroundColorStyle: { rgbColor: { red: 0.42, green: 0.46, blue: 0.53 } } },
        backgroundColorStyle: { rgbColor: { red: 1, green: 1, blue: 1 } },
        basicChart: {
          chartType: "COLUMN",
          legendPosition: "BOTTOM_LEGEND",
          headerCount: 1,
          axis: [
            { position: "BOTTOM_AXIS", title: "Месяц" },
            { position: "LEFT_AXIS", title: "Выручка, ₽" },
          ],
          domains: [{
            domain: {
              sourceRange: {
                sources: [{ sheetId: chartSheetId, startRowIndex: 0, endRowIndex: helperValues.length, startColumnIndex: 4, endColumnIndex: 5 }],
              },
            },
          }],
          series: [
            {
              series: { sourceRange: { sources: [{ sheetId: chartSheetId, startRowIndex: 0, endRowIndex: helperValues.length, startColumnIndex: 5, endColumnIndex: 6 }] } },
              targetAxis: "LEFT_AXIS",
              colorStyle: { rgbColor: { red: 0.22, green: 0.49, blue: 0.45 } },
            },
            {
              series: { sourceRange: { sources: [{ sheetId: chartSheetId, startRowIndex: 0, endRowIndex: helperValues.length, startColumnIndex: 6, endColumnIndex: 7 }] } },
              targetAxis: "LEFT_AXIS",
              colorStyle: { rgbColor: { red: 0.7, green: 0.43, blue: 0.2 } },
            },
          ],
        },
      },
      position: {
        overlayPosition: {
          anchorCell: { sheetId, rowIndex: chartSpacerStartRow, columnIndex: 7 },
          offsetXPixels: 0,
          offsetYPixels: 8,
          widthPixels: 520,
          heightPixels: 280,
        },
      },
    },
  },
});

await batchUpdate(spreadsheetId, token, requests);
await valuesUpdate(spreadsheetId, token, `${quoteSheetTitle(title)}!A1:N160`, values);
console.log(JSON.stringify({ sheet: title, sourceRows: allSources.length, totals, periodLabel }, null, 2));
