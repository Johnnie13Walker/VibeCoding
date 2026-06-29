import { describe, it, expect } from 'vitest';
import { canSeePortfolio } from '../portfolio-access';

describe('canSeePortfolio (открыто всем)', () => {
  it('виден любому авторизованному сотруднику', () => {
    expect(canSeePortfolio('any@x.ru', 'manager')).toBe(true);
    expect(canSeePortfolio('rop@belberry.net', 'rop', 2188)).toBe(true);
    expect(canSeePortfolio(undefined, undefined, undefined)).toBe(true);
  });
});
