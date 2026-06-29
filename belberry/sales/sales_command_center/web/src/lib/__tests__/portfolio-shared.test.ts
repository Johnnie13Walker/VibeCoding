import { describe, it, expect } from 'vitest';
import {
  serviceLabel,
  normalizeDomain,
  isSiteCaseUrl,
  parseClients,
  parseWdCases,
  mergeWdCases,
  aggregateNiches,
  aggregateServices,
  filterProjects,
} from '../portfolio-shared';

const CLIENTS = [
  ['Проект', 'Категория', 'Подкатегория', 'Услуги', 'Годы', 'Период', 'Последний год', 'Статус', 'Бренд', 'Опыт, мес.', 'Сайт активен', '2021', '2022', '2023', '2024', '2025', '2026'],
  ['k-medica.ru', 'Медицина', 'Клиника', 'WD, SEO, Deposit', '2022,2024', '2022→2026', '2026', 'активен', 'К медицина', '48', 'да', '', '', '', '', '', ''],
  ['stomklinika.ru', 'Стоматология', '', 'SEO, PPC', '2021', '2021→2026', '2026', 'активен', '', '60', 'Да', '', '', '', '', '', ''],
  ['', 'Медицина', '', 'SEO', '', '', '', '', '', '', '', '', '', '', '', '', ''], // пустой проект — пропуск
];

const WD = [
  ['Название проекта', 'Ссылка на тестовый сайт', 'Ссылка на бой', 'Год разработки', 'Сфера', 'Статус', 'Сотрудничество', 'Тип', 'Есть лого', 'Ссылка на кейс', 'Описание проекта', 'Аккаунт проекта', '', 'Шаблон', 'Ссылка на шаблон'],
  ['Пример заполнения', '', '', '', '', '', '', '', '', 'ссылка', '', '', '', '', ''],
  ['К медицина', '', 'https://k-medica.ru/', 'до 2023', 'Медицина', 'готов', 'нет', 'WD', 'Есть', 'https://belberry.net/works/k-medica', 'Индивидуальная разработка клиники', 'Гундарев', '', '', ''],
  ['Без кейса', '', 'https://stomklinika.ru/', '2024', 'Стом', 'готов', '', 'WD', '', '-', 'desc', '', '', '', ''],
];

describe('serviceLabel + normalizeDomain', () => {
  it('коды услуг → человеческие названия', () => {
    expect(serviceLabel('SEO')).toBe('SEO');
    expect(serviceLabel('PPC')).toBe('Контекст');
    expect(serviceLabel('WD')).toBe('Разработка сайта (инд. дизайн)');
    expect(serviceLabel('Program')).toBe('Техподдержка сайта');
    expect(serviceLabel('Deposit')).toBe('Техподдержка сайта');
    expect(serviceLabel('WDT')).toBe('Сайт на шаблоне 1С-Битрикс');
    expect(serviceLabel('НовыйКод')).toBe('НовыйКод');
  });
  it('домен нормализуется', () => {
    expect(normalizeDomain('https://www.K-Medica.ru/about?x=1')).toBe('k-medica.ru');
    expect(normalizeDomain('-')).toBeNull();
    expect(normalizeDomain('')).toBeNull();
  });
  it('кейс на сайте только belberry.net/acoola.team', () => {
    expect(isSiteCaseUrl('https://belberry.net/works/x')).toBe(true);
    expect(isSiteCaseUrl('https://acoola.team/projects/y')).toBe(true);
    expect(isSiteCaseUrl('https://example.com/case')).toBe(false);
    expect(isSiteCaseUrl('-')).toBe(false);
    expect(isSiteCaseUrl(null)).toBe(false);
  });
});

describe('parseClients', () => {
  const projects = parseClients(CLIENTS);
  it('пропускает пустые строки', () => {
    expect(projects).toHaveLength(2);
  });
  it('коды замаплены, Deposit→Техподдержка (дедуп с Program)', () => {
    const k = projects.find((p) => p.project === 'k-medica.ru')!;
    expect(k.services).toEqual(['Разработка сайта (инд. дизайн)', 'SEO', 'Техподдержка сайта']);
    expect(k.domain).toBe('k-medica.ru');
    expect(k.experienceMonths).toBe(48);
    expect(k.siteActive).toBe(true);
  });
});

describe('parseWdCases + merge', () => {
  it('кейс подмешивается по домену, «-» не считается кейсом', () => {
    const merged = mergeWdCases(parseClients(CLIENTS), parseWdCases(WD));
    const k = merged.find((p) => p.project === 'k-medica.ru')!;
    expect(k.caseUrl).toBe('https://belberry.net/works/k-medica');
    expect(k.caseDescription).toContain('Индивидуальная');
    const s = merged.find((p) => p.project === 'stomklinika.ru')!;
    expect(s.caseUrl).toBeNull(); // в WD стоит «-»
  });
});

describe('aggregate + filter', () => {
  const merged = mergeWdCases(parseClients(CLIENTS), parseWdCases(WD));
  it('агрегаты ниш и услуг', () => {
    expect(aggregateNiches(merged).find((n) => n.niche === 'Медицина')?.count).toBe(1);
    expect(aggregateServices(merged).find((s) => s.niche === 'SEO')?.count).toBe(2);
  });
  it('фильтр по нише/услуге/кейсу/поиску', () => {
    expect(filterProjects(merged, { niche: 'Стоматология' })).toHaveLength(1);
    expect(filterProjects(merged, { service: 'SEO' })).toHaveLength(2);
    expect(filterProjects(merged, { onlyWithCase: true })).toHaveLength(1);
    expect(filterProjects(merged, { query: 'stom' })).toHaveLength(1);
  });
});
