import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  findActiveUserByEmail: vi.fn(),
  sendCodeMessage: vi.fn(),
  issueCode: vi.fn(),
  checkRateLimit: vi.fn(),
}));

vi.mock('@/lib/bitrix', () => ({
  findActiveUserByEmail: mocks.findActiveUserByEmail,
  sendCodeMessage: mocks.sendCodeMessage,
}));
vi.mock('@/lib/loginCodes', () => ({ issueCode: mocks.issueCode }));
vi.mock('@/lib/rateLimit', () => ({ checkRateLimit: mocks.checkRateLimit }));

import { POST } from './route';

function request(body: unknown) {
  return new Request('http://localhost/api/auth/request-code', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

describe('request-code route', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.checkRateLimit.mockResolvedValue({ ok: true, remaining: 5 });
    mocks.findActiveUserByEmail.mockResolvedValue({
      bitrixId: 2812,
      email: 'manager@example.com',
      name: 'Manager',
    });
    mocks.issueCode.mockResolvedValue('123456');
    mocks.sendCodeMessage.mockResolvedValue(undefined);
  });

  it('rejects invalid email', async () => {
    const response = await POST(request({ email: 'bad' }));

    expect(response.status).toBe(400);
    expect(mocks.findActiveUserByEmail).not.toHaveBeenCalled();
  });

  it('returns 404 and does not issue code when user is not active', async () => {
    mocks.findActiveUserByEmail.mockResolvedValueOnce(null);

    const response = await POST(request({ email: 'missing@example.com' }));

    expect(response.status).toBe(404);
    expect(mocks.issueCode).not.toHaveBeenCalled();
    expect(mocks.sendCodeMessage).not.toHaveBeenCalled();
  });

  it('blocks rate-limited email before issuing code', async () => {
    mocks.checkRateLimit.mockResolvedValueOnce({ ok: false, remaining: 0 });

    const response = await POST(request({ email: 'manager@example.com' }));

    expect(response.status).toBe(429);
    expect(mocks.issueCode).not.toHaveBeenCalled();
  });

  it('issues and sends code', async () => {
    const response = await POST(request({ email: 'Manager@Example.com' }));

    await expect(response.json()).resolves.toEqual({ ok: true });
    expect(mocks.issueCode).toHaveBeenCalledWith('manager@example.com');
    expect(mocks.sendCodeMessage).toHaveBeenCalledWith(2812, '123456');
  });
});
