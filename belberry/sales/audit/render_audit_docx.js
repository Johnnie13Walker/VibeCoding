#!/usr/bin/env node
/**
 * render_audit_docx.js — Markdown → брендированный .docx (Belberry) через docx-js.
 *
 * Замена дефолтного `pandoc md → docx` в движке аудита: тот же вход (Markdown),
 * но фирменная вёрстка (синие заголовки, инфо-карточка, таблицы с шапкой,
 * цитаты-выноски), плюс надёжный docx-js вместо ручного XML.
 *
 * Использование:
 *   NODE_PATH="$(npm root -g)" node render_audit_docx.js <input.md> <output.docx> [--accent 2E75B6]
 *
 * Поддержка Markdown: YAML-фронтматтер (title/date/author), # / ## / ###,
 * pipe-таблицы (первая 2-колоночная с пустой шапкой → инфо-карточка),
 * > цитаты (выноски), маркир./нумер. списки, **жирный**, [текст](url), `код`,
 * \newpage → разрыв страницы, \vspace{..} игнорируется.
 *
 * Валидация результата:
 *   ~/.claude/skills/.venv-office/bin/python ~/.claude/skills/docx/scripts/office/validate.py <output.docx>
 */
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, LevelFormat, ExternalHyperlink, HeadingLevel,
  BorderStyle, WidthType, ShadingType, PageBreak, Header, Footer, PageNumber,
} = require("docx");

// ---------- CLI ----------
const args = process.argv.slice(2);
const positional = args.filter(a => !a.startsWith("--"));
const [inPath, outPath] = positional;
if (!inPath || !outPath) {
  console.error("usage: node render_audit_docx.js <input.md> <output.docx> [--accent HEX] [--footer TEXT]");
  process.exit(2);
}
const flag = (name, def) => { const i = args.indexOf("--" + name); return i >= 0 ? args[i + 1] : def; };
const ACCENT = (flag("accent", "2E75B6")).replace(/^#/, "");
const FOOTER = flag("footer", "");

// ---------- palette ----------
const HEAD_FILL = "D5E8F0", ZEBRA = "F2F7FB", CALLOUT = "FFF6E5", CALLOUT_BAR = "E0A030";
const CW = 9026; // A4, поля 1"
const thin = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const cellBorders = { top: thin, bottom: thin, left: thin, right: thin };

// ---------- inline parser: **bold**, [t](url), `code` ----------
function inlineRuns(text, base = {}) {
  const tokens = [];
  const re = /\*\*(.+?)\*\*|\[([^\]]+)\]\(([^)]+)\)|`([^`]+)`/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) tokens.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    if (m[1] !== undefined) tokens.push(new TextRun({ text: m[1], bold: true, ...base }));
    else if (m[2] !== undefined) tokens.push(new ExternalHyperlink({ link: m[3], children: [new TextRun({ text: m[2], style: "Hyperlink" })] }));
    else if (m[4] !== undefined) tokens.push(new TextRun({ text: m[4], font: "Courier New", ...base }));
    last = re.lastIndex;
  }
  if (last < text.length) tokens.push(new TextRun({ text: text.slice(last), ...base }));
  return tokens.length ? tokens : [new TextRun({ text, ...base })];
}

// ---------- frontmatter ----------
function splitFrontmatter(src) {
  const fm = {};
  if (src.startsWith("---")) {
    const end = src.indexOf("\n---", 3);
    if (end !== -1) {
      src.slice(3, end).split("\n").forEach(l => {
        const m = l.match(/^([a-zA-Z0-9_]+):\s*"?(.*?)"?\s*$/);
        if (m) fm[m[1]] = m[2];
      });
      return { fm, body: src.slice(end + 4) };
    }
  }
  return { fm, body: src };
}

// ---------- block tokenizer ----------
function tokenize(body) {
  const lines = body.replace(/\r/g, "").split("\n");
  const blocks = [];
  let i = 0;
  const isTable = l => /^\s*\|.*\|\s*$/.test(l);
  while (i < lines.length) {
    let line = lines[i];
    const t = line.trim();
    if (t === "") { i++; continue; }
    if (/^\\newpage/.test(t)) { blocks.push({ type: "pagebreak" }); i++; continue; }
    if (/^\\(vspace|newline|noindent)/.test(t)) { i++; continue; }
    let hm = t.match(/^(#{1,3})\s+(.*)$/);
    if (hm) { blocks.push({ type: "heading", level: hm[1].length, text: hm[2] }); i++; continue; }
    if (t.startsWith(">")) {
      const buf = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) { buf.push(lines[i].trim().replace(/^>\s?/, "")); i++; }
      blocks.push({ type: "quote", text: buf.join(" ").trim() });
      continue;
    }
    if (isTable(line)) {
      const rows = [];
      while (i < lines.length && isTable(lines[i])) {
        rows.push(lines[i].trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(c => c.trim()));
        i++;
      }
      blocks.push({ type: "table", rows });
      continue;
    }
    if (/^(\d+)\.\s+/.test(t)) {
      const items = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) { items.push(lines[i].trim().replace(/^\d+\.\s+/, "")); i++; }
      blocks.push({ type: "ol", items });
      continue;
    }
    if (/^[-*]\s+/.test(t)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) { items.push(lines[i].trim().replace(/^[-*]\s+/, "")); i++; }
      blocks.push({ type: "ul", items });
      continue;
    }
    // paragraph: collect until blank / structural line
    const buf = [];
    while (i < lines.length && lines[i].trim() !== "" && !isTable(lines[i]) &&
           !/^(#{1,3}\s|>|\\newpage|\d+\.\s|[-*]\s)/.test(lines[i].trim())) { buf.push(lines[i].trim()); i++; }
    blocks.push({ type: "p", text: buf.join(" ") });
  }
  return blocks;
}

// ---------- table helpers ----------
function txtCell(text, { w, fill, bold, color, head } = {}) {
  return new TableCell({
    borders: cellBorders, width: { size: w, type: WidthType.DXA },
    shading: fill ? { fill, type: ShadingType.CLEAR } : undefined,
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({ children: inlineRuns(String(text), { bold, color }) })],
  });
}
function isInfoCard(rows) {
  return rows.length >= 2 && rows[0].length === 2 && rows[0].every(c => c === "") && /^[-:\s]+$/.test(rows[1].join(""));
}
function renderTable(rows) {
  // drop separator row(s) like |---|---|
  const sepIdx = rows.findIndex(r => r.every(c => /^[-:]*$/.test(c)));
  const infoCard = isInfoCard(rows);
  const dataRows = rows.filter((r, idx) => idx !== sepIdx && !r.every(c => /^[-:]*$/.test(c)));
  const ncol = Math.max(...rows.map(r => r.length));
  if (infoCard) {
    const wL = 2700, wR = CW - wL;
    return new Table({ width: { size: CW, type: WidthType.DXA }, columnWidths: [wL, wR],
      rows: dataRows.filter(r => r.some(c => c !== "")).map(r => new TableRow({ children: [
        txtCell(r[0], { w: wL, fill: HEAD_FILL, bold: true }),
        txtCell(r[1] || "", { w: wR }),
      ] })) });
  }
  const colW = Math.floor(CW / ncol);
  const widths = Array.from({ length: ncol }, (_, k) => k === ncol - 1 ? CW - colW * (ncol - 1) : colW);
  const header = dataRows[0];
  const out = [new TableRow({ tableHeader: true, children: header.map((c, k) => txtCell(c, { w: widths[k], fill: ACCENT, bold: true, color: "FFFFFF" })) })];
  dataRows.slice(1).forEach((r, ri) => out.push(new TableRow({ children: widths.map((w, k) => txtCell(r[k] || "", { w, fill: ri % 2 ? ZEBRA : undefined })) })));
  return new Table({ width: { size: CW, type: WidthType.DXA }, columnWidths: widths, rows: out });
}

// ---------- build doc ----------
const raw = fs.readFileSync(inPath, "utf8");
const { fm, body } = splitFrontmatter(raw);
const blocks = tokenize(body);

const children = [];
// title from frontmatter, else first H1
let titled = false;
let skipFirstH1 = false;
if (fm.title) { children.push(new Paragraph({ style: "Title", children: [new TextRun(fm.title)] })); titled = true; skipFirstH1 = true; }
const sub = [fm.author, fm.date].filter(Boolean).join(" · ");
if (sub) children.push(new Paragraph({ spacing: { after: 160 }, children: [new TextRun({ text: sub, color: "777777" })] }));

for (const b of blocks) {
  if (b.type === "pagebreak") { children.push(new Paragraph({ children: [new PageBreak()] })); continue; }
  if (b.type === "heading") {
    if (b.level === 1 && skipFirstH1) { skipFirstH1 = false; continue; } // первый H1 == дубль title из фронтматтера
    if (b.level === 1 && titled) { // повторный H1 == заголовок раздела
      children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: inlineRuns(b.text) }));
    } else if (b.level === 1 && !titled) {
      children.push(new Paragraph({ style: "Title", children: inlineRuns(b.text) })); titled = true;
    } else {
      children.push(new Paragraph({ heading: b.level === 2 ? HeadingLevel.HEADING_2 : HeadingLevel.HEADING_3, children: inlineRuns(b.text) }));
    }
    continue;
  }
  if (b.type === "p") { children.push(new Paragraph({ spacing: { after: 120 }, children: inlineRuns(b.text) })); continue; }
  if (b.type === "ul") { b.items.forEach(it => children.push(new Paragraph({ numbering: { reference: "b", level: 0 }, spacing: { after: 60 }, children: inlineRuns(it) }))); continue; }
  if (b.type === "ol") { b.items.forEach(it => children.push(new Paragraph({ numbering: { reference: "n", level: 0 }, spacing: { after: 80 }, children: inlineRuns(it) }))); continue; }
  if (b.type === "table") { children.push(renderTable(b.rows)); children.push(new Paragraph({ spacing: { after: 120 }, children: [] })); continue; }
  if (b.type === "quote") {
    children.push(new Paragraph({ spacing: { before: 100, after: 160 },
      shading: { fill: CALLOUT, type: ShadingType.CLEAR },
      border: { left: { style: BorderStyle.SINGLE, size: 18, color: CALLOUT_BAR, space: 12 } },
      children: inlineRuns(b.text, { italics: true }) }));
    continue;
  }
}

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Title", name: "Title", basedOn: "Normal", next: "Normal",
        run: { size: 40, bold: true, color: ACCENT, font: "Arial" }, paragraph: { spacing: { after: 80 } } },
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, color: ACCENT, font: "Arial" },
        paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 0,
          border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 4 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, color: "1F1F1F", font: "Arial" }, paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, color: "444444", font: "Arial" }, paragraph: { spacing: { before: 140, after: 80 }, outlineLevel: 2 } },
    ],
  },
  numbering: { config: [
    { reference: "b", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 600, hanging: 280 } } } }] },
    { reference: "n", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 600, hanging: 320 } } } }] },
  ] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "Belberry · Аудит сделки", color: "999999", size: 18 })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
      new TextRun({ text: (FOOTER ? FOOTER + "   ·   " : ""), color: "999999", size: 18 }),
      new TextRun({ children: [PageNumber.CURRENT], color: "999999", size: 18 }),
    ] })] }) },
    children,
  }],
});

Packer.toBuffer(doc).then(b => { fs.writeFileSync(outPath, b); console.log("written", outPath, b.length, "bytes,", blocks.length, "blocks"); });
