import { afterEach, describe, expect, it, vi } from 'vitest';

import { coreRuntime, authHeaders } from './coreClient';
import { getJobStats, getJobs, getSourceStatus, runDueVerification, syncDueSources, syncTencentSource, verifyJob } from './jobsClient';

afterEach(() => vi.unstubAllGlobals());

function calledUrls(fetchMock: ReturnType<typeof vi.fn>): string[] {
  return fetchMock.mock.calls.map((call) => String(call[0]));
}

describe('jobsClient', () => {
  it('serializes active filters and returns typed job data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], total: 0, limit: 50, offset: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await getJobs({ ownership: 'central_soe', q: '视觉设计', location: '南京' });

    expect(calledUrls(fetchMock)).toEqual([
      `${coreRuntime().baseUrl}/api/jobs?ownership=central_soe&q=%E8%A7%86%E8%A7%89%E8%AE%BE%E8%AE%A1&location=%E5%8D%97%E4%BA%AC`,
    ]);
    // Dev mode (no session token): requests must not carry an auth header.
    expect(calledUrls(fetchMock).length).toBeGreaterThan(0);
  });

  it('passes server-side pagination params to the jobs endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], total: 0, limit: 50, offset: 50 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await getJobs({ limit: 50, offset: 50 });

    expect(calledUrls(fetchMock)).toEqual([`${coreRuntime().baseUrl}/api/jobs?limit=50&offset=50`]);
  });

  it('loads source health and posts sync / verification actions', async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } })),
    );
    vi.stubGlobal('fetch', fetchMock);

    await getSourceStatus();
    await syncTencentSource();
    await syncDueSources();
    await verifyJob('job-1');
    await runDueVerification(20);

    const urls = calledUrls(fetchMock);
    expect(urls[0]).toBe(`${coreRuntime().baseUrl}/api/sources/status`);
    expect(urls[1]).toBe(`${coreRuntime().baseUrl}/api/sources/tencent/sync`);
    expect(urls[2]).toBe(`${coreRuntime().baseUrl}/api/sources/sync-due`);
    expect(urls[3]).toBe(`${coreRuntime().baseUrl}/api/verification/jobs/job-1`);
    expect(urls[4]).toBe(`${coreRuntime().baseUrl}/api/verification/run-due?limit=20`);
  });

  it('injects the session token header when the shell provides one', async () => {
    (window as unknown as Record<string, unknown>).__XIAOYUE_CORE__ = {
      baseUrl: 'http://127.0.0.1:54321',
      sessionToken: 'launch-secret',
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], total: 0, limit: 50, offset: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await getJobs();

    expect(calledUrls(fetchMock)).toEqual(['http://127.0.0.1:54321/api/jobs']);
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(headers.get('Authorization')).toBe('Bearer launch-secret');
    delete (window as unknown as Record<string, unknown>).__XIAOYUE_CORE__;
  });

  it('loads job radar statistics', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ total: 12, with_url_unverified: 7, without_url: 5, central_soe: 3, local_soe: 2, unknown: 7 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    );
    await expect(getJobStats()).resolves.toMatchObject({ total: 12, central_soe: 3 });
  });

  it('authHeaders is empty without a shell session token', () => {
    expect(Object.keys(authHeaders())).toHaveLength(0);
  });
});
