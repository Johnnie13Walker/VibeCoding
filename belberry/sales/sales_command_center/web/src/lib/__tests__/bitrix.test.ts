import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { assertLarisaToken, findActiveUserByEmail, sendCodeMessage } from '../bitrix';

const state = {
  auth: {
    client_endpoint: 'https://belberrycrm.bitrix24.ru/rest/',
    access_token: 'secret-token',
  },
};

describe('bitrix client', () => {
  let statePath: string;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'scc-bitrix-'));
    statePath = path.join(dir, 'install.latest.json');
    await fs.writeFile(statePath, JSON.stringify(state), 'utf8');
    process.env.BITRIX_STATE_PATH = statePath;
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    delete process.env.BITRIX_STATE_PATH;
  });

  it('returns first active user by email', async () => {
    fetchMock.mockResolvedValueOnce(
      Response.json({ result: [{ ID: '42', EMAIL: 'm@example.com', NAME: 'Mila' }] }),
    );

    await expect(findActiveUserByEmail('m@example.com')).resolves.toEqual({
      bitrixId: 42,
      email: 'm@example.com',
      name: 'Mila',
    });

    expect(String(fetchMock.mock.calls[0][1].body)).toContain('filter%5BACTIVE%5D=Y');
  });

  it('returns null when active user is not found', async () => {
    fetchMock
      .mockResolvedValueOnce(Response.json({ result: [] }))
      .mockResolvedValueOnce(Response.json({ result: [] }));

    await expect(findActiveUserByEmail('missing@example.com')).resolves.toBeNull();
  });

  it('posts code notification through im.notify.personal.add', async () => {
    fetchMock.mockResolvedValueOnce(Response.json({ result: true }));

    await sendCodeMessage(77, '123456');

    const url = String(fetchMock.mock.calls[0][0]);
    const body = String(fetchMock.mock.calls[0][1].body);

    expect(url).toContain('/im.notify.personal.add.json');
    expect(body).toContain('USER_ID=77');
    expect(body).toContain('123456');
  });

  it('warns when token owner is not Larisa', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    fetchMock.mockResolvedValueOnce(Response.json({ result: { ID: 99 } }));

    await expect(assertLarisaToken()).resolves.toBe(false);
    expect(warn).toHaveBeenCalledOnce();
  });

  it('accepts Larisa token owner', async () => {
    fetchMock.mockResolvedValueOnce(Response.json({ result: { ID: 2812 } }));

    await expect(assertLarisaToken()).resolves.toBe(true);
  });
});
