import { afterEach, describe, expect, it, vi } from 'vitest';

import { getJobStats, getJobs, getSourceStatus, runDueVerification, syncTencentSource, verifyJob } from './jobsClient';

afterEach(() => vi.unstubAllGlobals());

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

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8765/api/jobs?ownership=central_soe&q=%E8%A7%86%E8%A7%89%E8%AE%BE%E8%AE%A1&location=%E5%8D%97%E4%BA%AC',
    );
  });

  it('loads source health and posts sync / verification actions', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await getSourceStatus();
    await syncTencentSource();
    await verifyJob('job-1');
    await runDueVerification(20);

    expect(fetchMock).toHaveBeenNthCalledWith(1, 'http://127.0.0.1:8765/api/sources/status');
    expect(fetchMock).toHaveBeenNthCalledWith(2, 'http://127.0.0.1:8765/api/sources/tencent/sync', { method: 'POST' });
    expect(fetchMock).toHaveBeenNthCalledWith(3, 'http://127.0.0.1:8765/api/verification/jobs/job-1', { method: 'POST' });
    expect(fetchMock).toHaveBeenNthCalledWith(4, 'http://127.0.0.1:8765/api/verification/run-due?limit=20', { method: 'POST' });
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
});
