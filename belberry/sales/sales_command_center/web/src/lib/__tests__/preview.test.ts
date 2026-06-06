import { afterEach, describe, expect, it, vi } from 'vitest';
import { isPreviewMode } from '../preview';

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('isPreviewMode', () => {
  it('выключен без флага', () => {
    vi.stubEnv('SCC_PREVIEW', '');
    vi.stubEnv('NODE_ENV', 'development');
    expect(isPreviewMode()).toBe(false);
  });

  it('включён при SCC_PREVIEW=1 вне прода', () => {
    vi.stubEnv('SCC_PREVIEW', '1');
    vi.stubEnv('NODE_ENV', 'development');
    expect(isPreviewMode()).toBe(true);
  });

  it('игнорируется в проде даже с флагом', () => {
    vi.stubEnv('SCC_PREVIEW', '1');
    vi.stubEnv('NODE_ENV', 'production');
    expect(isPreviewMode()).toBe(false);
  });

  it('любое значение кроме 1 не включает', () => {
    vi.stubEnv('SCC_PREVIEW', '0');
    vi.stubEnv('NODE_ENV', 'development');
    expect(isPreviewMode()).toBe(false);
  });
});
