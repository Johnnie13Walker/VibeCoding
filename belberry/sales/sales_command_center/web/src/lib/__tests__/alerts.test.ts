import { describe, expect, it } from 'vitest';
import { dealReason, dealSeverity, isOverdue } from '@/lib/alerts';

describe('dealReason', () => {
  it('нет бюджета при нулевой сумме', () => {
    expect(dealReason(0, 5)).toBe('нет бюджета');
  });
  it('критический возраст при ≥31 дн', () => {
    expect(dealReason(100_000, 31)).toBe('критический возраст');
  });
  it('застряла N дн в обычном случае', () => {
    expect(dealReason(100_000, 5)).toBe('застряла 5 дн.');
  });
});

describe('dealSeverity', () => {
  it('critical при ≥31 дн', () => {
    expect(dealSeverity(100_000, 31)).toBe('critical');
  });
  it('critical при крупной сумме и ≥14 дн', () => {
    expect(dealSeverity(600_000, 14)).toBe('critical');
  });
  it('warning в остальных случаях', () => {
    expect(dealSeverity(100_000, 5)).toBe('warning');
  });
});

describe('isOverdue', () => {
  const now = new Date('2026-06-03T12:00:00+03:00');
  it('дедлайн в прошлом → просрочено', () => {
    expect(isOverdue('2026-06-01T15:00:00+03:00', now)).toBe(true);
  });
  it('дедлайн в будущем → нет', () => {
    expect(isOverdue('2026-06-05T15:00:00+03:00', now)).toBe(false);
  });
  it('пустой дедлайн → нет', () => {
    expect(isOverdue(null, now)).toBe(false);
  });
});
