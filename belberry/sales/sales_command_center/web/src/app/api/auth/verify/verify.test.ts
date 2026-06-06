import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  findActiveUserByEmail: vi.fn(),
  consumeCode: vi.fn(),
  checkRateLimit: vi.fn(),
  getSession: vi.fn(),
  dbSelect: vi.fn(),
  eq: vi.fn(),
}));

vi.mock('drizzle-orm', () => ({ eq: mocks.eq }));
vi.mock('@/db', () => ({ db: { select: mocks.dbSelect } }));
vi.mock('@/db/schema', () => ({ users: { role: 'role', bitrixId: 'bitrix_id' } }));
vi.mock('@/lib/bitrix', () => ({ findActiveUserByEmail: mocks.findActiveUserByEmail }));
vi.mock('@/lib/loginCodes', () => ({ consumeCode: mocks.consumeCode }));
vi.mock('@/lib/rateLimit', () => ({ checkRateLimit: mocks.checkRateLimit }));
vi.mock('@/lib/session', () => ({ getSession: mocks.getSession }));

import { POST } from './route';

function request(body: unknown) {
  return new Request('http://localhost/api/auth/verify', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

function mockUserRole(role: string) {
  const limit = vi.fn().mockResolvedValue([{ role }]);
  const where = vi.fn(() => ({ limit }));
  const from = vi.fn(() => ({ where }));
  mocks.dbSelect.mockReturnValue({ from });
}

describe('verify route', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.eq.mockReturnValue('where');
    mocks.checkRateLimit.mockResolvedValue({ ok: true, remaining: 5 });
    mocks.consumeCode.mockResolvedValue({ ok: true, email: 'manager@example.com' });
    mocks.findActiveUserByEmail.mockResolvedValue({
      bitrixId: 42,
      email: 'manager@example.com',
      name: 'Manager',
    });
    mockUserRole('rop');
    mocks.getSession.mockResolvedValue({ save: vi.fn() });
  });

  it('rejects invalid body', async () => {
    const response = await POST(request({ email: 'manager@example.com', code: '123' }));

    expect(response.status).toBe(400);
    expect(mocks.consumeCode).not.toHaveBeenCalled();
  });

  it('blocks before consuming code when rate limited', async () => {
    mocks.checkRateLimit.mockResolvedValueOnce({ ok: false, remaining: 0 });

    const response = await POST(request({ email: 'manager@example.com', code: '123456' }));

    expect(response.status).toBe(429);
    expect(mocks.consumeCode).not.toHaveBeenCalled();
  });

  it('rejects invalid code', async () => {
    mocks.consumeCode.mockResolvedValueOnce({ ok: false, reason: 'mismatch' });

    const response = await POST(request({ email: 'manager@example.com', code: '000000' }));

    expect(response.status).toBe(401);
  });

  it('rejects inactive user after one-time code is consumed', async () => {
    mocks.findActiveUserByEmail.mockResolvedValueOnce(null);

    const response = await POST(request({ email: 'manager@example.com', code: '123456' }));

    expect(response.status).toBe(403);
  });

  it('saves session with local role', async () => {
    const session = { save: vi.fn() };
    mocks.getSession.mockResolvedValueOnce(session);

    const response = await POST(request({ email: 'Manager@Example.com', code: '123456' }));

    await expect(response.json()).resolves.toEqual({ ok: true });
    expect(session).toMatchObject({
      bitrixId: 42,
      email: 'manager@example.com',
      role: 'rop',
    });
    expect(session.save).toHaveBeenCalledOnce();
  });
});
