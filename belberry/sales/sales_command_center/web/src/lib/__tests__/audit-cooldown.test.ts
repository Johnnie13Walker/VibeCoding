import { describe, expect, it } from 'vitest';

// db не трогаем — тестируем чистую логику запрета повтора (раз в 45 дней).
import { AUDIT_COOLDOWN_DAYS, isAuditOnCooldown, nextAuditAvailableAt } from '../audit';

const DAY = 86_400_000;

describe('запрет повтора аудита (45 дней)', () => {
  it('окно — ровно 45 дней', () => {
    expect(AUDIT_COOLDOWN_DAYS).toBe(45);
    const last = new Date('2026-06-01T10:00:00Z');
    expect(nextAuditAvailableAt(last).toISOString()).toBe(new Date(last.getTime() + 45 * DAY).toISOString());
  });

  it('свежий аудит (10 дней назад) — запрет активен', () => {
    const now = new Date('2026-06-25T12:00:00Z');
    const last = new Date(now.getTime() - 10 * DAY);
    expect(isAuditOnCooldown(last, now)).toBe(true);
  });

  it('старый аудит (50 дней назад) — повтор разрешён', () => {
    const now = new Date('2026-06-25T12:00:00Z');
    const last = new Date(now.getTime() - 50 * DAY);
    expect(isAuditOnCooldown(last, now)).toBe(false);
  });

  it('граница: 44 дня — ещё запрет, 45 дней — уже можно', () => {
    const now = new Date('2026-06-25T12:00:00Z');
    expect(isAuditOnCooldown(new Date(now.getTime() - 44 * DAY), now)).toBe(true);
    // ровно через 45 дней запрет снимается (now == nextAvailableAt → не раньше)
    expect(isAuditOnCooldown(new Date(now.getTime() - 45 * DAY), now)).toBe(false);
  });
});
