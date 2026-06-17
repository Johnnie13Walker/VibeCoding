#!/usr/bin/env node
import { createSign } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";

const DEFAULT_SOURCE_URL = "https://docs.google.com/spreadsheets/d/17SBisFgKrf3hRP_zjVPC2e4wMzlq8j8HDC2bvkyS74Y/edit?gid=1482533080#gid=1482533080";
const DEFAULT_TARGET_URL = "https://docs.google.com/spreadsheets/d/1TSEei_ncr3SQmiYT074Q17HOzmxxtrPV447j27N_BZw/edit?gid=1955270606#gid=1955270606";
const DEFAULT_SA_PATH = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json";

const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SCOPE = "https://www.googleapis.com/auth/spreadsheets";
const TARGET_SHEET_TITLE = "Клиенты";
const HEADER_ROW_INDEX_1 = 13;
const DATA_START_ROW_INDEX_1 = 14;
const TARGET_COLUMNS = [
  "Проект",
  "Категория",
  "Подкатегория",
  "Услуги",
  "Годы",
  "Период",
  "Последний год",
  "Статус",
  "Бренд",
  "Опыт, мес.",
  "Сайт активен",
  "2021",
  "2022",
  "2023",
  "2024",
  "2025",
  "2026",
];
const SOURCE_COLUMNS = {
  project: ["проект", "проект/сайт", "site", "сайт"],
  service: ["услуга", "продукт"],
  brand: ["бренд"],
  year: ["год"],
  month: ["месяц", "месяц оплаты"],
  paidAt: ["дата оплаты"],
  department: ["отдел"],
  newOld: ["new/old", "new old"],
};
const DEFAULT_EXCLUDED_PROJECTS = ["saturnia.ru"];
const DEFAULT_EXCLUDED_SERVICES = ["agency", "service", "services", "эдженси", "сервисес"];
const PROJECT_CLASSIFICATION_OVERRIDES = new Map([
  ["1c-bitrix.ru", ["IT и телеком", "Разработка ПО"]],
  ["calltouch.ru", ["IT и телеком", "Аналитика и BI"]],
  ["elama.ru", ["Маркетинг и медиа", "Маркетинг"]],
  ["shop.ccc.eu/ru", ["Ритейл и e-commerce", "E-commerce"]],
]);

function parseArgs(argv) {
  const args = {
    dryRun: false,
    sourceUrl: process.env.PORTFOLIO_SOURCE_SHEET_URL || DEFAULT_SOURCE_URL,
    targetUrl: process.env.PORTFOLIO_CLIENTS_SHEET_URL || process.env.PORTFOLIO_DASHBOARD_SHEET_URL || DEFAULT_TARGET_URL,
    targetSheetTitle: process.env.PORTFOLIO_CLIENTS_SHEET_TITLE || TARGET_SHEET_TITLE,
    serviceAccountPath: process.env.PORTFOLIO_GOOGLE_SERVICE_ACCOUNT_JSON
      || process.env.MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON
      || process.env.GOOGLE_SERVICE_ACCOUNT_JSON
      || DEFAULT_SA_PATH,
    reportPath: process.env.PORTFOLIO_CLIENTS_REPORT_JSON || "",
    excludedProjects: (process.env.PORTFOLIO_CLIENTS_EXCLUDE_PROJECTS || DEFAULT_EXCLUDED_PROJECTS.join(","))
      .split(",")
      .map((value) => normalizeProject(value))
      .filter(Boolean),
    excludedServices: (process.env.PORTFOLIO_CLIENTS_EXCLUDE_SERVICES || DEFAULT_EXCLUDED_SERVICES.join(","))
      .split(",")
      .map((value) => normalizeServiceKey(value))
      .filter(Boolean),
  };

  for (let index = 0; index < argv.length; index += 1) {
    const token = String(argv[index] || "");
    const next = String(argv[index + 1] || "");
    if (token === "--dry-run") {
      args.dryRun = true;
    } else if (token === "--source-url") {
      args.sourceUrl = next;
      index += 1;
    } else if (token === "--target-url") {
      args.targetUrl = next;
      index += 1;
    } else if (token === "--target-sheet") {
      args.targetSheetTitle = next;
      index += 1;
    } else if (token === "--service-account") {
      args.serviceAccountPath = next;
      index += 1;
    } else if (token === "--report-json") {
      args.reportPath = next;
      index += 1;
    }
  }
  return args;
}

function base64url(input) {
  return Buffer.from(input).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function extractSpreadsheetId(url) {
  const match = String(url || "").match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
  return match ? match[1] : "";
}

function extractGid(url) {
  const match = String(url || "").match(/[?#&]gid=(\d+)/);
  return match ? Number(match[1]) : null;
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

function normalizeHeader(value) {
  return String(value ?? "").replace(/\s+/g, " ").trim().toLowerCase();
}

function cleanText(value) {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

function safeSheetText(value) {
  const text = cleanText(value);
  return /^[=+\-]/.test(text) ? `'${text}` : text;
}

function normalizeProject(value) {
  return cleanText(value)
    .toLowerCase()
    .replace(/^https?:\/\//, "")
    .replace(/^www\./, "")
    .replace(/\/+$/, "")
    .replace(/^@/, "instagram:");
}

function hasPortfolioProjectPointer(value) {
  const project = cleanText(value).toLowerCase();
  if (!project) return false;
  if (project.startsWith("@")) return true;
  if (/^https?:\/\//.test(project)) return true;
  if (project.includes("youtube.com") || project.includes("youtu.be") || project.includes("instagram.com")) return true;
  if (/\s/.test(project)) return false;
  return project.includes(".") && /^[\p{L}0-9][\p{L}0-9._/-]*$/u.test(project);
}

function normalizeService(value) {
  return cleanText(value).replace(/[Сс]EO/g, "SEO");
}

function normalizeServiceKey(value) {
  return normalizeService(value)
    .toLowerCase()
    .replace(/[с]/g, "c")
    .replace(/[е]/g, "e")
    .replace(/\s+/g, "");
}

function isExcludedService(service, excludedServices) {
  return excludedServices.includes(normalizeServiceKey(service));
}

function toYear(value) {
  const match = cleanText(value).match(/20\d{2}/);
  return match ? Number(match[0]) : 0;
}

function toMonth(value) {
  const text = cleanText(value).toLowerCase();
  const number = Number(text.replace(",", "."));
  if (Number.isFinite(number) && number >= 1 && number <= 12) return Math.trunc(number);
  const names = new Map([
    ["январ", 1],
    ["феврал", 2],
    ["март", 3],
    ["апрел", 4],
    ["ма", 5],
    ["июн", 6],
    ["июл", 7],
    ["август", 8],
    ["сентябр", 9],
    ["октябр", 10],
    ["ноябр", 11],
    ["декабр", 12],
  ]);
  for (const [prefix, month] of names) {
    if (text.startsWith(prefix)) return month;
  }
  return 0;
}

function periodFromYears(years) {
  if (!years.length) return "";
  const sorted = [...years].sort((a, b) => a - b);
  return sorted[0] === sorted[sorted.length - 1] ? String(sorted[0]) : `${sorted[0]}-${sorted[sorted.length - 1]}`;
}

function periodFromItems(items) {
  const years = [];
  for (const item of items) {
    for (const year of item.years) {
      if (year) years.push(year);
    }
  }
  return periodFromYears([...new Set(years)]);
}

function statusByYear(maxYear) {
  if (maxYear >= 2026) return "Активен";
  if (maxYear === 2025) return "Спящий";
  if (maxYear > 0) return "Архив";
  return "Не определено";
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
  if (!response.ok) throw new Error(`Sheets API error: ${response.status} ${JSON.stringify(payload)}`);
  return payload;
}

async function valuesGet(spreadsheetId, token, range) {
  const payload = await fetchJson(
    `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}?majorDimension=ROWS`,
    token,
  );
  return payload.values || [];
}

async function batchUpdate(spreadsheetId, token, requests) {
  if (!requests.length) return {};
  return fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}:batchUpdate`, token, {
    method: "POST",
    body: JSON.stringify({ requests }),
  });
}

async function metadata(spreadsheetId, token) {
  return fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}?includeGridData=false`, token);
}

function sheetTitleByGid(meta, gid, fallbackTitle) {
  if (gid !== null) {
    const sheet = (meta.sheets || []).find((entry) => Number(entry.properties.sheetId) === Number(gid));
    if (sheet) return sheet.properties.title;
  }
  if (fallbackTitle) return fallbackTitle;
  const first = (meta.sheets || [])[0];
  return first?.properties?.title || "";
}

function getColumnIndex(headerMap, candidates) {
  for (const candidate of candidates) {
    const index = headerMap.get(normalizeHeader(candidate));
    if (index !== undefined) return index;
  }
  return -1;
}

function sourceIndexMap(headers) {
  const headerMap = new Map(headers.map((header, index) => [normalizeHeader(header), index]));
  const result = {};
  for (const [key, candidates] of Object.entries(SOURCE_COLUMNS)) {
    result[key] = getColumnIndex(headerMap, candidates);
  }
  const required = ["project", "service", "brand", "year", "month", "paidAt", "department"];
  const missing = required.filter((key) => result[key] < 0);
  if (missing.length) throw new Error(`В источнике не найдены безопасные колонки: ${missing.join(", ")}`);
  return result;
}

async function readSourceRows(sourceSpreadsheetId, token, sourceTitle, excludedServices = []) {
  const rows = await valuesGet(sourceSpreadsheetId, token, `${quoteSheetTitle(sourceTitle)}!A1:AR`);
  const headers = rows[0] || [];
  const idx = sourceIndexMap(headers);
  const grouped = new Map();

  for (const row of rows.slice(1)) {
    const service = normalizeService(row[idx.service]);
    if (!service || isExcludedService(service, excludedServices)) continue;
    const project = cleanText(row[idx.project]);
    if (!project) continue;
    const key = normalizeProject(project);
    if (!grouped.has(key)) {
      grouped.set(key, {
        project,
        services: new Set(),
        years: new Set(),
        months: new Set(),
        brands: new Map(),
        yearServices: new Map(),
      });
    }
    const item = grouped.get(key);
    const year = toYear(row[idx.year]);
    const month = toMonth(row[idx.month]);
    const brand = cleanText(row[idx.brand]);
    if (service) item.services.add(service);
    if (year) item.years.add(year);
    if (year && month) item.months.add(`${year}-${String(month).padStart(2, "0")}`);
    if (brand) item.brands.set(brand, (item.brands.get(brand) || 0) + 1);
    if (year && service) {
      if (!item.yearServices.has(year)) item.yearServices.set(year, new Set());
      item.yearServices.get(year).add(service);
    }
  }
  return grouped;
}

async function readTargetRows(targetSpreadsheetId, token, targetTitle) {
  const range = `${quoteSheetTitle(targetTitle)}!A${HEADER_ROW_INDEX_1}:Q1000`;
  const rows = await valuesGet(targetSpreadsheetId, token, range);
  const dataRows = rows.slice(1).filter((row) => cleanText(row[0]));
  const existing = new Map();
  const classifications = [];
  dataRows.forEach((row, index) => {
    const project = cleanText(row[0]);
    const category = cleanText(row[1]);
    const subcategory = cleanText(row[2]);
    if (project) existing.set(normalizeProject(project), { row, rowIndex1: DATA_START_ROW_INDEX_1 + index });
    if (project && category && subcategory && category !== "Не определено") {
      classifications.push({ project, category, subcategory });
    }
  });
  return {
    rows,
    dataRows,
    existing,
    classifications,
    lastDataRowIndex1: HEADER_ROW_INDEX_1 + dataRows.length,
  };
}

function mostFrequent(map) {
  return [...map.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "ru"))[0]?.[0] || "";
}

function needsBrandFill(value) {
  const text = cleanText(value).toLowerCase();
  return !text || text === "не определено";
}

function siteCandidates(project) {
  const value = cleanText(project);
  if (!value) return [];
  if (value.startsWith("@")) {
    const handle = value.slice(1).trim();
    return handle ? [`https://www.instagram.com/${handle}/`] : [];
  }
  const originalUrl = /^https?:\/\//i.test(value) ? value : `https://${value}`;
  const withoutProtocol = value.replace(/^https?:\/\//i, "");
  const domain = withoutProtocol.replace(/\/.*$/, "").replace(/^www\./i, "");
  if (!domain.includes(".")) return [];
  return [
    originalUrl,
    `https://${domain}`,
    `https://www.${domain}`,
    `http://${domain}`,
    `http://www.${domain}`,
  ];
}

async function fetchSite(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(url, {
      redirect: "follow",
      signal: controller.signal,
      headers: {
        "user-agent": "Mozilla/5.0 (compatible; CloudbotPortfolio/1.0)",
        accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      },
    });
    const text = await response.text().catch(() => "");
    return {
      ok: response.status >= 200 && response.status < 500,
      status: response.status,
      url: response.url || url,
      text: text.slice(0, 300000),
    };
  } catch (error) {
    return { ok: false, status: 0, url, text: "", error: String(error?.message || error) };
  } finally {
    clearTimeout(timer);
  }
}

async function checkSite(project) {
  const candidates = siteCandidates(project);
  for (const candidate of candidates) {
    const result = await fetchSite(candidate);
    if (!result.ok) continue;
    if (String(project).startsWith("@")) {
      const handle = String(project).slice(1).toLowerCase();
      const page = result.text.toLowerCase();
      const missing = page.includes("sorry, this page") || page.includes("страница недоступна");
      if (!page.includes(handle) || missing) continue;
    }
    return { active: "Да", url: result.url, status: result.status, text: result.text };
  }
  return { active: "Нет", url: candidates[0] || "", status: 0, text: "" };
}

async function mapConcurrent(items, limit, worker) {
  const results = Array(items.length);
  let nextIndex = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (nextIndex < items.length) {
      const currentIndex = nextIndex;
      nextIndex += 1;
      results[currentIndex] = await worker(items[currentIndex], currentIndex);
    }
  });
  await Promise.all(workers);
  return results;
}

function classifyByText(project, pageText, classifications) {
  const text = `${project} ${pageText}`.toLowerCase();
  const override = PROJECT_CLASSIFICATION_OVERRIDES.get(normalizeProject(project).replace("instagram:", "@"));
  if (override) return { category: override[0], subcategory: override[1] };
  const existingExact = classifications.find((item) => {
    const root = normalizeProject(item.project).split(".").slice(-2).join(".");
    return root && normalizeProject(project).includes(root);
  });
  if (existingExact) return { category: existingExact.category, subcategory: existingExact.subcategory };

  const projectText = String(project).toLowerCase();
  const titleMatch = pageText.match(/<title[^>]*>(.*?)<\/title>/i);
  const metaDescriptionMatch = pageText.match(/<meta[^>]+name=["']description["'][^>]+content=["']([^"']+)/i);
  const compactText = `${projectText} ${titleMatch?.[1] || ""} ${metaDescriptionMatch?.[1] || ""}`.toLowerCase();
  const medicalClassification = classifyMedicalByText(compactText);
  if (medicalClassification) return medicalClassification;
  const rules = [
    [/фарма|аптек|лекарств|медиздел|medical device/i, "Фармацевтика и медизделия", "Медизделия"],
    [/недвиж|жк|жилой комплекс|квартир|девелоп|строит/i, "Недвижимость", "Жилой комплекс"],
    [/авто|akpp|шина|дилер|машин|тюнинг|сервис/i, "Авто", "Авто"],
    [/\b(it|cloud|software|saas|data|bi|ai)\b|облач|аналитик|телеком|искусствен|битрикс/i, "IT и телеком", "Разработка ПО"],
    [/маркетинг|media|реклам|продакшн|smm|digital/i, "Маркетинг и медиа", "Маркетинг"],
    [/туризм|отель|hotel|restaurant|ресторан|кафе|horeca/i, "Туризм и HoReCa", "HoReCa"],
    [/банк|финанс|страхов|кредит|инвест/i, "Финансы и страхование", "Финансы"],
    [/красот|wellness|spa|космет|салон/i, "Красота и wellness", "Косметология"],
    [/мебел|интерьер|дизайн/i, "Мебель и интерьер", "Мебель"],
    [/еда|пищ|продукт|напит/i, "Пищевая отрасль", "Продукты питания"],
    [/логист|достав|транспорт/i, "Логистика", "Логистика"],
    [/безопас|охран|security/i, "Безопасность", "Безопасность"],
    [/образован|школ|университет|курс/i, "Образование", "Образование"],
    [/промышлен|завод|производств|оборудован/i, "Промышленность и производство", "Промышленное оборудование"],
  ];
  for (const [pattern, category, subcategory] of rules) {
    if (pattern.test(compactText)) return { category, subcategory };
  }
  return { category: "Не определено", subcategory: "Не определено" };
}

function classifyMedicalByText(text) {
  const normalized = String(text || "").toLowerCase().replace(/ё/g, "е");
  const profileRules = [
    [/стоматолог|стомат|дентал|stomat|dental|dent|ортодонт|ortodont|имплант|зубн|зуботех/i, "Стоматология"],
    [/ветеринар|ветклиник|\bвет\b/i, "Ветеринарная клиника"],
    [/эко|репродукт|репрод|reprod|фертил|ivf/i, "Репродуктивная клиника / ЭКО"],
    [/лаборатор|анализ/i, "Лаборатория"],
    [/диагност|мрт|кт\b|узи|томограф/i, "Диагностический центр"],
    [/пластическ|блефаропласт|маммопласт|ринопласт|фейслифт|липосакц/i, "Пластическая хирургия"],
    [/космет|эстетическ|дермат|лазер|эпиляц|skin|sculptra|beauty/i, "Косметология"],
    [/офтальм|зрен|глаз/i, "Офтальмология"],
    [/\bлор\b|_lor|lor_|lor-|@lor|отоларинг|(^|[^a-zа-я])lor([^a-zа-я]|$)/i, "ЛОР-клиника"],
    [/ортопед|травмат|сустав|колен|позвоноч|спин|osteopol|остеопат/i, "Ортопедия и травматология"],
    [/невро|невролог/i, "Неврология"],
    [/кардио|сердц/i, "Кардиология"],
    [/флеб|вен\b|варикоз/i, "Флебология"],
    [/онко|рак\b|опухол/i, "Онкология"],
    [/уролог/i, "Урология"],
    [/гинеколог|гинекология|акушер/i, "Гинекология"],
    [/педиатр|детск|ребен|дети|подрост|teen|baby/i, "Педиатрия"],
    [/псих|психиатр|психотерап/i, "Психотерапия / психиатрия"],
    [/нарко|зависим|алкогол|нарколог|nazaraliev/i, "Наркология"],
    [/реабилит|восстанов|rehab|head-and-hands|spine-restore|autonomiya|blagorc|hrs18|promedmove|naminov/i, "Реабилитационный центр"],
    [/санатор/i, "Санаторий"],
  ];
  for (const [pattern, subcategory] of profileRules) {
    if (pattern.test(normalized)) return { category: "Медицина", subcategory };
  }
  if (/клиник|clinic|klinika|медик|медицин|(^|[^a-z])med|диагност|лечение|health/i.test(normalized)) {
    return { category: "Медицина", subcategory: "Медицинский центр" };
  }
  if (/doctor|доктор|врач/i.test(normalized)) {
    return { category: "Медицина", subcategory: "Врач" };
  }
  return null;
}

function buildRow(item, siteCheck, classification) {
  const years = [...item.years].sort((a, b) => a - b);
  const maxYear = years[years.length - 1] || 0;
  const services = [...item.services].sort((a, b) => a.localeCompare(b, "ru"));
  const row = Array(TARGET_COLUMNS.length).fill("");
  row[0] = safeSheetText(item.project);
  row[1] = classification.category;
  row[2] = classification.subcategory;
  row[3] = services.join(", ");
  row[4] = years.join(", ");
  row[5] = periodFromYears(years);
  row[6] = maxYear ? String(maxYear) : "";
  row[7] = statusByYear(maxYear);
  row[8] = mostFrequent(item.brands);
  row[9] = String(item.months.size || item.years.size || "");
  row[10] = siteCheck.active;
  for (let year = 2021; year <= 2026; year += 1) {
    row[10 + (year - 2020)] = [...(item.yearServices.get(year) || [])].sort((a, b) => a.localeCompare(b, "ru")).join(", ");
  }
  return row;
}

function existingSafeRow(item) {
  const row = buildRow(item, { active: "" }, { category: "", subcategory: "" });
  return [
    ...row.slice(3, 10),
    ...row.slice(11, 17),
  ];
}

function existingSafeValues(row) {
  return [
    row[3] || "",
    row[4] || "",
    row[5] || "",
    row[6] || "",
    row[7] || "",
    row[8] || "",
    row[9] || "",
    row[11] || "",
    row[12] || "",
    row[13] || "",
    row[14] || "",
    row[15] || "",
    row[16] || "",
  ].map((value) => String(value ?? ""));
}

function cellData(row, siteUrl) {
  return row.map((value, index) => {
    const cell = { userEnteredValue: { stringValue: String(value ?? "") } };
    if (index === 0 && siteUrl) {
      cell.userEnteredFormat = { textFormat: { link: { uri: siteUrl } } };
    }
    return cell;
  });
}

async function appendRows(targetSpreadsheetId, token, sheetId, lastDataRowIndex1, rows, periodLabel) {
  if (!rows.length) return;
  const insertStart = lastDataRowIndex1;
  const insertEnd = lastDataRowIndex1 + rows.length;
  await batchUpdate(targetSpreadsheetId, token, [
    {
      insertDimension: {
        range: { sheetId, dimension: "ROWS", startIndex: insertStart, endIndex: insertEnd },
        inheritFromBefore: true,
      },
    },
    {
      copyPaste: {
        source: {
          sheetId,
          startRowIndex: lastDataRowIndex1 - 1,
          endRowIndex: lastDataRowIndex1,
          startColumnIndex: 0,
          endColumnIndex: TARGET_COLUMNS.length,
        },
        destination: {
          sheetId,
          startRowIndex: insertStart,
          endRowIndex: insertEnd,
          startColumnIndex: 0,
          endColumnIndex: TARGET_COLUMNS.length,
        },
        pasteType: "PASTE_FORMAT",
        pasteOrientation: "NORMAL",
      },
    },
    {
      updateCells: {
        range: {
          sheetId,
          startRowIndex: insertStart,
          endRowIndex: insertEnd,
          startColumnIndex: 0,
          endColumnIndex: TARGET_COLUMNS.length,
        },
        rows: rows.map(({ row, siteUrl }) => ({ values: cellData(row, siteUrl) })),
        fields: "userEnteredValue,userEnteredFormat.textFormat.link",
      },
    },
    {
      setBasicFilter: {
        filter: {
          range: {
            sheetId,
            startRowIndex: HEADER_ROW_INDEX_1 - 1,
            endRowIndex: insertEnd,
            startColumnIndex: 0,
            endColumnIndex: TARGET_COLUMNS.length,
          },
        },
      },
    },
    {
      setDataValidation: {
        range: {
          sheetId,
          startRowIndex: insertStart,
          endRowIndex: insertEnd,
          startColumnIndex: 10,
          endColumnIndex: 11,
        },
        rule: {
          condition: {
            type: "ONE_OF_LIST",
            values: [
              { userEnteredValue: "Да" },
              { userEnteredValue: "Нет" },
            ],
          },
          strict: true,
          showCustomUi: true,
        },
      },
    },
    {
      updateCells: {
        range: {
          sheetId,
          startRowIndex: 2,
          endRowIndex: 3,
          startColumnIndex: 0,
          endColumnIndex: 11,
        },
        rows: [{
          values: [
            { userEnteredValue: { stringValue: "Кейсов" } },
            { userEnteredValue: { formulaValue: "=COUNTA(A14:A)" } },
            { userEnteredValue: { stringValue: "Активные 2026" } },
            { userEnteredValue: { formulaValue: "=COUNTIF(H14:H;\"Активен\")" } },
            {},
            { userEnteredValue: { stringValue: "Категорий" } },
            { userEnteredValue: { formulaValue: "=COUNTA(UNIQUE(FILTER(B14:B;B14:B<>\"\")))" } },
            { userEnteredValue: { stringValue: "Услуг" } },
            { userEnteredValue: { formulaValue: "=COUNTA(UNIQUE(TRANSPOSE(SPLIT(TEXTJOIN(\", \";TRUE;D14:D);\", \"))))" } },
            { userEnteredValue: { stringValue: "Период" } },
            { userEnteredValue: { stringValue: periodLabel || "2021-2026" } },
          ],
        }],
        fields: "userEnteredValue",
      },
    },
  ]);
}

async function updateExistingSafeRows(targetSpreadsheetId, token, sheetId, updates) {
  if (!updates.length) return;
  const requests = updates.flatMap((update) => [
    {
      updateCells: {
        range: {
          sheetId,
          startRowIndex: update.rowIndex1 - 1,
          endRowIndex: update.rowIndex1,
          startColumnIndex: 3,
          endColumnIndex: 10,
        },
        rows: [{ values: update.row.slice(0, 7).map((value) => ({ userEnteredValue: { stringValue: String(value ?? "") } })) }],
        fields: "userEnteredValue",
      },
    },
    {
      updateCells: {
        range: {
          sheetId,
          startRowIndex: update.rowIndex1 - 1,
          endRowIndex: update.rowIndex1,
          startColumnIndex: 11,
          endColumnIndex: 17,
        },
        rows: [{ values: update.row.slice(7).map((value) => ({ userEnteredValue: { stringValue: String(value ?? "") } })) }],
        fields: "userEnteredValue",
      },
    },
  ]);
  await batchUpdate(targetSpreadsheetId, token, requests);
}

async function updateExistingBrands(targetSpreadsheetId, token, sheetId, updates) {
  if (!updates.length) return;
  await batchUpdate(targetSpreadsheetId, token, updates.map((update) => ({
    updateCells: {
      range: {
        sheetId,
        startRowIndex: update.rowIndex1 - 1,
        endRowIndex: update.rowIndex1,
        startColumnIndex: 8,
        endColumnIndex: 9,
      },
      rows: [{ values: [{ userEnteredValue: { stringValue: update.brand } }] }],
      fields: "userEnteredValue",
    },
  })));
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const sourceSpreadsheetId = extractSpreadsheetId(args.sourceUrl);
  const targetSpreadsheetId = extractSpreadsheetId(args.targetUrl);
  if (!sourceSpreadsheetId) throw new Error("Не удалось извлечь id исходной таблицы.");
  if (!targetSpreadsheetId) throw new Error("Не удалось извлечь id таблицы портфолио.");

  const serviceAccount = JSON.parse(await readFile(args.serviceAccountPath, "utf8"));
  const token = await fetchAccessToken(serviceAccount);
  const sourceMeta = await metadata(sourceSpreadsheetId, token);
  const sourceTitle = sheetTitleByGid(sourceMeta, extractGid(args.sourceUrl), "Продажи");
  const targetMeta = await metadata(targetSpreadsheetId, token);
  const targetSheet = (targetMeta.sheets || []).find((sheet) => sheet.properties.title === args.targetSheetTitle);
  if (!targetSheet) throw new Error(`Вкладка портфолио не найдена: ${args.targetSheetTitle}`);

  const sourceRows = await readSourceRows(sourceSpreadsheetId, token, sourceTitle, args.excludedServices);
  const targetRows = await readTargetRows(targetSpreadsheetId, token, args.targetSheetTitle);
  const skippedProjectsWithoutPointer = [...sourceRows.values()]
    .filter((item) => !hasPortfolioProjectPointer(item.project))
    .map((item) => item.project)
    .sort((a, b) => normalizeProject(a).localeCompare(normalizeProject(b), "ru"));
  const candidates = [...sourceRows.entries()]
    .filter(([key, item]) => hasPortfolioProjectPointer(item.project) && !targetRows.existing.has(key) && !args.excludedProjects.includes(key))
    .map(([, item]) => item)
    .sort((a, b) => normalizeProject(a.project).localeCompare(normalizeProject(b.project), "ru"));
  const safeRowUpdates = [...sourceRows.entries()]
    .map(([key, item]) => {
      const existing = targetRows.existing.get(key);
      if (!existing) return null;
      const row = existingSafeRow(item);
      if (JSON.stringify(existingSafeValues(existing.row)) === JSON.stringify(row.map((value) => String(value ?? "")))) {
        return null;
      }
      return { project: item.project, rowIndex1: existing.rowIndex1, row };
    })
    .filter(Boolean);
  const brandUpdates = [...sourceRows.entries()]
    .map(([key, item]) => {
      const existing = targetRows.existing.get(key);
      const brand = mostFrequent(item.brands);
      if (!existing || !brand || !needsBrandFill(existing.row[8])) return null;
      return { project: item.project, rowIndex1: existing.rowIndex1, brand };
    })
    .filter(Boolean);

  const rowsToAppend = [];
  const unknownProjects = [];
  const inactiveSites = [];
  const enrichedCandidates = await mapConcurrent(candidates, 10, async (item) => {
    const siteCheck = await checkSite(item.project);
    const classification = classifyByText(item.project, siteCheck.text, targetRows.classifications);
    return { item, siteCheck, classification };
  });
  for (const { item, siteCheck, classification } of enrichedCandidates) {
    if (classification.category === "Не определено") unknownProjects.push(item.project);
    if (siteCheck.active !== "Да") inactiveSites.push(item.project);
    rowsToAppend.push({
      project: item.project,
      row: buildRow(item, siteCheck, classification),
      siteUrl: siteCheck.url,
      siteActive: siteCheck.active,
      category: classification.category,
      subcategory: classification.subcategory,
    });
  }

  if (!args.dryRun) {
    await updateExistingSafeRows(targetSpreadsheetId, token, targetSheet.properties.sheetId, safeRowUpdates);
    await updateExistingBrands(targetSpreadsheetId, token, targetSheet.properties.sheetId, brandUpdates);
    await appendRows(
      targetSpreadsheetId,
      token,
      targetSheet.properties.sheetId,
      targetRows.lastDataRowIndex1,
      rowsToAppend,
      periodFromItems([...sourceRows.values()]),
    );
  }

  const result = {
    ok: true,
    dryRun: args.dryRun,
    updatedAtMsk: nowMsk(),
    sourceSheet: sourceTitle,
    targetSheet: args.targetSheetTitle,
    sourceProjects: sourceRows.size,
    existingProjects: targetRows.existing.size,
    newProjectsFound: candidates.length,
    existingRowsUpdatedCount: args.dryRun ? 0 : safeRowUpdates.length,
    plannedExistingRowsUpdatedCount: safeRowUpdates.length,
    brandUpdatesCount: args.dryRun ? 0 : brandUpdates.length,
    plannedBrandUpdatesCount: brandUpdates.length,
    addedCount: args.dryRun ? 0 : rowsToAppend.length,
    plannedAddCount: rowsToAppend.length,
    skippedProjectsWithoutPointer,
    addedProjects: rowsToAppend.map((item) => ({
      project: item.project,
      category: item.category,
      subcategory: item.subcategory,
      siteActive: item.siteActive,
    })),
    existingRowsUpdatedProjects: safeRowUpdates.map((item) => ({
      project: item.project,
      row: item.rowIndex1,
    })),
    unknownProjects,
    inactiveSites,
    brandUpdatedProjects: brandUpdates.map((item) => ({
      project: item.project,
      row: item.rowIndex1,
      brand: item.brand,
    })),
  };
  const output = JSON.stringify(result, null, 2);
  if (args.reportPath) await writeFile(args.reportPath, `${output}\n`, "utf8");
  console.log(output);
}

main().catch((error) => {
  console.error(String(error?.stack || error?.message || error || "unknown error"));
  process.exit(1);
});
