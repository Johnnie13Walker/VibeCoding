import fs from 'node:fs';
import path from 'node:path';

const sourcePath = process.argv[2];
const outputPath = process.argv[3];

if (!sourcePath || !outputPath) {
  console.error('Использование: node tools/render_datalens_preview.mjs <export.json> <output.html>');
  process.exit(1);
}

const raw = JSON.parse(fs.readFileSync(sourcePath, 'utf8'));
const entries = raw.export?.entries ?? {};
const dashEntry = Object.values(entries.dash ?? {})[0]?.dash;

if (!dashEntry) {
  console.error('В экспорте не найден дашборд DataLens.');
  process.exit(1);
}

const tab = dashEntry.data?.tabs?.[0];
const widgets = entries.widget ?? {};
const layoutById = new Map((tab?.layout ?? []).map((item) => [item.i, item]));
const regularItems = tab?.items ?? [];
const globalItems = tab?.globalItems ?? [];
const allItems = [...globalItems, ...regularItems];
const maxY = Math.max(...(tab?.layout ?? []).map((item) => item.y + item.h), 1);

function htmlEscape(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function chartInfo(item) {
  if (item.type === 'text') {
    const text = String(item.data?.text ?? '').replace(/^#+\s*/, '').trim();
    return {
      title: text,
      type: 'text',
      source: 'text',
    };
  }

  if (item.type === 'group_control') {
    const control = item.data?.group?.[0] ?? {};
    return {
      title: control.title ?? 'Фильтр',
      type: 'control',
      source: control.source?.elementType ?? 'control',
      defaultValue: control.source?.defaultValue ?? control.defaults?.[control.source?.fieldName] ?? '',
    };
  }

  const tabData = item.data?.tabs?.find((candidate) => candidate.isDefault) ?? item.data?.tabs?.[0] ?? {};
  const chartId = tabData.chartId;
  const widget = widgets[String(chartId)]?.widget;
  const shared = widget?.data?.shared ?? {};
  const type = shared.visualization?.id ?? 'unknown';

  return {
    title: tabData.title || widget?.name || `Виджет ${chartId}`,
    type,
    source: widget?.name ?? '',
    fields: (shared.visualization?.placeholders ?? [])
      .flatMap((placeholder) => placeholder.items ?? [])
      .map((field) => field.fakeTitle || field.title)
      .filter(Boolean)
      .slice(0, 7),
  };
}

function metricMarkup(info, index) {
  const samples = ['128 420', '42 318', '18,6%', '7 914', '3,42', '1 287', '24,1%'];
  const deltas = ['+12,4%', '+8,1%', '-3,2%', '+21,7%', '+0,8%', '-1,5%', '+6,3%'];
  const positive = !deltas[index % deltas.length].startsWith('-');
  return `
    <div class="metric-value">${samples[index % samples.length]}</div>
    <div class="metric-delta ${positive ? 'positive' : 'negative'}">${deltas[index % deltas.length]} к периоду сравнения</div>
  `;
}

function lineMarkup() {
  return `
    <svg class="chart-svg" viewBox="0 0 420 170" role="img" aria-label="Линейный график">
      <defs>
        <linearGradient id="lineFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="#2f80ed" stop-opacity="0.24"/>
          <stop offset="100%" stop-color="#2f80ed" stop-opacity="0.02"/>
        </linearGradient>
      </defs>
      <g stroke="#e2e8f0" stroke-width="1">
        <line x1="18" y1="28" x2="402" y2="28"/><line x1="18" y1="72" x2="402" y2="72"/>
        <line x1="18" y1="116" x2="402" y2="116"/><line x1="18" y1="160" x2="402" y2="160"/>
      </g>
      <path d="M20 142 C70 126 82 86 132 98 C180 110 194 42 238 58 C282 74 296 120 340 82 C366 60 384 48 404 42 L404 160 L20 160 Z" fill="url(#lineFill)"/>
      <path d="M20 142 C70 126 82 86 132 98 C180 110 194 42 238 58 C282 74 296 120 340 82 C366 60 384 48 404 42" fill="none" stroke="#2f80ed" stroke-width="4" stroke-linecap="round"/>
      <path d="M20 126 C68 118 92 118 132 92 C174 64 202 92 238 86 C282 78 306 94 340 68 C368 48 386 70 404 58" fill="none" stroke="#26a269" stroke-width="3" stroke-linecap="round" stroke-dasharray="6 8"/>
    </svg>
  `;
}

function donutMarkup() {
  return `
    <div class="donut-wrap">
      <div class="donut"></div>
      <div class="legend">
        <span><b class="blue"></b>Desktop</span>
        <span><b class="green"></b>Mobile</span>
        <span><b class="yellow"></b>Tablet</span>
      </div>
    </div>
  `;
}

function barMarkup() {
  return `
    <div class="bars">
      ${[78, 56, 88, 42, 66, 51, 73].map((height, index) => `<span style="height:${height}%"><i>${index + 1}</i></span>`).join('')}
    </div>
  `;
}

function tableMarkup() {
  return `
    <table>
      <thead><tr><th>Запрос / страница</th><th>Клики</th><th>Показы</th><th>CTR</th></tr></thead>
      <tbody>
        <tr><td>/catalog/seo</td><td>1 248</td><td>18 920</td><td>6,6%</td></tr>
        <tr><td>seo аудит сайта</td><td>934</td><td>14 310</td><td>6,5%</td></tr>
        <tr><td>органический трафик</td><td>682</td><td>11 870</td><td>5,7%</td></tr>
      </tbody>
    </table>
  `;
}

function controlMarkup(info) {
  const value = String(info.defaultValue ?? '').replace('__eq_', '').slice(0, 10);
  return `<div class="control"><span>${htmlEscape(info.title)}</span><strong>${htmlEscape(value || info.source)}</strong></div>`;
}

function textMarkup(info) {
  return info.title
    ? `<div class="section-title">${htmlEscape(info.title)}</div>`
    : `<div class="section-spacer"></div>`;
}

function visualMarkup(info, index) {
  if (info.type === 'text') return textMarkup(info);
  if (info.type === 'control') return controlMarkup(info);
  if (info.type === 'metric') return metricMarkup(info, index);
  if (info.type === 'line' || info.type === 'combined-chart') return lineMarkup();
  if (info.type === 'donut') return donutMarkup();
  if (info.type === 'column') return barMarkup();
  if (info.type === 'flatTable') return tableMarkup();
  return `<div class="placeholder">Тип визуализации: ${htmlEscape(info.type)}</div>`;
}

function cardMarkup(item, index) {
  const layout = layoutById.get(item.id);
  if (!layout) return '';

  const info = chartInfo(item);
  const isControl = info.type === 'control';
  const isText = info.type === 'text';
  const fields = info.fields?.length
    ? `<div class="fields">${info.fields.map((field) => `<span>${htmlEscape(field)}</span>`).join('')}</div>`
    : '';

  return `
    <section class="tile ${isControl ? 'tile-control' : ''} ${isText ? 'tile-text' : ''}" style="grid-column:${layout.x + 1} / span ${layout.w}; grid-row:${layout.y + 1} / span ${layout.h};">
      ${isControl || isText ? '' : `<header><h2>${htmlEscape(info.title)}</h2><span>${htmlEscape(info.type)}</span></header>`}
      <div class="body">${visualMarkup(info, index)}</div>
      ${isControl || isText ? '' : fields}
    </section>
  `;
}

const cards = allItems.map(cardMarkup).join('\n');

const html = `<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${htmlEscape(dashEntry.name)} — локальный просмотр</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f7fb;
      --card: #ffffff;
      --text: #172033;
      --muted: #667085;
      --line: #d9e0ea;
      --blue: #2f80ed;
      --green: #26a269;
      --yellow: #f2b705;
      --red: #d92d20;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font: 14px/1.45 Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    .page {
      width: min(1880px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }
    .top {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 24px;
      margin-bottom: 18px;
    }
    h1 {
      margin: 0;
      font-size: 28px;
      font-weight: 760;
      letter-spacing: 0;
    }
    .note {
      max-width: 760px;
      margin: 6px 0 0;
      color: var(--muted);
    }
    .badge {
      border: 1px solid var(--line);
      background: var(--card);
      border-radius: 8px;
      padding: 9px 12px;
      color: var(--muted);
      white-space: nowrap;
    }
    .dashboard {
      display: grid;
      grid-template-columns: repeat(36, minmax(0, 1fr));
      grid-template-rows: repeat(${maxY}, 30px);
      grid-auto-flow: dense;
      gap: 10px;
      align-items: stretch;
    }
    .tile {
      min-width: 0;
      overflow: hidden;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
      display: flex;
      flex-direction: column;
    }
    .tile header {
      min-height: 42px;
      padding: 10px 12px 4px;
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 10px;
    }
    .tile h2 {
      margin: 0;
      font-size: 13px;
      font-weight: 680;
      letter-spacing: 0;
      line-height: 1.25;
    }
    .tile header span {
      flex: 0 0 auto;
      font-size: 11px;
      color: var(--muted);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 2px 6px;
    }
    .body {
      flex: 1;
      min-height: 0;
      padding: 8px 12px 10px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .metric-value {
      width: 100%;
      font-size: clamp(24px, 2.2vw, 42px);
      font-weight: 760;
      line-height: 1;
      text-align: center;
    }
    .metric-delta {
      width: 100%;
      margin-top: 8px;
      text-align: center;
      font-weight: 620;
      font-size: 12px;
    }
    .positive { color: var(--green); }
    .negative { color: var(--red); }
    .chart-svg {
      width: 100%;
      height: 100%;
      min-height: 120px;
    }
    .fields {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 0 12px 10px;
      color: var(--muted);
      font-size: 11px;
    }
    .fields span {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 2px 6px;
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .tile-control {
      border-style: dashed;
      box-shadow: none;
    }
    .tile-text {
      background: transparent;
      border-color: transparent;
      box-shadow: none;
    }
    .tile-text .body {
      justify-content: flex-start;
      padding: 0 4px;
    }
    .section-title {
      font-size: 20px;
      font-weight: 760;
      line-height: 1.25;
      color: var(--text);
    }
    .section-spacer {
      width: 100%;
      height: 1px;
    }
    .control {
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 8px 10px;
    }
    .control span {
      color: var(--muted);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .control strong {
      font-size: 13px;
      font-weight: 680;
      white-space: nowrap;
    }
    .donut-wrap {
      width: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 22px;
    }
    .donut {
      width: min(150px, 45%);
      aspect-ratio: 1;
      border-radius: 50%;
      background: conic-gradient(var(--blue) 0 54%, var(--green) 54% 88%, var(--yellow) 88% 100%);
      position: relative;
    }
    .donut:after {
      content: "";
      position: absolute;
      inset: 24%;
      background: var(--card);
      border-radius: 50%;
    }
    .legend {
      display: grid;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
    }
    .legend b {
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 3px;
      margin-right: 6px;
    }
    .blue { background: var(--blue); }
    .green { background: var(--green); }
    .yellow { background: var(--yellow); }
    .bars {
      width: 100%;
      height: 100%;
      min-height: 150px;
      display: flex;
      align-items: end;
      gap: 5%;
      padding: 16px 8px 8px;
      border-bottom: 1px solid var(--line);
    }
    .bars span {
      flex: 1;
      min-width: 12px;
      border-radius: 6px 6px 0 0;
      background: linear-gradient(180deg, #2f80ed, #6bb8ff);
      position: relative;
    }
    .bars i {
      position: absolute;
      bottom: -23px;
      left: 50%;
      transform: translateX(-50%);
      color: var(--muted);
      font-style: normal;
      font-size: 11px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    th, td {
      text-align: left;
      padding: 8px 7px;
      border-bottom: 1px solid var(--line);
      white-space: nowrap;
    }
    th {
      color: var(--muted);
      font-weight: 650;
    }
    .placeholder {
      color: var(--muted);
      border: 1px dashed var(--line);
      border-radius: 8px;
      padding: 14px;
    }
    @media (max-width: 900px) {
      .page { width: calc(100vw - 20px); padding-top: 14px; }
      .top { display: block; }
      .badge { display: inline-block; margin-top: 12px; white-space: normal; }
      .dashboard {
        display: flex;
        flex-direction: column;
      }
      .tile { min-height: 170px; }
      .tile-control { min-height: 58px; }
    }
  </style>
</head>
<body>
  <main class="page">
    <div class="top">
      <div>
        <h1>${htmlEscape(dashEntry.name)}</h1>
        <p class="note">Локальная реконструкция шаблона DataLens из JSON-экспорта. Позиции, названия виджетов, типы графиков и фильтры взяты из файла; численные значения показаны как демонстрационные заглушки.</p>
      </div>
      <div class="badge">${regularItems.length} виджетов, ${globalItems.length} фильтров, ${Object.keys(entries.dataset ?? {}).length} датасета</div>
    </div>
    <div class="dashboard">
      ${cards}
    </div>
  </main>
</body>
</html>`;

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, html, 'utf8');
console.log(outputPath);
