import { describe, expect, it } from 'vitest';
import { canSeeKp } from '../kp-access';

describe('canSeeKp — пилотный гейт страницы КП', () => {
  it('пускает только es@belberry.net (регистр/пробелы не мешают)', () => {
    expect(canSeeKp('es@belberry.net')).toBe(true);
    expect(canSeeKp(' ES@Belberry.NET ')).toBe(true);
  });
  it('не пускает остальных и пустоту', () => {
    expect(canSeeKp('manager@belberry.net')).toBe(false);
    expect(canSeeKp('')).toBe(false);
    expect(canSeeKp(undefined)).toBe(false);
    expect(canSeeKp(null)).toBe(false);
  });
});
