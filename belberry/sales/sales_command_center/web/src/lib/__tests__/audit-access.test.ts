import { describe, expect, it } from 'vitest';
import { canSeeAudit } from '../audit-access';

describe('canSeeAudit — гейт страницы «Аудит сделок»', () => {
  it('пускает руководителя и РОП по роли', () => {
    expect(canSeeAudit('anyone@belberry.net', 'director')).toBe(true);
    expect(canSeeAudit('anyone@belberry.net', 'rop')).toBe(true);
  });
  it('пускает allowlist-почту независимо от роли (регистр/пробелы не мешают)', () => {
    expect(canSeeAudit('es@belberry.net')).toBe(true);
    expect(canSeeAudit(' ES@Belberry.NET ', 'manager')).toBe(true);
  });
  it('не пускает обычного менеджера и пустоту', () => {
    expect(canSeeAudit('manager@belberry.net', 'manager')).toBe(false);
    expect(canSeeAudit('', null)).toBe(false);
    expect(canSeeAudit(undefined)).toBe(false);
  });
});
