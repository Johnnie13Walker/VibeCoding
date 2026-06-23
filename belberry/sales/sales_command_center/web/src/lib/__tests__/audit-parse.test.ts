import { describe, expect, it } from 'vitest';
import { parseDealId } from '../audit';

describe('parseDealId — ID сделки из ввода', () => {
  it('берёт ID из ссылки, а не «24» из bitrix24', () => {
    expect(parseDealId('https://belberrycrm.bitrix24.ru/crm/deal/details/23332/')).toBe(23332);
    expect(parseDealId('https://belberrycrm.bitrix24.ru/crm/deal/details/23332/?any=details%2F23332%2F')).toBe(23332);
  });
  it('принимает голый ID', () => {
    expect(parseDealId('23332')).toBe(23332);
    expect(parseDealId('  24200 ')).toBe(24200);
  });
  it('низкий ID из ссылки не теряется', () => {
    expect(parseDealId('https://belberrycrm.bitrix24.ru/crm/deal/details/24/')).toBe(24);
  });
  it('мусор → null', () => {
    expect(parseDealId('')).toBeNull();
    expect(parseDealId('просто текст')).toBeNull();
    expect(parseDealId('0')).toBeNull();
  });
});
