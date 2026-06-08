import { describe, expect, it } from 'vitest';
import {
  dealReason,
  dealSeverity,
  isOverdue,
  silenceDays,
  silenceReason,
  silenceSeverity,
} from '@/lib/alerts';

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

describe('silenceDays', () => {
  const snap = '2026-06-07';
  it('кал. дни от последней коммуникации до снимка', () => {
    expect(silenceDays('2026-05-24', null, snap)).toBe(14);
    expect(silenceDays('2026-05-04', null, snap)).toBe(34);
  });
  it('будущая/сегодняшняя дата → 0, не отрицательное', () => {
    expect(silenceDays('2026-06-07', null, snap)).toBe(0);
    expect(silenceDays('2026-06-20', null, snap)).toBe(0);
  });
  it('контакта не было → возраст застоя как нижняя оценка', () => {
    expect(silenceDays(null, 40, snap)).toBe(40);
  });
  it('контакта не было и возраст неизвестен → null (не судим)', () => {
    expect(silenceDays(null, null, snap)).toBeNull();
    expect(silenceDays(null, 0, snap)).toBeNull();
  });
});

describe('silenceSeverity', () => {
  it('critical при ≥30 дн', () => {
    expect(silenceSeverity(30)).toBe('critical');
    expect(silenceSeverity(34)).toBe('critical');
  });
  it('warning при 15..29 дн', () => {
    expect(silenceSeverity(15)).toBe('warning');
    expect(silenceSeverity(29)).toBe('warning');
  });
});

describe('silenceReason', () => {
  it('молчит N дн при наличии контакта', () => {
    expect(silenceReason('2026-05-04', 34)).toBe('молчит 34 дн.');
  });
  it('контакта не было при null', () => {
    expect(silenceReason(null, 40)).toBe('контакта не было');
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
