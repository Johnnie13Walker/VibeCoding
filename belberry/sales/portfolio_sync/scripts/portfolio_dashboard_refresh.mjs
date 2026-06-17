#!/usr/bin/env node
import { createSign } from "node:crypto";
import { readFile } from "node:fs/promises";

const DEFAULT_DATABASE_URL = "https://docs.google.com/spreadsheets/d/1TgWlFHOvSDtW0e60fCLNvWDW7ADwOimHpypbQG7GI9E/edit";
const DEFAULT_DASHBOARD_URL = "https://docs.google.com/spreadsheets/d/1om_oGYvDZrADYbAbznZOyk7InhHF7kKs5MrMzzAJC2A/edit";
const DEFAULT_SA_PATH = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json";

const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SCOPE = "https://www.googleapis.com/auth/spreadsheets";
const DATABASE_SHEET = "Данные";
const YEARS_ACTIVE_LABEL = "2025–26";

const SHEETS = {
  dashboard: "Дашборд",
  categories: "Категории",
  products: "Продукты",
  clients: "Клиенты",
  productClient: "Продукт × Клиент",
  classification: "Классификация",
  data: "Данные",
  dashData: "dash_data",
};

const COLORS = {
  header: { red: 0.118, green: 0.184, blue: 0.263 },
  headerText: { red: 1, green: 1, blue: 1 },
  band: { red: 0.929, green: 0.953, blue: 0.976 },
  accent: { red: 0.839, green: 0.898, blue: 0.957 },
  muted: { red: 0.961, green: 0.965, blue: 0.969 },
};

function parseArgs(argv) {
  const args = {
    dryRun: false,
    databaseUrl: process.env.PORTFOLIO_DATABASE_SHEET_URL || DEFAULT_DATABASE_URL,
    dashboardUrl: process.env.PORTFOLIO_DASHBOARD_SHEET_URL || DEFAULT_DASHBOARD_URL,
    serviceAccountPath: process.env.PORTFOLIO_GOOGLE_SERVICE_ACCOUNT_JSON
      || process.env.MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON
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
    if (token === "--database-url") {
      args.databaseUrl = next;
      index += 1;
      continue;
    }
    if (token === "--dashboard-url") {
      args.dashboardUrl = next;
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
  const text = String(value ?? "").trim();
  return /^[=+\-@]/.test(text) ? `'${text}` : text;
}

function numberText(value) {
  return String(Number(value || 0));
}

function pct(part, total) {
  if (!total) return "0%";
  return `${Math.round((part / total) * 100)}%`;
}

function pct1(part, total) {
  if (!total) return "0,0%";
  return `${((part / total) * 100).toFixed(1).replace(".", ",")}%`;
}

function avg1(value) {
  return Number(value || 0).toFixed(1).replace(".", ",");
}

function yearNumber(value) {
  const n = Number(String(value ?? "").replace(",", ".").trim());
  return Number.isFinite(n) ? Math.trunc(n) : 0;
}

function monthNumber(value) {
  const n = Number(String(value ?? "").replace(",", ".").trim());
  return Number.isFinite(n) ? Math.trunc(n) : 0;
}

function minMaxPeriod(years) {
  const sorted = [...years].sort((a, b) => a - b);
  if (!sorted.length) return "";
  if (sorted[0] === sorted[sorted.length - 1]) return String(sorted[0]);
  return `${sorted[0]}-${sorted[sorted.length - 1]}`;
}

function yearsList(years) {
  return [...years].sort((a, b) => a - b).join(", ");
}

function statusByMaxYear(maxYear) {
  if (maxYear >= 2025) return "Активен";
  if (maxYear === 2024) return "Спящий";
  return "Архив";
}

function topEntry(map) {
  return [...map.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0]), "ru"))[0] || ["", 0];
}

function inc(map, key, delta = 1) {
  map.set(key, (map.get(key) || 0) + delta);
}

function addToNested(map, key1, key2, value) {
  if (!map.has(key1)) map.set(key1, new Map());
  inc(map.get(key1), key2, value);
}

function buildJwt({ client_email: clientEmail, private_key: privateKey }) {
  const now = Math.floor(Date.now() / 1000);
  const header = base64url(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const claim = base64url(JSON.stringify({ iss: clientEmail, scope: SCOPE, aud: TOKEN_URL, exp: now + 3600, iat: now }));
  const signer = createSign("RSA-SHA256");
  signer.update(`${header}.${claim}`);
  signer.end();
  const signature = signer.sign(privateKey, "base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  return `${header}.${claim}.${signature}`;
}

async function fetchAccessToken(serviceAccount) {
  const response = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
      assertion: buildJwt(serviceAccount),
    }),
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
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json", ...(init.headers || {}) },
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

async function valuesUpdate(spreadsheetId, token, title, grid) {
  const rows = Math.max(grid.length, 1);
  const cols = Math.max(...grid.map((row) => row.length), 1);
  const normalized = grid.map((row) => Array.from({ length: cols }, (_, index) => row[index] ?? ""));
  const range = `${quoteSheetTitle(title)}!A1:${colLetter(cols)}${rows}`;
  const response = await fetch(
    `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}?valueInputOption=RAW`,
    {
      method: "PUT",
      headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({ majorDimension: "ROWS", values: normalized }),
    },
  );
  const payload = await response.json();
  if (!response.ok) throw new Error(`Values update error: ${response.status} ${JSON.stringify(payload)}`);
  return payload;
}

async function valuesClear(spreadsheetId, token, title, rows, cols) {
  const range = `${quoteSheetTitle(title)}!A1:${colLetter(cols)}${rows}`;
  const response = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}:clear`, {
    method: "POST",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: "{}",
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(`Values clear error: ${response.status} ${JSON.stringify(payload)}`);
  return payload;
}

async function ensureSheets(spreadsheetId, token, sheetSpecs) {
  const metadata = await fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}?includeGridData=false`, token);
  const existing = new Map((metadata.sheets || []).map((sheet) => [sheet.properties.title, sheet.properties]));
  const requests = [];
  for (const spec of sheetSpecs) {
    if (!existing.has(spec.title)) {
      requests.push({
        addSheet: {
          properties: {
            title: spec.title,
            hidden: Boolean(spec.hidden),
            gridProperties: { rowCount: Math.max(spec.rows + 20, 100), columnCount: Math.max(spec.cols + 2, 12) },
          },
        },
      });
    }
  }
  if (requests.length) await batchUpdate(spreadsheetId, token, requests);
  const updated = await fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}?includeGridData=false`, token);
  return new Map((updated.sheets || []).map((sheet) => [sheet.properties.title, sheet.properties.sheetId]));
}

function readClassification(rows) {
  const map = new Map();
  for (const row of rows.slice(1)) {
    const project = safeText(row[0]);
    if (!project) continue;
    map.set(project, {
      project,
      category: safeText(row[1]) || "Не определено",
      subcategory: safeText(row[2]) || "Не определено",
      source: safeText(row[3]) || "сохранено",
      sourceRows: safeText(row[4]) || "",
      sourceRowNumbers: safeText(row[5]) || "",
    });
  }
  return map;
}

function buildModel(dataRows, classificationRows) {
  const classification = readClassification(classificationRows);
  const projects = new Map();
  const years = new Set();

  for (const row of dataRows.slice(1)) {
    const project = safeText(row[0]);
    const service = safeText(row[1]);
    const brand = safeText(row[2]);
    const year = yearNumber(row[3]);
    const month = monthNumber(row[4]);
    const department = safeText(row[6]);
    const newOld = safeText(row[7]);
    if (!project || !service || !year) continue;
    years.add(year);
    if (!projects.has(project)) {
      const classified = classification.get(project) || {
        project,
        category: "Не определено",
        subcategory: "Не определено",
        source: "нет классификации",
        sourceRows: "",
        sourceRowNumbers: "",
      };
      projects.set(project, {
        project,
        category: classified.category,
        subcategory: classified.subcategory,
        classification: classified,
        brands: new Set(),
        departments: new Set(),
        newOld: new Set(),
        services: new Set(),
        years: new Set(),
        months: new Set(),
        receipts: 0,
        servicesByYear: new Map(),
        yearsByService: new Map(),
        monthsByService: new Map(),
        receiptsByService: new Map(),
      });
    }
    const item = projects.get(project);
    if (brand) item.brands.add(brand);
    if (department) item.departments.add(department);
    if (newOld) item.newOld.add(newOld);
    item.services.add(service);
    item.years.add(year);
    if (month) item.months.add(`${year}-${String(month).padStart(2, "0")}`);
    item.receipts += 1;
    if (!item.servicesByYear.has(year)) item.servicesByYear.set(year, new Set());
    item.servicesByYear.get(year).add(service);
    if (!item.yearsByService.has(service)) item.yearsByService.set(service, new Set());
    item.yearsByService.get(service).add(year);
    if (!item.monthsByService.has(service)) item.monthsByService.set(service, new Set());
    if (month) item.monthsByService.get(service).add(`${year}-${String(month).padStart(2, "0")}`);
    inc(item.receiptsByService, service);
  }

  const yearList = [...years].sort((a, b) => a - b);
  const projectList = [...projects.values()].sort((a, b) => a.category.localeCompare(b.category, "ru") || a.project.localeCompare(b.project, "ru"));
  return { projects, projectList, yearList };
}

function enrichModel(model) {
  const services = new Set();
  const categories = new Set();
  for (const project of model.projectList) {
    project.minYear = Math.min(...project.years);
    project.maxYear = Math.max(...project.years);
    project.period = minMaxPeriod(project.years);
    project.status = statusByMaxYear(project.maxYear);
    project.monthCount = project.months.size;
    project.servicesList = [...project.services].sort((a, b) => a.localeCompare(b, "ru"));
    for (const service of project.services) services.add(service);
    categories.add(project.category);
  }
  return {
    ...model,
    serviceList: [...services].sort((a, b) => a.localeCompare(b, "ru")),
    categoryList: [...categories].sort((a, b) => a.localeCompare(b, "ru")),
  };
}

function buildCategoryRows(model) {
  const totalProjects = model.projectList.length;
  const byCategory = new Map();
  for (const project of model.projectList) {
    if (!byCategory.has(project.category)) {
      byCategory.set(project.category, { projects: [], subcategories: new Map(), products: new Map(), active: 0, months: 0 });
    }
    const item = byCategory.get(project.category);
    item.projects.push(project);
    inc(item.subcategories, project.subcategory);
    for (const service of project.services) inc(item.products, service);
    if (project.maxYear >= 2025) item.active += 1;
    item.months += project.monthCount;
  }

  return [...byCategory.entries()]
    .map(([category, data]) => {
      const [topSubcategory] = topEntry(data.subcategories);
      const [topProduct] = topEntry(data.products);
      return [
        category,
        numberText(data.projects.length),
        pct1(data.projects.length, totalProjects),
        numberText(data.subcategories.size),
        topSubcategory,
        topProduct,
        numberText(data.active),
        avg1(data.months / data.projects.length),
      ];
    })
    .sort((a, b) => Number(b[1]) - Number(a[1]) || a[0].localeCompare(b[0], "ru"));
}

function buildProductRows(model) {
  const rows = [];
  const totalProjects = model.projectList.length;
  for (const service of model.serviceList) {
    const projects = model.projectList.filter((project) => project.services.has(service));
    const byCategory = new Map();
    const byYear = new Map();
    for (const project of projects) {
      inc(byCategory, project.category);
      for (const year of project.yearsByService.get(service) || []) inc(byYear, year);
    }
    const [topCategory, topCategoryCount] = topEntry(byCategory);
    const y2024 = byYear.get(2024) || 0;
    const y2025 = byYear.get(2025) || 0;
    const delta = y2025 - y2024;
    rows.push([
      service,
      numberText(projects.length),
      pct1(projects.length, totalProjects),
      topCategory ? `${topCategory} (${topCategoryCount})` : "",
      ...model.yearList.map((year) => numberText(byYear.get(year) || 0)),
      delta > 0 ? `+ ${delta}` : String(delta),
    ]);
  }
  return rows.sort((a, b) => Number(b[1]) - Number(a[1]) || a[0].localeCompare(b[0], "ru"));
}

function buildClientRows(model) {
  return model.projectList.map((project) => [
    project.project,
    project.category,
    project.subcategory,
    project.period,
    project.servicesList.join(", "),
    ...model.yearList.map((year) => [...(project.servicesByYear.get(year) || [])].sort((a, b) => a.localeCompare(b, "ru")).join(", ")),
    numberText(project.monthCount),
    numberText(project.receipts),
    project.status,
  ]);
}

function buildProductClientRows(model) {
  const rows = [];
  for (const project of model.projectList) {
    for (const service of project.servicesList) {
      const serviceYears = project.yearsByService.get(service) || new Set();
      const serviceMonths = project.monthsByService.get(service) || new Set();
      rows.push([
        service,
        project.project,
        project.category,
        project.subcategory,
        yearsList(serviceYears),
        minMaxPeriod(serviceYears),
        yearsList(project.years),
        project.servicesList.join(", "),
        numberText(serviceMonths.size),
        numberText(project.receiptsByService.get(service) || 0),
        project.classification.source === "нет классификации" ? "нет классификации" : "есть данные",
      ]);
    }
  }
  return rows.sort((a, b) => a[0].localeCompare(b[0], "ru") || a[2].localeCompare(b[2], "ru") || a[1].localeCompare(b[1], "ru"));
}

function buildClassificationRows(model) {
  return model.projectList.map((project) => [
    project.project,
    project.category,
    project.subcategory,
    project.classification.source || "сохранено",
    project.classification.sourceRows || "",
    project.classification.sourceRowNumbers || "",
  ]);
}

function buildRetentionRows(model) {
  const byCohort = new Map();
  for (const project of model.projectList) {
    if (!byCohort.has(project.minYear)) byCohort.set(project.minYear, []);
    byCohort.get(project.minYear).push(project);
  }
  return [...byCohort.entries()].sort((a, b) => a[0] - b[0]).map(([cohort, projects]) => [
    String(cohort),
    numberText(projects.length),
    ...model.yearList.map((year) => {
      if (year < cohort) return "";
      const active = projects.filter((project) => project.years.has(year)).length;
      return pct(active, projects.length);
    }),
  ]);
}

function buildYearProductRows(model, topProducts) {
  return model.yearList.map((year) => {
    const counts = new Map();
    for (const project of model.projectList) {
      const yearServices = project.servicesByYear.get(year) || new Set();
      for (const service of yearServices) inc(counts, service);
    }
    const topSum = topProducts.reduce((sum, product) => sum + (counts.get(product) || 0), 0);
    const allSum = [...counts.values()].reduce((sum, value) => sum + value, 0);
    return [String(year), ...topProducts.map((product) => numberText(counts.get(product) || 0)), numberText(allSum - topSum)];
  });
}

function buildCategoryProductRows(model, topProducts) {
  const rows = [];
  for (const category of model.categoryList) {
    const projects = model.projectList.filter((project) => project.category === category);
    rows.push([
      category,
      numberText(projects.length),
      ...topProducts.map((product) => numberText(projects.filter((project) => project.services.has(product)).length)),
    ]);
  }
  return rows.sort((a, b) => Number(b[1]) - Number(a[1]) || a[0].localeCompare(b[0], "ru"));
}

function buildSheets(model) {
  const categoryRows = buildCategoryRows(model);
  const productRows = buildProductRows(model);
  const clientRows = buildClientRows(model);
  const productClientRows = buildProductClientRows(model);
  const classificationRows = buildClassificationRows(model);
  const retentionRows = buildRetentionRows(model);
  const topProducts = productRows.slice(0, 10).map((row) => row[0]);
  const yearProductRows = buildYearProductRows(model, topProducts.slice(0, 5));
  const heatmapRows = buildCategoryProductRows(model, topProducts);
  const topCategory = categoryRows[0] || ["", "0", "0%", "", "", "", "0", ""];
  const topProduct = productRows[0] || ["", "0", "0%"];
  const activeCount = model.projectList.filter((project) => project.maxYear >= 2025).length;
  const yearPeriod = `${model.yearList[0]}–${model.yearList[model.yearList.length - 1]}`;
  const categoryShare = topCategory[2];
  const activeShare = pct(activeCount, model.projectList.length);
  const updated = nowMsk();

  const dashboard = [
    [],
    ["", "Клиентское портфолио"],
    ["", `${model.projectList.length} клиентов · ${categoryRows.length} категорий · ${productRows.length} продуктов · ${yearPeriod}`],
    [],
    ["", "ГЛАВНОЕ"],
    ["", `•  Топ-ниша: ${topCategory[0]} — ${topCategory[1]} клиентов (${categoryShare}). Внутри сильнее всего: ${topCategory[4]}.`],
    ["", `•  Топ-продукт: ${topProduct[0]} — ${topProduct[1]} проектов (${topProduct[2]} портфолио).`],
    ["", `•  Активных в ${YEARS_ACTIVE_LABEL}: ${activeCount} клиентов (${activeShare}). Обновлено из закрытой базы: ${updated} МСК.`],
    [],
    [],
    ["", "КЛИЕНТОВ", "", "", "", `АКТИВНЫХ В ${YEARS_ACTIVE_LABEL}`, "", "", "", "ТОП-НИША", "", "", "", "ТОП-ПРОДУКТ"],
    ["", numberText(model.projectList.length), "", "", "", `${activeCount} (${activeShare})`, "", "", "", topCategory[0], "", "", "", topProduct[0]],
    ["", "всего в портфолио", "", "", "", "сейчас в работе", "", "", "", `${categoryShare} · ${topCategory[1]} клиентов`, "", "", "", `${topProduct[1]} проектов · ${topProduct[2]}`],
    [],
    [],
    ["", "УДЕРЖАНИЕ КЛИЕНТОВ ПО КОГОРТАМ", "", "", "", "", "", "", "", "ДИНАМИКА ПОРТФОЛИО ПО ГОДАМ"],
    ["", "Когорта", "Размер", ...model.yearList.map(String)],
    ...retentionRows.map((row) => ["", ...row]),
    [],
    [],
    ["", "Динамика по топ-продуктам"],
    ["", "Год", ...topProducts.slice(0, 5), "Другие"],
    ...yearProductRows.map((row) => ["", ...row]),
    [],
    [],
    ["", "ТЕПЛОВАЯ КАРТА: КАТЕГОРИЯ × ПРОДУКТ"],
    [],
    ["", "Категория", "Клиентов", ...topProducts],
    ...heatmapRows.slice(0, 20).map((row) => ["", ...row]),
  ];

  const categories = [
    ["Категории"],
    [`${categoryRows.length} ниш. Где сильнее, где живём дольше, что внутри`],
    [],
    ["Категория", "Проектов", "Доля", "Подкатегорий", "Топ-подкатегория", "Топ-продукт", `Активных в ${YEARS_ACTIVE_LABEL}`, "Ср. месяцев работы"],
    ...categoryRows,
    [],
    [],
    ["Подкатегории внутри топ-7 категорий"],
  ];
  for (const categoryRow of categoryRows.slice(0, 7)) {
    const category = categoryRow[0];
    const subRows = model.projectList
      .filter((project) => project.category === category)
      .reduce((map, project) => {
        inc(map, project.subcategory);
        return map;
      }, new Map());
    categories.push([], [category], ["Подкатегория", "Проектов"], ...[...subRows.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12).map(([name, count]) => [name, numberText(count)]));
  }

  const products = [
    ["Продукты"],
    [`${productRows.length} продуктов. Счёт идёт по уникальным проектам, не по суммам оплат`],
    [],
    ["Продукт", "Проектов всего", "Доля", "Топ-категория", ...model.yearList.map(String), "Δ 2024→2025"],
    ...productRows,
  ];

  const clients = [
    ["Клиенты"],
    [`${model.projectList.length} проектов · фильтруемые поля и статус активности`],
    [],
    ["Проект", "Категория", "Подкатегория", "Период", "Услуги", ...model.yearList.map(String), "Месяцев", "Поступлений", "Статус"],
    ...clientRows,
  ];

  const productClient = [
    ["Продукт", "Проект", "Категория", "Подкатегория", "Годы продукта", "Период продукта", "Годы сотрудничества", "Все продукты проекта", "Месяцев", "Поступлений", "Статус данных"],
    ...productClientRows,
  ];

  const classification = [
    ["Проект", "Категория", "Подкатегория", "Источник", "Строк в исходнике", "Строки исходника"],
    ...classificationRows,
  ];

  const data = [
    ["Техническая база вынесена в закрытый документ"],
    ["Эта вкладка не содержит сырых платежей и финансовых сумм."],
    [`Источник для дашборда: ${DEFAULT_DATABASE_URL}`],
    [`Последнее обновление, МСК: ${updated}`],
  ];

  const dashData = [
    ["Год", ...topProducts.slice(0, 5), "Другие"],
    ...yearProductRows,
    [],
    ["Категория", "Клиентов", ...topProducts],
    ...heatmapRows,
    [],
    ["Когорта", "Размер", ...model.yearList.map(String)],
    ...retentionRows,
    [],
    ["Продукт", "Проектов всего", ...model.yearList.map(String)],
    ...productRows.map((row) => [row[0], row[1], ...row.slice(4, 4 + model.yearList.length)]),
  ];

  return {
    [SHEETS.dashboard]: dashboard,
    [SHEETS.categories]: categories,
    [SHEETS.products]: products,
    [SHEETS.clients]: clients,
    [SHEETS.productClient]: productClient,
    [SHEETS.classification]: classification,
    [SHEETS.data]: data,
    [SHEETS.dashData]: dashData,
  };
}

function cellStyle({ backgroundColor, textColor, bold = false, fontSize = 10, horizontalAlignment = "LEFT", verticalAlignment = "MIDDLE" } = {}) {
  return {
    userEnteredFormat: {
      numberFormat: { type: "TEXT" },
      backgroundColor,
      horizontalAlignment,
      verticalAlignment,
      wrapStrategy: "WRAP",
      textFormat: { bold, fontSize, foregroundColor: textColor || { red: 0.098, green: 0.11, blue: 0.129 } },
    },
  };
}

function borderStyle(color = { red: 0.82, green: 0.855, blue: 0.902 }) {
  return { style: "SOLID", width: 1, color };
}

function widthRequests(sheetId, widths, fallbackCols) {
  const requests = widths.map((pixelSize, index) => ({
    updateDimensionProperties: {
      range: { sheetId, dimension: "COLUMNS", startIndex: index, endIndex: index + 1 },
      properties: { pixelSize },
      fields: "pixelSize",
    },
  }));
  if (widths.length < fallbackCols) {
    requests.push({
      updateDimensionProperties: {
        range: { sheetId, dimension: "COLUMNS", startIndex: widths.length, endIndex: fallbackCols },
        properties: { pixelSize: 130 },
        fields: "pixelSize",
      },
    });
  }
  return requests;
}

function headerRowIndex(title) {
  if ([SHEETS.categories, SHEETS.products, SHEETS.clients].includes(title)) return 3;
  return 0;
}

function tableWidths(title, cols) {
  if (title === SHEETS.categories) return [260, 95, 90, 125, 240, 150, 145, 140];
  if (title === SHEETS.products) return [140, 115, 90, 260, ...Array(Math.max(cols - 5, 1)).fill(82)];
  if (title === SHEETS.clients) return [240, 220, 220, 120, 320, ...Array(Math.max(cols - 8, 1)).fill(82), 90, 110, 105];
  if (title === SHEETS.productClient) return [140, 240, 210, 210, 210, 140, 210, 320, 95, 105, 130];
  if (title === SHEETS.classification) return [260, 220, 220, 150, 130, 180];
  return Array(cols).fill(150);
}

function styleRequests(sheetId, rows, cols, hidden, title) {
  const headerIndex = headerRowIndex(title);
  const visibleTable = !hidden && [SHEETS.categories, SHEETS.products, SHEETS.clients].includes(title);
  const requests = [
    { clearBasicFilter: { sheetId } },
    {
      updateSheetProperties: {
        properties: {
          sheetId,
          hidden: Boolean(hidden),
          gridProperties: {
            frozenRowCount: visibleTable ? headerIndex + 1 : (rows > 10 ? 1 : 0),
            rowCount: Math.max(rows + 30, 100),
            columnCount: Math.max(cols + 2, 12),
            hideGridlines: true,
          },
        },
        fields: "hidden,gridProperties(frozenRowCount,rowCount,columnCount,hideGridlines)",
      },
    },
    {
      repeatCell: {
        range: { sheetId, startRowIndex: 0, endRowIndex: Math.max(rows, 1), startColumnIndex: 0, endColumnIndex: Math.max(cols, 1) },
        cell: cellStyle({ backgroundColor: hidden ? { red: 0.98, green: 0.98, blue: 0.98 } : { red: 1, green: 1, blue: 1 }, verticalAlignment: "TOP" }),
        fields: "userEnteredFormat",
      },
    },
    {
      repeatCell: {
        range: { sheetId, startRowIndex: headerIndex, endRowIndex: headerIndex + 1, startColumnIndex: 0, endColumnIndex: Math.max(cols, 1) },
        cell: cellStyle({ backgroundColor: COLORS.header, textColor: COLORS.headerText, bold: true, horizontalAlignment: "CENTER" }),
        fields: "userEnteredFormat",
      },
    },
    {
      updateBorders: {
        range: { sheetId, startRowIndex: headerIndex, endRowIndex: Math.max(rows, headerIndex + 1), startColumnIndex: 0, endColumnIndex: Math.max(cols, 1) },
        top: borderStyle(),
        bottom: borderStyle(),
        left: borderStyle(),
        right: borderStyle(),
        innerHorizontal: borderStyle({ red: 0.9, green: 0.918, blue: 0.941 }),
        innerVertical: borderStyle({ red: 0.9, green: 0.918, blue: 0.941 }),
      },
    },
    ...widthRequests(sheetId, tableWidths(title, cols), Math.max(cols, 1)),
  ];
  if (visibleTable) {
    requests.push(
      {
        repeatCell: {
          range: { sheetId, startRowIndex: 0, endRowIndex: 1, startColumnIndex: 0, endColumnIndex: Math.min(cols, 8) },
          cell: cellStyle({ backgroundColor: { red: 1, green: 1, blue: 1 }, bold: true, fontSize: 18 }),
          fields: "userEnteredFormat",
        },
      },
      {
        repeatCell: {
          range: { sheetId, startRowIndex: 1, endRowIndex: 2, startColumnIndex: 0, endColumnIndex: Math.min(cols, 8) },
          cell: cellStyle({ backgroundColor: { red: 1, green: 1, blue: 1 }, textColor: { red: 0.392, green: 0.455, blue: 0.545 }, fontSize: 11 }),
          fields: "userEnteredFormat",
        },
      },
    );
  }
  if (rows > headerIndex + 1 && cols > 1) {
    requests.push({
      setBasicFilter: { filter: { range: { sheetId, startRowIndex: headerIndex, endRowIndex: rows, startColumnIndex: 0, endColumnIndex: cols } } },
    });
  }
  return requests;
}

function dashboardStyleRequests(sheetId, rows, cols) {
  const cardRanges = [
    { startColumnIndex: 1, endColumnIndex: 4 },
    { startColumnIndex: 5, endColumnIndex: 8 },
    { startColumnIndex: 9, endColumnIndex: 12 },
    { startColumnIndex: 13, endColumnIndex: 16 },
  ];
  const mergeRanges = [
    { startRowIndex: 1, endRowIndex: 2, startColumnIndex: 1, endColumnIndex: 10 },
    { startRowIndex: 2, endRowIndex: 3, startColumnIndex: 1, endColumnIndex: 10 },
    { startRowIndex: 4, endRowIndex: 5, startColumnIndex: 1, endColumnIndex: 15 },
    { startRowIndex: 5, endRowIndex: 6, startColumnIndex: 1, endColumnIndex: 15 },
    { startRowIndex: 6, endRowIndex: 7, startColumnIndex: 1, endColumnIndex: 15 },
    { startRowIndex: 7, endRowIndex: 8, startColumnIndex: 1, endColumnIndex: 15 },
    { startRowIndex: 15, endRowIndex: 16, startColumnIndex: 1, endColumnIndex: 8 },
    { startRowIndex: 15, endRowIndex: 16, startColumnIndex: 9, endColumnIndex: 16 },
    { startRowIndex: 25, endRowIndex: 26, startColumnIndex: 1, endColumnIndex: 16 },
  ];
  for (const range of cardRanges) {
    mergeRanges.push(
      { startRowIndex: 10, endRowIndex: 11, ...range },
      { startRowIndex: 11, endRowIndex: 12, ...range },
      { startRowIndex: 12, endRowIndex: 13, ...range },
    );
  }
  return [
    {
      unmergeCells: {
        range: { sheetId, startRowIndex: 0, endRowIndex: Math.max(rows, 80), startColumnIndex: 0, endColumnIndex: Math.max(cols, 16) },
      },
    },
    ...mergeRanges.map((range) => ({ mergeCells: { range: { sheetId, ...range }, mergeType: "MERGE_ALL" } })),
    {
      updateSheetProperties: {
        properties: { sheetId, hidden: false, gridProperties: { frozenRowCount: 0, rowCount: Math.max(rows + 20, 100), columnCount: Math.max(cols + 2, 16), hideGridlines: true } },
        fields: "hidden,gridProperties(frozenRowCount,rowCount,columnCount,hideGridlines)",
      },
    },
    {
      repeatCell: {
        range: { sheetId, startRowIndex: 0, endRowIndex: Math.max(rows, 1), startColumnIndex: 0, endColumnIndex: Math.max(cols, 1) },
        cell: cellStyle({ backgroundColor: { red: 0.973, green: 0.98, blue: 0.988 }, verticalAlignment: "TOP" }),
        fields: "userEnteredFormat",
      },
    },
    {
      repeatCell: {
        range: { sheetId, startRowIndex: 1, endRowIndex: 2, startColumnIndex: 1, endColumnIndex: 10 },
        cell: cellStyle({ backgroundColor: { red: 0.973, green: 0.98, blue: 0.988 }, bold: true, fontSize: 24 }),
        fields: "userEnteredFormat",
      },
    },
    {
      repeatCell: {
        range: { sheetId, startRowIndex: 2, endRowIndex: 3, startColumnIndex: 1, endColumnIndex: 10 },
        cell: cellStyle({ backgroundColor: { red: 0.973, green: 0.98, blue: 0.988 }, textColor: { red: 0.392, green: 0.455, blue: 0.545 }, fontSize: 11 }),
        fields: "userEnteredFormat",
      },
    },
    {
      repeatCell: {
        range: { sheetId, startRowIndex: 4, endRowIndex: 8, startColumnIndex: 1, endColumnIndex: 15 },
        cell: cellStyle({ backgroundColor: { red: 1, green: 1, blue: 1 }, fontSize: 11 }),
        fields: "userEnteredFormat",
      },
    },
    {
      repeatCell: {
        range: { sheetId, startRowIndex: 4, endRowIndex: 5, startColumnIndex: 1, endColumnIndex: 4 },
        cell: cellStyle({ backgroundColor: { red: 1, green: 1, blue: 1 }, bold: true, textColor: { red: 0.059, green: 0.231, blue: 0.443 } }),
        fields: "userEnteredFormat",
      },
    },
    ...cardRanges.flatMap((range) => [
      {
        repeatCell: {
          range: { sheetId, startRowIndex: 10, endRowIndex: 13, ...range },
          cell: cellStyle({ backgroundColor: { red: 1, green: 1, blue: 1 }, bold: true }),
          fields: "userEnteredFormat",
        },
      },
      {
        updateBorders: {
          range: { sheetId, startRowIndex: 10, endRowIndex: 13, ...range },
          top: borderStyle(),
          bottom: borderStyle(),
          left: borderStyle(),
          right: borderStyle(),
          innerHorizontal: borderStyle({ red: 0.9, green: 0.918, blue: 0.941 }),
          innerVertical: borderStyle({ red: 1, green: 1, blue: 1 }),
        },
      },
    ]),
    {
      repeatCell: {
        range: { sheetId, startRowIndex: 15, endRowIndex: 17, startColumnIndex: 1, endColumnIndex: 15 },
        cell: cellStyle({ backgroundColor: { red: 0.973, green: 0.98, blue: 0.988 }, bold: true, textColor: { red: 0.059, green: 0.231, blue: 0.443 } }),
        fields: "userEnteredFormat",
      },
    },
    {
      repeatCell: {
        range: { sheetId, startRowIndex: 16, endRowIndex: 17, startColumnIndex: 1, endColumnIndex: 15 },
        cell: cellStyle({ backgroundColor: COLORS.header, textColor: COLORS.headerText, bold: true, horizontalAlignment: "CENTER" }),
        fields: "userEnteredFormat",
      },
    },
    {
      repeatCell: {
        range: { sheetId, startRowIndex: 17, endRowIndex: Math.min(rows, 28), startColumnIndex: 1, endColumnIndex: 8 },
        cell: cellStyle({ backgroundColor: { red: 1, green: 1, blue: 1 }, fontSize: 10, horizontalAlignment: "CENTER" }),
        fields: "userEnteredFormat",
      },
    },
    {
      repeatCell: {
        range: { sheetId, startRowIndex: 25, endRowIndex: 27, startColumnIndex: 1, endColumnIndex: 15 },
        cell: cellStyle({ backgroundColor: { red: 0.973, green: 0.98, blue: 0.988 }, bold: true, textColor: { red: 0.059, green: 0.231, blue: 0.443 } }),
        fields: "userEnteredFormat",
      },
    },
    {
      repeatCell: {
        range: { sheetId, startRowIndex: 27, endRowIndex: 28, startColumnIndex: 1, endColumnIndex: 15 },
        cell: cellStyle({ backgroundColor: COLORS.header, textColor: COLORS.headerText, bold: true, horizontalAlignment: "CENTER" }),
        fields: "userEnteredFormat",
      },
    },
    {
      updateBorders: {
        range: { sheetId, startRowIndex: 16, endRowIndex: Math.min(rows, 25), startColumnIndex: 1, endColumnIndex: Math.min(cols, 15) },
        top: borderStyle(),
        bottom: borderStyle(),
        left: borderStyle(),
        right: borderStyle(),
        innerHorizontal: borderStyle({ red: 0.9, green: 0.918, blue: 0.941 }),
        innerVertical: borderStyle({ red: 0.9, green: 0.918, blue: 0.941 }),
      },
    },
    {
      updateBorders: {
        range: { sheetId, startRowIndex: 27, endRowIndex: Math.min(rows, 50), startColumnIndex: 1, endColumnIndex: Math.min(cols, 15) },
        top: borderStyle(),
        bottom: borderStyle(),
        left: borderStyle(),
        right: borderStyle(),
        innerHorizontal: borderStyle({ red: 0.9, green: 0.918, blue: 0.941 }),
        innerVertical: borderStyle({ red: 0.9, green: 0.918, blue: 0.941 }),
      },
    },
    ...widthRequests(sheetId, [28, 250, 118, 118, 26, 118, 118, 118, 26, 250, 118, 118, 26, 250, 118, 118], Math.max(cols, 16)),
    ...[24, 44, 28, 14, 28, 32, 32, 32, 14, 16, 34, 38, 34, 14, 16, 30, ...Array(12).fill(30), 14, 14, 26, ...Array(12).fill(26)].map((pixelSize, index) => ({
      updateDimensionProperties: {
        range: { sheetId, dimension: "ROWS", startIndex: index, endIndex: index + 1 },
        properties: { pixelSize },
        fields: "pixelSize",
      },
    })),
  ];
}

async function dashboardChartDeleteRequests(spreadsheetId, token, dashboardSheetId) {
  const payload = await fetchJson(
    `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}?includeGridData=false&fields=sheets(properties(sheetId),charts(chartId))`,
    token,
  );
  const dashboard = (payload.sheets || []).find((sheet) => sheet.properties?.sheetId === dashboardSheetId);
  return (dashboard?.charts || []).map((chart) => ({ deleteEmbeddedObject: { objectId: chart.chartId } }));
}

function dashboardChartRequests(dashboardSheetId, dashDataSheetId) {
  return [
    {
      addChart: {
        chart: {
          spec: {
            title: "Динамика портфолио по годам",
            basicChart: {
              chartType: "LINE",
              legendPosition: "RIGHT_LEGEND",
              headerCount: 1,
              axis: [
                { position: "BOTTOM_AXIS", title: "Год" },
                { position: "LEFT_AXIS", title: "Проектов" },
              ],
              domains: [
                {
                  domain: {
                    sourceRange: {
                      sources: [
                        { sheetId: dashDataSheetId, startRowIndex: 0, endRowIndex: 12, startColumnIndex: 0, endColumnIndex: 1 },
                      ],
                    },
                  },
                },
              ],
              series: [1, 2, 3, 4, 5, 6].map((columnIndex) => ({
                series: {
                  sourceRange: {
                    sources: [
                      { sheetId: dashDataSheetId, startRowIndex: 0, endRowIndex: 12, startColumnIndex: columnIndex, endColumnIndex: columnIndex + 1 },
                    ],
                  },
                },
                targetAxis: "LEFT_AXIS",
              })),
            },
          },
          position: {
            overlayPosition: {
              anchorCell: { sheetId: dashboardSheetId, rowIndex: 16, columnIndex: 9 },
              offsetXPixels: 10,
              offsetYPixels: 8,
              widthPixels: 760,
              heightPixels: 330,
            },
          },
        },
      },
    },
  ];
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const databaseId = extractSheetId(args.databaseUrl);
  const dashboardId = extractSheetId(args.dashboardUrl);
  if (!databaseId) throw new Error("Не удалось извлечь id базы портфолио.");
  if (!dashboardId) throw new Error("Не удалось извлечь id визуального дашборда.");

  const serviceAccount = JSON.parse(await readFile(args.serviceAccountPath, "utf8"));
  const token = await fetchAccessToken(serviceAccount);
  const dataRows = await valuesGet(databaseId, token, `${quoteSheetTitle(DATABASE_SHEET)}!A:H`);
  const classificationRows = await valuesGet(dashboardId, token, `${quoteSheetTitle(SHEETS.classification)}!A:F`);
  const model = enrichModel(buildModel(dataRows, classificationRows));
  const sheets = buildSheets(model);
  const hiddenSheets = new Set([SHEETS.productClient, SHEETS.classification, SHEETS.data, SHEETS.dashData]);

  if (!args.dryRun) {
    const sheetIds = await ensureSheets(dashboardId, token, Object.entries(sheets).map(([title, grid]) => ({
      title,
      rows: grid.length,
      cols: Math.max(...grid.map((row) => row.length), 1),
      hidden: hiddenSheets.has(title),
    })));
    for (const [title, grid] of Object.entries(sheets)) {
      const cols = Math.max(...grid.map((row) => row.length), 1);
      await valuesClear(dashboardId, token, title, Math.max(grid.length + 500, 2000), Math.max(cols + 5, 40));
      await valuesUpdate(dashboardId, token, title, grid);
      const style = title === SHEETS.dashboard
        ? dashboardStyleRequests(sheetIds.get(title), grid.length, cols)
        : styleRequests(sheetIds.get(title), grid.length, cols, hiddenSheets.has(title), title);
      await batchUpdate(dashboardId, token, style);
    }
    await batchUpdate(dashboardId, token, [
      ...(await dashboardChartDeleteRequests(dashboardId, token, sheetIds.get(SHEETS.dashboard))),
      ...dashboardChartRequests(sheetIds.get(SHEETS.dashboard), sheetIds.get(SHEETS.dashData)),
    ]);
  }

  console.log(JSON.stringify({
    ok: true,
    dryRun: args.dryRun,
    database: args.databaseUrl,
    dashboard: args.dashboardUrl,
    projects: model.projectList.length,
    categories: buildCategoryRows(model).length,
    products: buildProductRows(model).length,
    years: model.yearList,
    missingClassification: model.projectList.filter((project) => project.classification.source === "нет классификации").length,
    updatedAtMsk: nowMsk(),
  }, null, 2));
}

main().catch((error) => {
  console.error(String(error?.message || error || "unknown error"));
  process.exit(1);
});
