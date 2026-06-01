import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getIronSession: vi.fn(),
}));

vi.mock('iron-session', () => ({ getIronSession: mocks.getIronSession }));

import { NextRequest } from 'next/server';
import { middleware } from '../../middleware';

function request(pathname: string) {
  return new NextRequest(`http://localhost${pathname}`);
}

describe('middleware', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getIronSession.mockResolvedValue({});
  });

  it('redirects unauthenticated root to login', async () => {
    const response = await middleware(request('/'));

    expect(response.status).toBe(307);
    expect(response.headers.get('location')).toContain('/login?redirect=%2F');
    expect(response.headers.get('X-Robots-Tag')).toBe('noindex, nofollow');
  });

  it('allows login page', async () => {
    const response = await middleware(request('/login'));

    expect(response.status).toBe(200);
    expect(mocks.getIronSession).not.toHaveBeenCalled();
    expect(response.headers.get('X-Robots-Tag')).toBe('noindex, nofollow');
  });

  it('allows auth api handlers', async () => {
    const response = await middleware(request('/api/auth/verify'));

    expect(response.status).toBe(200);
    expect(mocks.getIronSession).not.toHaveBeenCalled();
  });

  it('allows authenticated root', async () => {
    mocks.getIronSession.mockResolvedValueOnce({ bitrixId: 42 });

    const response = await middleware(request('/'));

    expect(response.status).toBe(200);
    expect(response.headers.get('X-Robots-Tag')).toBe('noindex, nofollow');
  });
});
