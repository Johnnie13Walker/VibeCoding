import { describe, expect, it } from 'vitest';
import { canSeeAudit } from '../audit-access';

describe('canSeeAudit — открыт всем авторизованным (пилот завершён)', () => {
  it('пускает любого сотрудника независимо от роли', () => {
    expect(canSeeAudit('es@belberry.net')).toBe(true);
    expect(canSeeAudit('manager@belberry.net', 'manager')).toBe(true);
    expect(canSeeAudit('rop@belberry.net', 'rop')).toBe(true);
  });
  // Авторизация (наличие сессии) проверяется отдельно в страницах/роутах,
  // поэтому сам гейт доступа теперь всегда true.
  it('не зависит от наличия почты', () => {
    expect(canSeeAudit('', null)).toBe(true);
    expect(canSeeAudit(undefined)).toBe(true);
  });
});
