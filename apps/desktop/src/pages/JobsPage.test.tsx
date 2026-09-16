import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { JobsPage } from './JobsPage';

afterEach(() => vi.unstubAllGlobals());

it('renders imported jobs and keeps unverified applications gated', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/sources/status')) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              { source_name: 'tencent-sheet', last_run_status: 'SUCCESS', last_run_at: '2026-09-16T09:00:00Z', last_good_version: '2026-09-16', last_good_hash: 'abc', last_error: null },
              { source_name: 'workfind-online', last_run_status: 'FAILED', last_run_at: '2026-09-16T08:00:00Z', last_good_version: null, last_good_hash: 'def', last_error: 'temporary outage' },
            ]),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      if (url.endsWith('/api/jobs/stats')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ total: 1, with_url_unverified: 1, without_url: 0, verified_open: 0, rediscovery_required: 0, central_soe: 1, local_soe: 0, unknown: 0 }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({
            items: [
              {
                id: 'job-1',
                company: { id: 1, name: '中国移动通信集团有限公司', ownership: 'central_soe', province: '北京', level: 'central' },
                title: '视觉设计、宣传策划', location: '南京', industry: '通信', recruitment_batch: '27届秋招',
                deadline_text: '招满即止', apply_url: 'https://example.com/apply', canonical_url: 'https://example.com/apply', status: 'DISCOVERED_URL_UNVERIFIED',
                verification_health: 'REDIRECTED', ats: 'moka', last_verified_at: '2026-09-16T09:05:00Z', source_updated_at: '2026-09-03', sources: ['xiaozhao-radar'],
              },
            ],
            total: 1, limit: 50, offset: 0,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      );
    }),
  );

  render(<JobsPage />);

  await waitFor(() => expect(screen.getByText('中国移动通信集团有限公司')).toBeInTheDocument());
  expect(screen.getByText('视觉设计、宣传策划')).toBeInTheDocument();
  expect(screen.getByText('入口待验证')).toBeInTheDocument();
  expect(screen.getByText('腾讯文档')).toBeInTheDocument();
  expect(screen.getByText('WorkFind')).toBeInTheDocument();
  expect(screen.getByText('Moka')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '验证入口' })).toBeEnabled();
  expect(screen.getByRole('button', { name: '开始申请' })).toBeDisabled();
  expect(screen.getByRole('link', { name: '查看原始入口' })).toHaveAttribute('href', 'https://example.com/apply');
});
