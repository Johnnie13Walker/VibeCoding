import { createHash, randomInt, timingSafeEqual } from 'node:crypto';

export function generateCode(): string {
  return randomInt(0, 1_000_000).toString().padStart(6, '0');
}

export function hashCode(code: string): string {
  return createHash('sha256').update(code, 'utf8').digest('hex');
}

export function verifyCode(plain: string, hash: string): boolean {
  if (!/^[a-f0-9]{64}$/.test(hash)) {
    return false;
  }

  const expected = Buffer.from(hash, 'hex');
  const actual = Buffer.from(hashCode(plain), 'hex');

  if (expected.length !== actual.length) {
    return false;
  }

  return timingSafeEqual(expected, actual);
}
