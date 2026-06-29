import { describe, it, expect } from 'vitest';
import { canSeePortfolio } from '../portfolio-access';

describe('canSeePortfolio (пока только владелец)', () => {
  it('видит директор, владелец по email и по bitrixId 12', () => {
    expect(canSeePortfolio('any@x.ru', 'director')).toBe(true);
    expect(canSeePortfolio('es@belberry.net', 'manager')).toBe(true);
    expect(canSeePortfolio('ES@Belberry.net ', 'manager')).toBe(true);
    expect(canSeePortfolio(null, null, 12)).toBe(true);
  });
  it('рядовой менеджер не видит', () => {
    expect(canSeePortfolio('mop@belberry.net', 'manager')).toBe(false);
    expect(canSeePortfolio('rop@belberry.net', 'rop', 2188)).toBe(false);
    expect(canSeePortfolio(undefined, undefined, undefined)).toBe(false);
  });
});
