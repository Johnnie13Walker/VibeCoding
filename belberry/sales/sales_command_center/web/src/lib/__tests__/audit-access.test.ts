import { describe, expect, it } from 'vitest';
import { canSeeAudit } from '../audit-access';

describe('canSeeAudit — пилотный гейт «Аудит сделок» (только заказчик)', () => {
  it('пускает только allowlist-почту (регистр/пробелы не мешают)', () => {
    expect(canSeeAudit('es@belberry.net')).toBe(true);
    expect(canSeeAudit(' ES@Belberry.NET ')).toBe(true);
  });
  it('роль НЕ даёт доступа на время пилота', () => {
    expect(canSeeAudit('anyone@belberry.net', 'director')).toBe(false);
    expect(canSeeAudit('rop@belberry.net', 'rop')).toBe(false);
  });
  it('не пускает обычного менеджера и пустоту', () => {
    expect(canSeeAudit('manager@belberry.net', 'manager')).toBe(false);
    expect(canSeeAudit('', null)).toBe(false);
    expect(canSeeAudit(undefined)).toBe(false);
  });
});
