import { describe, expect, it } from 'vitest';
import { dealReason, dealSeverity, isPromiseOverdue } from '@/lib/alerts';

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

describe('isPromiseOverdue', () => {
  it('дата-дедлайн в прошлом → просрочено', () => {
    expect(isPromiseOverdue('2026-06-01', '2026-06-03')).toBe(true);
  });
  it('дата-дедлайн в будущем → нет', () => {
    expect(isPromiseOverdue('2026-06-05', '2026-06-03')).toBe(false);
  });
  it('свободный текст не считаем просрочкой', () => {
    expect(isPromiseOverdue('на этой неделе', '2026-06-03')).toBe(false);
  });
  it('пустой дедлайн → нет', () => {
    expect(isPromiseOverdue(null, '2026-06-03')).toBe(false);
  });
});
