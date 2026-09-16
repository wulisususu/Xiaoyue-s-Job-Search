import { afterEach, describe, expect, it, vi } from 'vitest';

import { CoreApiError, getCoreHealth } from './coreClient';

afterEach(() => vi.unstubAllGlobals());

describe('getCoreHealth', () => {
  it('returns typed health data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'ok', database: 'ok', version: '0.1.0' }), { status: 200, headers: { 'Content-Type': 'application/json' } })));
    await expect(getCoreHealth()).resolves.toEqual({ status: 'ok', database: 'ok', version: '0.1.0' });
  });

  it('throws CoreApiError for non-success responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 503 })));
    await expect(getCoreHealth()).rejects.toEqual(expect.objectContaining<Partial<CoreApiError>>({ status: 503 }));
  });
});
