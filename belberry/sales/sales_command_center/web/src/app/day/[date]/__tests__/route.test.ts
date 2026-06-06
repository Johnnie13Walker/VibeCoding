import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
  getReportHtml: vi.fn(),
}));

vi.mock('@/lib/session', () => ({ getSession: mocks.getSession }));
vi.mock('@/lib/reports', () => ({ getReportHtml: mocks.getReportHtml }));

import { GET } from '../route';

function request(date: string) {
  return new Request(`http://localhost/day/${date}`);
}

function context(date: string) {
  return {
    params: Promise.resolve({ date }),
  };
}

describe('day report route', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getSession.mockResolvedValue({ bitrixId: 42 });
    mocks.getReportHtml.mockResolvedValue(
      '<!DOCTYPE html><html lang="ru"><head><style>body{color:red}</style></head><body><h1>OK</h1></body></html>',
    );
  });

  it('returns 401 without session', async () => {
    mocks.getSession.mockResolvedValueOnce({});

    const response = await GET(request('2026-05-29'), context('2026-05-29'));

    expect(response.status).toBe(401);
    expect(mocks.getReportHtml).not.toHaveBeenCalled();
  });

  it('sanitizes report html before returning it', async () => {
    mocks.getReportHtml.mockResolvedValueOnce(
      '<!DOCTYPE html><html lang="ru"><head><style>body{color:red}</style></head><body><h1>OK</h1><script>alert(1)</script></body></html>',
    );

    const response = await GET(request('2026-05-29'), context('2026-05-29'));
    const body = await response.text();

    expect(response.status).toBe(200);
    expect(response.headers.get('Content-Type')).toContain('text/html');
    expect(body).not.toContain('<script');
    expect(body).toContain('<style>');
  });

  it('returns 404 for invalid dates', async () => {
    const response = await GET(request('foo'), context('foo'));

    expect(response.status).toBe(404);
    expect(mocks.getReportHtml).not.toHaveBeenCalled();
  });

  it('returns 404 html when report is absent', async () => {
    mocks.getReportHtml.mockResolvedValueOnce(null);

    const response = await GET(request('2026-01-01'), context('2026-01-01'));
    const body = await response.text();

    expect(response.status).toBe(404);
    expect(response.headers.get('Content-Type')).toContain('text/html');
    expect(body).toContain('Нет отчёта');
  });
});
