import { afterEach, describe, expect, it } from 'vitest';
import { isSameOrigin } from '../origin';

function req(headers: Record<string, string>): Request {
  return new Request('http://localhost/api/x', { method: 'POST', headers });
}

describe('isSameOrigin (CSRF guard)', () => {
  const prevBase = process.env.SCC_BASE_URL;
  afterEach(() => {
    if (prevBase === undefined) delete process.env.SCC_BASE_URL;
    else process.env.SCC_BASE_URL = prevBase;
  });

  it('allows when Origin host matches forwarded Host', () => {
    expect(isSameOrigin(req({ host: 'blbr-team.net', origin: 'https://blbr-team.net' }))).toBe(true);
  });

  it('allows when Origin matches SCC_BASE_URL even if Host differs', () => {
    process.env.SCC_BASE_URL = 'https://blbr-team.net';
    expect(isSameOrigin(req({ host: '127.0.0.1:3010', origin: 'https://blbr-team.net' }))).toBe(true);
  });

  it('blocks a foreign Origin', () => {
    expect(isSameOrigin(req({ host: 'blbr-team.net', origin: 'https://evil.example' }))).toBe(false);
  });

  it('fails open when Origin header is absent', () => {
    expect(isSameOrigin(req({ host: 'blbr-team.net' }))).toBe(true);
  });

  it('blocks an unparseable Origin', () => {
    expect(isSameOrigin(req({ host: 'blbr-team.net', origin: 'not-a-url' }))).toBe(false);
  });
});
