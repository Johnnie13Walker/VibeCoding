import { describe, expect, it } from 'vitest';
import { generateCode, hashCode, verifyCode } from '../code';

describe('code utilities', () => {
  it('generates a six-digit numeric code', () => {
    expect(generateCode()).toMatch(/^\d{6}$/);
  });

  it('hashes code to deterministic sha256 hex', () => {
    const hash = hashCode('123456');

    expect(hash).toMatch(/^[a-f0-9]{64}$/);
    expect(hashCode('123456')).toBe(hash);
  });

  it('verifies matching and non-matching codes', () => {
    const hash = hashCode('123456');

    expect(verifyCode('123456', hash)).toBe(true);
    expect(verifyCode('654321', hash)).toBe(false);
  });

  it('returns false for malformed hashes', () => {
    expect(verifyCode('123456', 'bad-hash')).toBe(false);
  });
});
