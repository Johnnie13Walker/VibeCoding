import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  dbSelect: vi.fn(),
}));

vi.mock('@/db', () => ({ db: { select: mocks.dbSelect } }));
vi.mock('@/db/schema', () => ({
  reports: {
    reportDate: 'report_date',
    status: 'status',
    html: 'html',
  },
}));
vi.mock('drizzle-orm', () => ({
  desc: vi.fn((value) => ({ desc: value })),
  eq: vi.fn((left, right) => ({ eq: [left, right] })),
  inArray: vi.fn((left, right) => ({ inArray: [left, right] })),
}));

import { availableReportDates, getReportHtml } from '../reports';

function mockSelectResult<T>(rows: T[]) {
  const limit = vi.fn().mockResolvedValue(rows);
  const orderBy = vi.fn().mockResolvedValue(rows);
  const where = vi.fn(() => ({ limit, orderBy }));
  const from = vi.fn(() => ({ where }));
  mocks.dbSelect.mockReturnValue({ from });
  return { from, where, limit, orderBy };
}

describe('reports reader', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns only ready report dates', async () => {
    mockSelectResult([
      { d: '2026-05-30', status: 'partial_llm_failure' },
      { d: '2026-05-29', status: 'done' },
      { d: '2026-05-28', status: 'pending' },
      { d: '2026-05-27', status: 'error' },
    ]);

    await expect(availableReportDates()).resolves.toEqual(['2026-05-30', '2026-05-29']);
  });

  it('returns html for done and partial reports', async () => {
    mockSelectResult([{ html: '<!DOCTYPE html><html></html>', status: 'done' }]);

    await expect(getReportHtml('2026-05-29')).resolves.toBe(
      '<!DOCTYPE html><html></html>',
    );
  });

  it('returns null for missing report', async () => {
    mockSelectResult([]);

    await expect(getReportHtml('2026-01-01')).resolves.toBeNull();
  });

  it('returns null for empty html or non-ready status', async () => {
    mockSelectResult([{ html: '', status: 'done' }]);
    await expect(getReportHtml('2026-05-29')).resolves.toBeNull();

    mockSelectResult([{ html: '<html></html>', status: 'pending' }]);
    await expect(getReportHtml('2026-05-29')).resolves.toBeNull();
  });
});
