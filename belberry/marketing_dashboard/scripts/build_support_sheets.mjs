import { createSign } from "node:crypto";
import { readFile } from "node:fs/promises";

const SHEET_URL = "https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit#gid=0";
const SA_PATH = process.env.MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON || process.env.GOOGLE_SERVICE_ACCOUNT_JSON || "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json";
const COHORT_PATH = "/tmp/cohort_slice_3.json";
const WINS_PATH = "/tmp/wins_ytd_2026.json";
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
async function valuesUpdate(spreadsheetId, token, range, values) {
  const res = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}?valueInputOption=USER_ENTERED`, {
    method: "PUT",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify({ majorDimension: "ROWS", values }),
  });
  const payload = await res.json();
  if (!res.ok) throw new Error(`Values update error: ${res.status} ${JSON.stringify(payload)}`);
  return payload;
}
async function ensureSheet(spreadsheetId, token, sheets, title, rowCount = 400, columnCount = 12) {
  if (sheets.has(title)) return sheets.get(title);
  const result = await batchUpdate(spreadsheetId, token, [{ addSheet: { properties: { title, gridProperties: { rowCount, columnCount } } } }]);
  const createdSheetId = result.replies?.[0]?.addSheet?.properties?.sheetId;
  if (createdSheetId == null) throw new Error(`Не удалось создать вкладку "${title}"`);
  sheets.set(title, createdSheetId);
  return createdSheetId;
}
function fmtInt(value) {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(Number(value || 0));
}
function moscowTimestamp() {
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: "Europe/Moscow",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date()) + " МСК";
}
function formatPeriod(meta) {
  return String(meta?.period || "").replace("..", " — ");
}
function hyperlink(url, text) {
  return `=HYPERLINK("${url}";"${String(text || "").replace(/"/g, '""')}")`;
}

function buildQualityRows(cohort, wins) {
  const detailRows = cohort.detail_rows || [];
  const detailById = new Map(detailRows.map((row) => [String(row.id), row]));
  const issueMap = new Map();

  const ensureIssue = (row) => {
    const id = String(row.id || row.deal_id);
    if (!issueMap.has(id)) {
      const detail = detailById.get(id) || {};
      issueMap.set(id, {
        id,
        title: row.title || detail.title || "Без названия",
        url: row.url || detail.url || "",
        created_at: detail.created_at || row.won_at || "",
        brand: detail.brand || row.brand || "",
        source: detail.source || row.source || "",
        current_category: detail.current_category || row.category || "",
        current_stage: detail.current_stage || "",
        severity: 2,
        problems: new Set(),
        notes: new Set(),
      });
    }
    return issueMap.get(id);
  };

  for (const row of detailRows) {
    const issue = ensureIssue(row);
    const source = String(row.source || "").trim();
    const brand = String(row.brand || "").trim();
    if (!brand || brand === "Без бренда") {
      issue.severity = 1;
      issue.problems.add("Без бренда");
      issue.notes.add("В карточке не заполнено поле бренда.");
    }
    if (!source || source === "Без источника") {
      issue.severity = 1;
      issue.problems.add("Без источника");
      issue.notes.add("Источник пустой или не выбран.");
    }
    if (source === "Не выяснено") {
      issue.problems.add("Не выяснено");
      issue.notes.add("Источник допустим, но атрибуция требует ручной проверки.");
    }

    const stageFlags = [];
    if (row.kp && !row.lead) stageFlags.push("КП без лида");
    if (row.contract && !row.kp) stageFlags.push("Договор без КП");
    if (row.sale && !row.contract) stageFlags.push("Продажа без договора");
    if (stageFlags.length) {
      issue.problems.add("Аномалия стадий");
      issue.notes.add(stageFlags.join("; "));
    }
  }

  for (const row of wins.deal_rows || []) {
    const source = String(row.source || "").trim();
    const brand = String(row.brand || "").trim();
    if (source === "Не выяснено" || source === "Без источника" || !source || !brand || brand === "Без бренда") {
      const issue = ensureIssue({ ...row, id: row.deal_id });
      issue.severity = 1;
      issue.problems.add("Продажа с проблемной атрибуцией");
      issue.notes.add(`Успех: ${row.won_at}. Сумма: ${fmtInt(row.deal_amount || 0)} ₽.`);
    }
  }

  const rows = Array.from(issueMap.values())
    .filter((item) => item.problems.size)
    .map((item) => ({
      ...item,
      problemLabel: Array.from(item.problems).join(" · "),
      noteLabel: Array.from(item.notes).join(" | "),
      priority: item.severity === 1 ? "P1" : "P2",
    }))
    .sort((a, b) => a.severity - b.severity || a.created_at.localeCompare(b.created_at) || a.title.localeCompare(b.title, "ru"));

  return {
    rows,
    summary: {
      noSource: rows.filter((row) => row.problems.has("Без источника")).length,
      unclear: rows.filter((row) => row.problems.has("Не выяснено")).length,
      noBrand: rows.filter((row) => row.problems.has("Без бренда")).length,
      stage: rows.filter((row) => row.problems.has("Аномалия стадий")).length,
      wonAttr: rows.filter((row) => row.problems.has("Продажа с проблемной атрибуцией")).length,
      total: rows.length,
    },
  };
}

function buildQualityValues(cohort, wins) {
  const quality = buildQualityRows(cohort, wins);
  const values = [
    ["Качество данных · маркетинговый дашборд"],
    ["Период", formatPeriod(cohort.meta), "", "Обновлено", moscowTimestamp(), "", "Логика", "Сделки отчётного контура + телемаркетинг по встречам"],
    ["Лист показывает только те карточки, которые сейчас мешают корректно читать источники, конверсии и выручку."],
    [""],
    ["Сводка"],
    ["Без источника", quality.summary.noSource, "", "Не выяснено", quality.summary.unclear, "", "Без бренда", quality.summary.noBrand],
    ["Аномалии стадий", quality.summary.stage, "", "Продажи с проблемной атрибуцией", quality.summary.wonAttr, "", "Всего проблемных сделок", quality.summary.total],
    [""],
    ["Очередь на правку"],
    ["Приоритет", "Проблема", "Дата обращения", "Сделка", "Бренд", "Источник", "Текущая воронка", "Текущий статус", "Комментарий"],
    ...quality.rows.map((row) => [
      row.priority,
      row.problemLabel,
      row.created_at,
      hyperlink(row.url, row.title),
      row.brand || "Без бренда",
      row.source || "Без источника",
      row.current_category || "—",
      row.current_stage || "—",
      row.noteLabel,
    ]),
  ];
  return { values, quality };
}

function buildMethodologyValues() {
  return [
    ["Методология · маркетинговый дашборд"],
    ["Обновлено", moscowTimestamp(), "", "Статус", "Рабочая версия"],
    ["Этот лист фиксирует, как именно считаются метрики в книге, чтобы дальше цифры не спорили между собой."],
    [""],
    ["1. Границы выборки"],
    ["В отчёт попадают только сделки, которые проходили воронку продаж."],
    ["Если сделка сначала была в продажах, а затем ушла в реанимацию, телемаркетинг или другую воронку, она всё равно остаётся в маркетинговой выборке."],
    ["Перенос сделки между воронками не создаёт новое обращение."],
    [""],
    ["2. Определения показателей"],
    ["Показатель", "Как считается"],
    ["Обращение", "Сделка создана в периоде. Для когортного слоя строка месяца = месяц создания сделки. Для источника «Телемаркетинг» строка месяца = поле «Дата встречи» первой встречи, созданной сотрудником телемаркетинга."],
    ["Лид", "Обращение, которое не закрыто в отказ с причиной «Спам» или «Вход: нет связи» / «Нет связи». Для источника «Телемаркетинг» лидом считается сделка, где первая встреча проведена или перенос первой встречи завершился проведённой встречей."],
    ["КП", "Первый вход сделки в стадию «Подготовка КП»."],
    ["Договор", "Первый вход сделки в стадию «Подготовка договора»."],
    ["Продажа", "Первый вход сделки в стадию «УСПЕХ»."],
    ["Выручка", "Сумма выигранных сделок по дате первого входа в «УСПЕХ»."],
    [""],
    ["3. Разница между слоями"],
    ["Когортный анализ", "Показывает, что произошло с когортой сделок, созданных в конкретном месяце."],
    ["Событийный анализ", "Показывает, сколько переходов в этапы фактически произошло в конкретном месяце, независимо от даты создания сделки."],
    [""],
    ["4. Источники и бренды"],
    ["Источник", "Берётся из карточки сделки на момент выгрузки. Исключение: если по сделке есть встреча, созданная сотрудником отдела телемаркетинга, источник принудительно считается как «Телемаркетинг». Это покрывает период до марта 2026, когда телемаркетологи работали из лидов, а не из отдельной воронки."],
    ["SOURCE_ID=Телемаркетинг", "Само значение поля SOURCE_ID не считается достаточным основанием для источника «Телемаркетинг». Если нет встречи, созданной сотрудником отдела телемаркетинга, сделка попадает в «Не выяснено»."],
    ["Спам", "Сделки с причиной отказа «Спам» или «Вход: нет связи» / «Нет связи» остаются обращениями, но не считаются лидами. Отдельно попадают в лист «Спам по источникам»."],
    ["Не выяснено", "Допустимое значение. Означает, что команда не смогла надёжно определить источник."],
    ["Без источника", "Ошибка качества данных. Такие сделки должны попадать в лист «Качество данных» и исправляться."],
    ["Без бренда", "Ошибка качества данных. Такие сделки не должны оставаться в рабочем маркетинговом отчёте."],
    [""],
    ["5. Ограничения"],
    ["Если в Bitrix сделка перепрыгивает стадии, в отчёте могут появляться аномальные переходы вида «КП без лида» или «Продажа без договора»."],
    ["Именно поэтому вместе с дашбордом ведётся отдельный лист «Качество данных»."],
    ["Если появится слой расходов, все метрики CPL / CAC / ROMI должны считаться только после нормализации источников."],
  ];
}

function buildExpensesValues(cohort) {
  const rows = Object.entries(cohort.cohort_by_source || {})
    .map(([key]) => {
      const [month, brand, source] = key.split("|||");
      return { month, brand, source };
    })
    .filter((row) => row.brand !== "Без бренда")
    .sort((a, b) => a.month.localeCompare(b.month) || a.brand.localeCompare(b.brand, "ru") || a.source.localeCompare(b.source, "ru"));

  const values = [
    ["Шаблон расходов · по месяцам, брендам и источникам"],
    ["Период", formatPeriod(cohort.meta), "", "Обновлено", moscowTimestamp()],
    ["Одна строка = один месяц + один бренд + один источник. Для organic / no-cost каналов ставь 0, а не пусто."],
    ["Используй те же названия источников, что и в маркетинговом отчёте, иначе CPL / CAC потом не сматчатся."],
    [""],
    ["Сводка"],
    ["Всего строк", `=COUNTA(A8:A)-1`, "", "Заполнено расходов", `=COUNT(D8:D)`, "", "Сумма расходов", `=SUM(D8:D)`],
    ["Месяц", "Бренд", "Источник", "Расход, ₽", "Статус", "Комментарий"],
    ...rows.map((row, index) => {
      const sheetRow = index + 9;
      return [
        row.month,
        row.brand,
        row.source,
        "",
        `=IF(D${sheetRow}=\"\";\"Заполнить\";\"ОК\")`,
        "",
      ];
    }),
  ];
  return { values, rowCount: rows.length };
}

function baseSheetRequests(sheetId, columnCount, frozenRowCount = 3, maxRows = 500) {
  return [
    { updateCells: { range: { sheetId }, fields: "userEnteredValue,userEnteredFormat,textFormatRuns,dataValidation,note" } },
    { unmergeCells: { range: { sheetId, startRowIndex: 0, endRowIndex: maxRows, startColumnIndex: 0, endColumnIndex: columnCount } } },
    { updateSheetProperties: { properties: { sheetId, gridProperties: { frozenRowCount } }, fields: "gridProperties.frozenRowCount" } },
    { repeatCell: { range: { sheetId }, cell: { userEnteredFormat: { backgroundColor: { red: 0.977, green: 0.984, blue: 0.992 }, textFormat: { fontFamily: "Arial", fontSize: 10, foregroundColor: { red: 0.129, green: 0.161, blue: 0.215 } }, wrapStrategy: "WRAP", verticalAlignment: "MIDDLE" } }, fields: "userEnteredFormat(backgroundColor,textFormat,wrapStrategy,verticalAlignment)" } },
    { mergeCells: { range: { sheetId, startRowIndex: 0, endRowIndex: 1, startColumnIndex: 0, endColumnIndex: columnCount }, mergeType: "MERGE_ALL" } },
    { repeatCell: { range: { sheetId, startRowIndex: 0, endRowIndex: 1, startColumnIndex: 0, endColumnIndex: columnCount }, cell: { userEnteredFormat: { backgroundColor: { red: 0.067, green: 0.125, blue: 0.2 }, textFormat: { foregroundColor: { red: 1, green: 1, blue: 1 }, fontSize: 16, bold: true }, verticalAlignment: "MIDDLE" } }, fields: "userEnteredFormat(backgroundColor,textFormat,verticalAlignment)" } },
    { repeatCell: { range: { sheetId, startRowIndex: 1, endRowIndex: 2 }, cell: { userEnteredFormat: { backgroundColor: { red: 0.905, green: 0.941, blue: 0.972 }, textFormat: { bold: true, foregroundColor: { red: 0.196, green: 0.255, blue: 0.333 } } } }, fields: "userEnteredFormat(backgroundColor,textFormat)" } },
  ];
}

function qualitySheetRequests(sheetId, values) {
  const requests = baseSheetRequests(sheetId, 9, 10, Math.max(values.length + 20, 160));
  requests.push(
    { mergeCells: { range: { sheetId, startRowIndex: 2, endRowIndex: 3, startColumnIndex: 0, endColumnIndex: 9 }, mergeType: "MERGE_ALL" } },
    { repeatCell: { range: { sheetId, startRowIndex: 2, endRowIndex: 3 }, cell: { userEnteredFormat: { backgroundColor: { red: 0.984, green: 0.98, blue: 0.945 }, textFormat: { foregroundColor: { red: 0.34, green: 0.36, blue: 0.24 } } } }, fields: "userEnteredFormat(backgroundColor,textFormat)" } },
    { mergeCells: { range: { sheetId, startRowIndex: 4, endRowIndex: 5, startColumnIndex: 0, endColumnIndex: 9 }, mergeType: "MERGE_ALL" } },
    { repeatCell: { range: { sheetId, startRowIndex: 4, endRowIndex: 5 }, cell: { userEnteredFormat: { backgroundColor: { red: 0.61, green: 0.16, blue: 0.18 }, textFormat: { bold: true, foregroundColor: { red: 1, green: 1, blue: 1 } } } }, fields: "userEnteredFormat(backgroundColor,textFormat)" } },
    { repeatCell: { range: { sheetId, startRowIndex: 5, endRowIndex: 7 }, cell: { userEnteredFormat: { backgroundColor: { red: 1, green: 1, blue: 1 }, textFormat: { bold: true }, horizontalAlignment: "CENTER" } }, fields: "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)" } },
    { mergeCells: { range: { sheetId, startRowIndex: 8, endRowIndex: 9, startColumnIndex: 0, endColumnIndex: 9 }, mergeType: "MERGE_ALL" } },
    { repeatCell: { range: { sheetId, startRowIndex: 8, endRowIndex: 9 }, cell: { userEnteredFormat: { backgroundColor: { red: 0.067, green: 0.463, blue: 0.431 }, textFormat: { bold: true, foregroundColor: { red: 1, green: 1, blue: 1 } } } }, fields: "userEnteredFormat(backgroundColor,textFormat)" } },
    { repeatCell: { range: { sheetId, startRowIndex: 9, endRowIndex: 10 }, cell: { userEnteredFormat: { backgroundColor: { red: 0.93, green: 0.95, blue: 0.98 }, textFormat: { bold: true }, horizontalAlignment: "CENTER" } }, fields: "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)" } },
    { repeatCell: { range: { sheetId, startRowIndex: 10, endRowIndex: values.length, startColumnIndex: 0, endColumnIndex: 9 }, cell: { userEnteredFormat: { backgroundColor: { red: 1, green: 1, blue: 1 }, verticalAlignment: "TOP" } }, fields: "userEnteredFormat(backgroundColor,verticalAlignment)" } },
    { repeatCell: { range: { sheetId, startRowIndex: 10, endRowIndex: values.length, startColumnIndex: 0, endColumnIndex: 1 }, cell: { userEnteredFormat: { horizontalAlignment: "CENTER", textFormat: { bold: true } } }, fields: "userEnteredFormat(horizontalAlignment,textFormat)" } },
    { repeatCell: { range: { sheetId, startRowIndex: 10, endRowIndex: values.length, startColumnIndex: 2, endColumnIndex: 3 }, cell: { userEnteredFormat: { horizontalAlignment: "CENTER" } }, fields: "userEnteredFormat(horizontalAlignment)" } },
    { updateBorders: { range: { sheetId, startRowIndex: 9, endRowIndex: values.length, startColumnIndex: 0, endColumnIndex: 9 }, top: { style: "SOLID", color: { red: 0.8, green: 0.82, blue: 0.85 } }, bottom: { style: "SOLID", color: { red: 0.8, green: 0.82, blue: 0.85 } }, left: { style: "SOLID", color: { red: 0.8, green: 0.82, blue: 0.85 } }, right: { style: "SOLID", color: { red: 0.8, green: 0.82, blue: 0.85 } }, innerHorizontal: { style: "SOLID", color: { red: 0.89, green: 0.9, blue: 0.92 } }, innerVertical: { style: "SOLID", color: { red: 0.89, green: 0.9, blue: 0.92 } } } },
    { updateDimensionProperties: { range: { sheetId, dimension: "ROWS", startIndex: 0, endIndex: 1 }, properties: { pixelSize: 38 }, fields: "pixelSize" } },
    { updateDimensionProperties: { range: { sheetId, dimension: "ROWS", startIndex: 2, endIndex: 3 }, properties: { pixelSize: 32 }, fields: "pixelSize" } },
    { autoResizeDimensions: { dimensions: { sheetId, dimension: "COLUMNS", startIndex: 0, endIndex: 9 } } },
  );
  return requests;
}

function methodologySheetRequests(sheetId, values) {
  const requests = baseSheetRequests(sheetId, 6, 4, 120);
  const sectionRows = [4, 9, 18, 22, 28];
  for (const rowIndex of sectionRows) {
    requests.push(
      { mergeCells: { range: { sheetId, startRowIndex: rowIndex, endRowIndex: rowIndex + 1, startColumnIndex: 0, endColumnIndex: 6 }, mergeType: "MERGE_ALL" } },
      { repeatCell: { range: { sheetId, startRowIndex: rowIndex, endRowIndex: rowIndex + 1 }, cell: { userEnteredFormat: { backgroundColor: { red: 0.067, green: 0.463, blue: 0.431 }, textFormat: { bold: true, foregroundColor: { red: 1, green: 1, blue: 1 } } } }, fields: "userEnteredFormat(backgroundColor,textFormat)" } },
    );
  }
  requests.push(
    { mergeCells: { range: { sheetId, startRowIndex: 2, endRowIndex: 3, startColumnIndex: 0, endColumnIndex: 6 }, mergeType: "MERGE_ALL" } },
    { repeatCell: { range: { sheetId, startRowIndex: 2, endRowIndex: 3 }, cell: { userEnteredFormat: { backgroundColor: { red: 0.984, green: 0.98, blue: 0.945 }, textFormat: { foregroundColor: { red: 0.34, green: 0.36, blue: 0.24 } } } }, fields: "userEnteredFormat(backgroundColor,textFormat)" } },
    { repeatCell: { range: { sheetId, startRowIndex: 10, endRowIndex: 17 }, cell: { userEnteredFormat: { backgroundColor: { red: 1, green: 1, blue: 1 } } }, fields: "userEnteredFormat(backgroundColor)" } },
    { repeatCell: { range: { sheetId, startRowIndex: 10, endRowIndex: 11 }, cell: { userEnteredFormat: { backgroundColor: { red: 0.93, green: 0.95, blue: 0.98 }, textFormat: { bold: true } } }, fields: "userEnteredFormat(backgroundColor,textFormat)" } },
    { updateBorders: { range: { sheetId, startRowIndex: 10, endRowIndex: 17, startColumnIndex: 0, endColumnIndex: 2 }, top: { style: "SOLID", color: { red: 0.8, green: 0.82, blue: 0.85 } }, bottom: { style: "SOLID", color: { red: 0.8, green: 0.82, blue: 0.85 } }, left: { style: "SOLID", color: { red: 0.8, green: 0.82, blue: 0.85 } }, right: { style: "SOLID", color: { red: 0.8, green: 0.82, blue: 0.85 } }, innerHorizontal: { style: "SOLID", color: { red: 0.89, green: 0.9, blue: 0.92 } }, innerVertical: { style: "SOLID", color: { red: 0.89, green: 0.9, blue: 0.92 } } } },
    { autoResizeDimensions: { dimensions: { sheetId, dimension: "COLUMNS", startIndex: 0, endIndex: 6 } } },
  );
  return requests;
}

function expensesSheetRequests(sheetId, values) {
  const requests = baseSheetRequests(sheetId, 8, 8, Math.max(values.length + 30, 220));
  requests.push({
    updateSheetProperties: {
      properties: { sheetId, gridProperties: { columnCount: 8 } },
      fields: "gridProperties.columnCount",
    },
  });
  requests.push(
    { mergeCells: { range: { sheetId, startRowIndex: 2, endRowIndex: 3, startColumnIndex: 0, endColumnIndex: 8 }, mergeType: "MERGE_ALL" } },
    { mergeCells: { range: { sheetId, startRowIndex: 3, endRowIndex: 4, startColumnIndex: 0, endColumnIndex: 8 }, mergeType: "MERGE_ALL" } },
    { repeatCell: { range: { sheetId, startRowIndex: 2, endRowIndex: 4 }, cell: { userEnteredFormat: { backgroundColor: { red: 0.984, green: 0.98, blue: 0.945 }, textFormat: { foregroundColor: { red: 0.34, green: 0.36, blue: 0.24 } } } }, fields: "userEnteredFormat(backgroundColor,textFormat)" } },
    { mergeCells: { range: { sheetId, startRowIndex: 5, endRowIndex: 6, startColumnIndex: 0, endColumnIndex: 8 }, mergeType: "MERGE_ALL" } },
    { repeatCell: { range: { sheetId, startRowIndex: 5, endRowIndex: 6 }, cell: { userEnteredFormat: { backgroundColor: { red: 0.067, green: 0.463, blue: 0.431 }, textFormat: { bold: true, foregroundColor: { red: 1, green: 1, blue: 1 } } } }, fields: "userEnteredFormat(backgroundColor,textFormat)" } },
    { repeatCell: { range: { sheetId, startRowIndex: 6, endRowIndex: 7 }, cell: { userEnteredFormat: { backgroundColor: { red: 1, green: 1, blue: 1 }, textFormat: { bold: true }, horizontalAlignment: "CENTER" } }, fields: "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)" } },
    { repeatCell: { range: { sheetId, startRowIndex: 7, endRowIndex: 8, startColumnIndex: 0, endColumnIndex: 8 }, cell: { userEnteredFormat: { backgroundColor: { red: 0.93, green: 0.95, blue: 0.98 }, textFormat: { bold: true }, horizontalAlignment: "CENTER" } }, fields: "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)" } },
    { repeatCell: { range: { sheetId, startRowIndex: 8, endRowIndex: values.length, startColumnIndex: 0, endColumnIndex: 8 }, cell: { userEnteredFormat: { backgroundColor: { red: 1, green: 1, blue: 1 } } }, fields: "userEnteredFormat(backgroundColor)" } },
    { repeatCell: { range: { sheetId, startRowIndex: 8, endRowIndex: values.length, startColumnIndex: 4, endColumnIndex: 5 }, cell: { userEnteredFormat: { horizontalAlignment: "CENTER" } }, fields: "userEnteredFormat(horizontalAlignment)" } },
    { repeatCell: { range: { sheetId, startRowIndex: 8, endRowIndex: values.length, startColumnIndex: 3, endColumnIndex: 4 }, cell: { userEnteredFormat: { numberFormat: { type: "NUMBER", pattern: "#,##0" } } }, fields: "userEnteredFormat.numberFormat" } },
    { updateBorders: { range: { sheetId, startRowIndex: 7, endRowIndex: values.length, startColumnIndex: 0, endColumnIndex: 8 }, top: { style: "SOLID", color: { red: 0.8, green: 0.82, blue: 0.85 } }, bottom: { style: "SOLID", color: { red: 0.8, green: 0.82, blue: 0.85 } }, left: { style: "SOLID", color: { red: 0.8, green: 0.82, blue: 0.85 } }, right: { style: "SOLID", color: { red: 0.8, green: 0.82, blue: 0.85 } }, innerHorizontal: { style: "SOLID", color: { red: 0.89, green: 0.9, blue: 0.92 } }, innerVertical: { style: "SOLID", color: { red: 0.89, green: 0.9, blue: 0.92 } } } },
    { autoResizeDimensions: { dimensions: { sheetId, dimension: "COLUMNS", startIndex: 0, endIndex: 8 } } },
  );
  return requests;
}

const spreadsheetId = extractSheetId(SHEET_URL);
const sa = await loadJson(SA_PATH);
const cohort = await loadJson(COHORT_PATH);
const wins = await loadJson(WINS_PATH);
const token = await fetchAccessToken(sa);
const metadata = await fetchJson(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}`, token);
const sheets = new Map((metadata.sheets || []).map((sheet) => [sheet.properties.title, sheet.properties.sheetId]));

const qualityTitle = "Качество данных";
const methodologyTitle = "Методология";
const expensesTitle = "Шаблон расходов";

const qualityId = await ensureSheet(spreadsheetId, token, sheets, qualityTitle, 220, 9);
const methodologyId = await ensureSheet(spreadsheetId, token, sheets, methodologyTitle, 120, 6);
const expensesId = await ensureSheet(spreadsheetId, token, sheets, expensesTitle, 260, 8);

const { values: qualityValues, quality } = buildQualityValues(cohort, wins);
const methodologyValues = buildMethodologyValues();
const { values: expensesValues, rowCount: expenseRows } = buildExpensesValues(cohort);

await batchUpdate(spreadsheetId, token, qualitySheetRequests(qualityId, qualityValues));
await valuesUpdate(spreadsheetId, token, `${quoteSheetTitle(qualityTitle)}!A1:I${qualityValues.length + 5}`, qualityValues);

await batchUpdate(spreadsheetId, token, methodologySheetRequests(methodologyId, methodologyValues));
await valuesUpdate(spreadsheetId, token, `${quoteSheetTitle(methodologyTitle)}!A1:F${methodologyValues.length + 5}`, methodologyValues);

await batchUpdate(spreadsheetId, token, expensesSheetRequests(expensesId, expensesValues));
await valuesUpdate(spreadsheetId, token, `${quoteSheetTitle(expensesTitle)}!A1:H${expensesValues.length + 5}`, expensesValues);

console.log(JSON.stringify({
  sheets: [qualityTitle, methodologyTitle, expensesTitle],
  quality,
  expenseRows,
}, null, 2));
