import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { DashboardPage } from './DashboardPage';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it('renders live job and application metrics from the core summary endpoint', async () => {
  const summary = {
    total_jobs: 128,
    new_jobs_today: 9,
    verified_open: 41,
    central_soe_jobs: 77,
    applications_total: 12,
    in_progress: 3,
    submitted: 5,
    interviewing: 2,
    offers: 1,
  };

  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith('/api/health')) {
      return Promise.resolve(new Response(JSON.stringify({
        status: 'ok',
        database: 'ok',
        version: '0.1.0',
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/dashboard/summary')) {
      return Promise.resolve(new Response(JSON.stringify(summary), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }));
    }
    return Promise.resolve(new Response('{}', {
      status: 404,
      headers: { 'Content-Type': 'application/json' },
    }));
  }));

  render(<DashboardPage />);

  await waitFor(() => expect(screen.getByText('128')).toBeInTheDocument());
  for (const [label, value] of [
    ['今日新增岗位', '9'],
    ['可申请岗位', '41'],
    ['央企岗位', '77'],
    ['岗位总数', '128'],
    ['填写中', '3'],
    ['已投递', '5'],
    ['面试中', '2'],
    ['Offer', '1'],
  ]) {
    const card = screen.getByText(label).closest('article');
    expect(card).not.toBeNull();
    expect(card).toHaveTextContent(value);
  }

  expect(screen.getByText('本地核心：已连接')).toBeInTheDocument();
  expect(screen.getByText(/当前共有 12 条投递记录/)).toBeInTheDocument();
  expect(screen.queryByText(/后续里程碑会接入 WorkFind/)).not.toBeInTheDocument();
});

it('shows a useful first-run state when no jobs exist', async () => {
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith('/api/health')) {
      return Promise.resolve(new Response(JSON.stringify({
        status: 'ok',
        database: 'ok',
        version: '0.1.0',
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    return Promise.resolve(new Response(JSON.stringify({
      total_jobs: 0,
      new_jobs_today: 0,
      verified_open: 0,
      central_soe_jobs: 0,
      applications_total: 0,
      in_progress: 0,
      submitted: 0,
      interviewing: 0,
      offers: 0,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
  }));

  render(<DashboardPage />);
  await waitFor(() => expect(screen.getByText('先同步岗位数据源')).toBeInTheDocument());
  expect(screen.getByText(/腾讯文档与 WorkFind/)).toBeInTheDocument();
});
