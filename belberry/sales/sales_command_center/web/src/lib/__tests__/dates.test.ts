import { describe, expect, it } from 'vitest';
import { isReportAvailable, parseReportDate } from '../dates';

describe('report date parsing', () => {
  it('accepts real YYYY-MM-DD dates', () => {
    expect(parseReportDate('2026-05-29')).toBe('2026-05-29');
  });

  it.each(['2026-13-40', '2026-02-31', '29-05-2026', 'foo', ''])(
    'rejects invalid date %s',
    (value) => {
      expect(parseReportDate(value)).toBeNull();
    },
  );

  it('checks date availability from arrays and sets', () => {
    expect(isReportAvailable('2026-05-29', ['2026-05-29'])).toBe(true);
    expect(isReportAvailable('2026-05-30', new Set(['2026-05-29']))).toBe(false);
  });
});
