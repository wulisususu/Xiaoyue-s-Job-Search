import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { JobsPage } from './JobsPage';

afterEach(() => vi.unstubAllGlobals());

it('renders imported jobs and keeps unverified applications gated', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/jobs/stats')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ total: 1, with_url_unverified: 1, without_url: 0, central_soe: 1, local_soe: 0, unknown: 0 }),
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
                deadline_text: '招满即止', apply_url: 'https://example.com/apply', status: 'DISCOVERED_URL_UNVERIFIED',
                source_updated_at: '2026-09-03', sources: ['xiaozhao-radar'],
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
  expect(screen.getByRole('button', { name: '开始申请' })).toBeDisabled();
  expect(screen.getByRole('link', { name: '查看原始入口' })).toHaveAttribute('href', 'https://example.com/apply');
});
