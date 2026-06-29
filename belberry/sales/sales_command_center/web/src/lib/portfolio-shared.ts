// Чистая логика витрины «Портфолио» (без сети) — парс листов Sheet, маппинг услуг,
// мердж кейсов, агрегаты и фильтры. Тестируется юнитами без Google API.

export interface PortfolioProject {
  project: string;
  domain: string | null;
  category: string; // ниша
  subcategory: string;
  services: string[]; // человекочитаемые услуги
  rawServices: string[];
  years: string;
  period: string;
  lastYear: string;
  status: string;
  brand: string;
  experienceMonths: number | null;
  siteActive: boolean;
  // богатый кейс (из «Портфолио WD», матч по домену) — есть не у всех
  caseUrl: string | null;
  caseDescription: string | null;
  caseType: string | null; // LP / TB / WD
}

// Коды услуг → человекочитаемые названия (расшифровка подтверждена пользователем
// 29.06). Program и Deposit — обе техподдержка сайта; WD — инд. дизайн; TB —
// шаблон медсайта Belberry; WDT (в данных может быть «ЦЕВ») — сайт на шаблоне 1С-Битрикс.
export const SERVICE_LABELS: Record<string, string> = {
  SEO: 'SEO',
  PPC: 'Контекст',
  WD: 'Разработка сайта (инд. дизайн)',
  TB: 'Шаблон медсайта Belberry',
  WDT: 'Сайт на шаблоне 1С-Битрикс',
  ЦЕВ: 'Сайт на шаблоне 1С-Битрикс',
  LP: 'Лендинг',
  SMM: 'SMM',
  ORM: 'ORM',
  GEO: 'GEO',
  AEO: 'AEO',
  Content: 'Контент',
  Branding: 'Фирменный стиль',
  Dzen: 'Дзен',
  Foto: 'Фотосъёмка',
  Таргет: 'Таргет',
  Audit: 'Аудит',
  Program: 'Техподдержка сайта',
  Deposit: 'Техподдержка сайта',
  Marketing: 'Маркетинг',
  Б24: 'Битрикс24',
};
// Все коды теперь — услуги; ничего не скрываем.
const HIDDEN_SERVICES = new Set<string>();

export function serviceLabel(code: string): string {
  const c = code.trim();
  return SERVICE_LABELS[c] ?? c;
}

/** Нормализует домен: убирает протокол/www/путь/хвостовой слеш, нижний регистр. */
export function normalizeDomain(value: string | null | undefined): string | null {
  if (!value) return null;
  let s = String(value).trim().toLowerCase();
  if (!s || s === '-') return null;
  s = s.replace(/^https?:\/\//, '').replace(/^www\./, '');
  s = s.split(/[/?#]/)[0];
  return s || null;
}

function headerIndex(headers: string[]): Map<string, number> {
  const m = new Map<string, number>();
  headers.forEach((h, i) => m.set(h.trim().toLowerCase(), i));
  return m;
}
function pick(row: string[], idx: number | undefined): string {
  return idx == null || idx < 0 ? '' : (row[idx] ?? '').trim();
}

/**
 * Парсит лист «Клиенты». rows — values начиная с СТРОКИ ЗАГОЛОВКА (строка 13 в Sheet).
 * Колонки: Проект, Категория, Подкатегория, Услуги, Годы, Период, Последний год,
 * Статус, Бренд, Опыт мес., Сайт активен, 2021…2026.
 */
export function parseClients(rows: string[][]): PortfolioProject[] {
  if (!rows.length) return [];
  const idx = headerIndex(rows[0]);
  const ci = {
    project: idx.get('проект'),
    category: idx.get('категория'),
    subcategory: idx.get('подкатегория'),
    services: idx.get('услуги'),
    years: idx.get('годы'),
    period: idx.get('период'),
    lastYear: idx.get('последний год'),
    status: idx.get('статус'),
    brand: idx.get('бренд'),
    exp: idx.get('опыт, мес.') ?? idx.get('опыт, мес') ?? idx.get('опыт мес.'),
    active: idx.get('сайт активен'),
  };
  const out: PortfolioProject[] = [];
  for (const row of rows.slice(1)) {
    const project = pick(row, ci.project);
    if (!project) continue;
    const rawServices = pick(row, ci.services)
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s && !HIDDEN_SERVICES.has(s));
    const services = [...new Set(rawServices.map(serviceLabel))];
    const expRaw = pick(row, ci.exp).replace(/[^\d]/g, '');
    const activeRaw = pick(row, ci.active).toLowerCase();
    out.push({
      project,
      domain: normalizeDomain(project),
      category: pick(row, ci.category) || 'Не определено',
      subcategory: pick(row, ci.subcategory),
      services,
      rawServices,
      years: pick(row, ci.years),
      period: pick(row, ci.period),
      lastYear: pick(row, ci.lastYear),
      status: pick(row, ci.status),
      brand: pick(row, ci.brand),
      experienceMonths: expRaw ? Number(expRaw) : null,
      siteActive: ['да', 'yes', 'true', '1', '+'].includes(activeRaw),
      caseUrl: null,
      caseDescription: null,
      caseType: null,
    });
  }
  return out;
}

export interface WdCase {
  domain: string | null;
  caseUrl: string | null;
  description: string;
  type: string;
}

/** Ссылка на кейс считается «опубликованной на сайте», если ведёт на belberry.net/acoola.team. */
export function isSiteCaseUrl(url: string | null): boolean {
  return !!url && /(?:belberry\.net|acoola\.team)/i.test(url);
}

/**
 * Парсит «Портфолио WD». rows начинаются с заголовка (строка 1). Данные с 3-й строки
 * (строка 2 — «Пример заполнения»). Матч с «Клиентами» по домену из «Ссылка на бой».
 */
export function parseWdCases(rows: string[][]): WdCase[] {
  if (rows.length < 2) return [];
  const idx = headerIndex(rows[0]);
  const ci = {
    boj: idx.get('ссылка на бой'),
    caseUrl: idx.get('ссылка на кейс'),
    desc: idx.get('описание проекта'),
    type: idx.get('тип'),
  };
  const out: WdCase[] = [];
  for (const row of rows.slice(1)) {
    const domain = normalizeDomain(pick(row, ci.boj));
    if (!domain) continue;
    const rawCase = pick(row, ci.caseUrl);
    const caseUrl = isSiteCaseUrl(rawCase) ? rawCase : null;
    out.push({ domain, caseUrl, description: pick(row, ci.desc), type: pick(row, ci.type) });
  }
  return out;
}

/** Подмешивает богатый кейс (caseUrl/описание/тип) к проектам по совпадению домена. */
export function mergeWdCases(projects: PortfolioProject[], cases: WdCase[]): PortfolioProject[] {
  const byDomain = new Map<string, WdCase>();
  for (const c of cases) if (c.domain && !byDomain.has(c.domain)) byDomain.set(c.domain, c);
  return projects.map((p) => {
    const c = p.domain ? byDomain.get(p.domain) : undefined;
    if (!c) return p;
    return { ...p, caseUrl: c.caseUrl, caseDescription: c.description || null, caseType: c.type || null };
  });
}

export interface NicheCount {
  niche: string;
  count: number;
}
export function aggregateNiches(projects: PortfolioProject[]): NicheCount[] {
  const m = new Map<string, number>();
  for (const p of projects) m.set(p.category, (m.get(p.category) ?? 0) + 1);
  return [...m.entries()].map(([niche, count]) => ({ niche, count })).sort((a, b) => b.count - a.count);
}
export function aggregateServices(projects: PortfolioProject[]): NicheCount[] {
  const m = new Map<string, number>();
  for (const p of projects) for (const s of p.services) m.set(s, (m.get(s) ?? 0) + 1);
  return [...m.entries()].map(([niche, count]) => ({ niche, count })).sort((a, b) => b.count - a.count);
}

export interface PortfolioFilter {
  niche?: string | null; // null/undefined = все
  service?: string | null;
  onlyWithCase?: boolean;
  query?: string;
}
export function filterProjects(projects: PortfolioProject[], f: PortfolioFilter): PortfolioProject[] {
  const q = (f.query ?? '').trim().toLowerCase();
  return projects.filter((p) => {
    if (f.niche && p.category !== f.niche) return false;
    if (f.service && !p.services.includes(f.service)) return false;
    if (f.onlyWithCase && !p.caseUrl) return false;
    if (q && !(`${p.project} ${p.brand}`.toLowerCase().includes(q))) return false;
    return true;
  });
}
