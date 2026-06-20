import { describe, expect, it } from 'vitest';
import { safeLoginRedirect } from '../loginRedirect';

describe('safeLoginRedirect', () => {
  it('keeps normal app paths', () => {
    expect(safeLoginRedirect('/meetings')).toBe('/meetings');
  });

  it('falls back to root for auth api and unsafe redirects', () => {
    expect(safeLoginRedirect('/api/auth')).toBe('/');
    expect(safeLoginRedirect('/api/auth/verify')).toBe('/');
    expect(safeLoginRedirect('/login')).toBe('/');
    expect(safeLoginRedirect('https://example.com')).toBe('/');
    expect(safeLoginRedirect('//example.com')).toBe('/');
    expect(safeLoginRedirect(undefined)).toBe('/');
  });
});
