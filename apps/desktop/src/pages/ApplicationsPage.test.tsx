import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { ApplicationsPage } from './ApplicationsPage';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it('reviews a Browser Agent fill plan before sending approved field ids', async () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const application = {
    id: 1,
    job_id: 'job-1',
    job_title: '视觉设计',
    company_name: '中国移动',
    status: 'OPENED',
    channel: 'browser_agent',
    opened_url: 'https://ats.example.com/apply',
    opened_at: '2026-09-19T08:00:00',
    updated_at: '2026-09-19T08:00:00',
  };
  const session = {
    id: 'agent-1',
    application_id: 1,
    url: application.opened_url,
    status: 'READY',
    browser: 'Microsoft Edge',
  };
  const plan = {
    token: 'plan-1',
    session_id: 'agent-1',
    page_url: application.opened_url,
    items: [
      { field_id: 'f-name', label: '姓名', control_type: 'text', value: '赵新悦', source_path: 'identity.name', confidence: 0.99, reason: '姓名', requires_confirmation: false },
      { field_id: 'f-origin', label: '生源地', control_type: 'text', value: '安徽', source_path: 'location.hukou', confidence: 0.72, reason: '生源地≈户籍地', requires_confirmation: true },
    ],
    unmatched: [{ field_id: 'f-contact', label: '紧急联系人', control_type: 'text' }],
    blocked: [],
  };

  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.endsWith('/api/applications')) {
      return Promise.resolve(new Response(JSON.stringify([application]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/browser-agent/sessions')) {
      return Promise.resolve(new Response(JSON.stringify([session]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/browser-agent/sessions/agent-1/plan')) {
      return Promise.resolve(new Response(JSON.stringify(plan), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/browser-agent/sessions/agent-1/fill')) {
      return Promise.resolve(new Response(JSON.stringify({ filled_count: 1, skipped_count: 0, status: 'FILLED' }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    return Promise.resolve(new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }));
  }));

  render(<ApplicationsPage />);

  await waitFor(() => expect(screen.getByText('中国移动')).toBeInTheDocument());
  expect(screen.getByText('智能填写')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: '扫描表单' }));
  await waitFor(() => expect(screen.getByText('identity.name')).toBeInTheDocument());
  expect(screen.getByText('location.hukou')).toBeInTheDocument();
  expect(screen.getByText(/紧急联系人/)).toBeInTheDocument();
  expect(screen.getByText(/不会点击提交按钮/)).toBeInTheDocument();

  const nameBox = screen.getByRole('checkbox', { name: /姓名/ }) as HTMLInputElement;
  const originBox = screen.getByRole('checkbox', { name: /生源地/ }) as HTMLInputElement;
  expect(nameBox.checked).toBe(true);
  expect(originBox.checked).toBe(false);

  fireEvent.click(screen.getByRole('button', { name: '填写已确认项' }));
  await waitFor(() => {
    const fill = calls.find((call) => call.url.endsWith('/api/browser-agent/sessions/agent-1/fill'));
    expect(fill).toBeDefined();
    expect(JSON.parse(String(fill!.init?.body))).toEqual({ plan_token: 'plan-1', field_ids: ['f-name'] });
  });
});
