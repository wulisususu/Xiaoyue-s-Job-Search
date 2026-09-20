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
    job_status: 'VERIFIED_OPEN',
    status: 'OPENED',
    allowed_next_statuses: ['IN_PROGRESS', 'SUBMITTED', 'ABANDONED'],
    channel: 'browser_agent',
    resume_version_id: null,
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
    mode: 'fill',
  };
  const plan = {
    token: 'plan-1',
    session_id: 'agent-1',
    page_url: application.opened_url,
    page_revision: 'revision-1',
    adapter_id: 'moka',
    adapter_display_name: 'Moka',
    adapter_implementation: 'moka_dom_v1',
    adapter_capabilities: ['dom_scan', 'post_fill_readback', 'moka_native_field_paths', 'indexed_repeatable_mapping', 'resume_upload'],
    adapter_limitations: ['additional_attachments', 'cascading_select', 'practice_experience_disambiguation', 'auto_submit'],
    items: [
      { field_id: 'f-name', label: '姓名', control_type: 'text', value: '赵新悦', source_path: 'identity.name', confidence: 0.99, reason: '姓名', requires_confirmation: false },
      { field_id: 'f-origin', label: '生源地', control_type: 'text', value: '安徽', source_path: 'location.hukou', confidence: 0.72, reason: '生源地≈户籍地', requires_confirmation: true },
    ],
    attachments: [{ field_id: 'resume-file', label: '上传简历', kind: 'resume', required: true }],
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
    if (url.endsWith('/api/resumes')) {
      return Promise.resolve(new Response(JSON.stringify([
        {
          id: 'resume-v2',
          sha256: 'a'.repeat(64),
          original_filename: '赵新悦-央企简历.pdf',
          file_ext: '.pdf',
          mime_type: 'application/pdf',
          size_bytes: 1024,
          version_number: 2,
          extraction_status: 'EXTRACTED',
          parser_name: 'pypdf',
          parser_version: '1',
          extraction_error: null,
          created_at: '2026-09-19T07:00:00',
          pending_draft_count: 0,
        },
      ]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/browser-agent/sessions/agent-1/plan')) {
      return Promise.resolve(new Response(JSON.stringify(plan), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/browser-agent/sessions/agent-1/semantic-plan')) {
      return Promise.resolve(new Response(JSON.stringify({
        ...plan,
        token: 'plan-ai',
        items: [
          ...plan.items,
          { field_id: 'f-contact', label: '紧急联系人', control_type: 'text', value: '未提供', source_path: 'identity.name', confidence: 0.55, reason: 'AI suggestion', requires_confirmation: true },
        ],
        unmatched: [],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/browser-agent/sessions/agent-1/resume-upload')) {
      return Promise.resolve(new Response(JSON.stringify({
        field_id: 'resume-file',
        resume_version_id: 'resume-v2',
        filename: '赵新悦-央企简历.pdf',
        status: 'VERIFIED',
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/browser-agent/sessions/agent-1/fill')) {
      return Promise.resolve(new Response(JSON.stringify({
        filled_count: 1,
        skipped_count: 0,
        verified_count: 1,
        failed_count: 0,
        uncertain_count: 0,
        status: 'VERIFIED',
        results: [
          {
            field_id: 'f-name',
            requested: '赵新悦',
            observed: '赵新悦',
            status: 'VERIFIED',
            reason: 'READBACK_MATCH',
          },
        ],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
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
  expect(screen.getByText('Moka', { selector: 'strong' })).toBeInTheDocument();
  expect(screen.getByText(/Moka 专项 DOM v1/)).toBeInTheDocument();
  expect(screen.getByText(/附件上传、级联选择、实习\/工作经历归类、自动提交/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'AI 补全未匹配' })).toBeInTheDocument();

  const resumeSelect = screen.getByRole('combobox', { name: '选择上传简历版本' }) as HTMLSelectElement;
  expect(resumeSelect.value).toBe('');
  expect(screen.getByRole('button', { name: '上传所选简历' })).toBeDisabled();
  fireEvent.change(resumeSelect, { target: { value: 'resume-v2' } });
  fireEvent.click(screen.getByRole('button', { name: '上传所选简历' }));

  await waitFor(() => {
    const upload = calls.find((call) => call.url.endsWith('/api/browser-agent/sessions/agent-1/resume-upload'));
    expect(upload).toBeDefined();
    expect(JSON.parse(String(upload!.init?.body))).toEqual({
      plan_token: 'plan-1',
      field_id: 'resume-file',
      resume_version_id: 'resume-v2',
    });
    expect(screen.getByText(/已回读：赵新悦-央企简历.pdf/)).toBeInTheDocument();
  });

  fireEvent.click(screen.getByRole('button', { name: 'AI 补全未匹配' }));
  await waitFor(() => expect(screen.getByText('identity.name', { selector: 'code' })).toBeInTheDocument());

  const aiCall = calls.find((call) => call.url.endsWith('/api/browser-agent/sessions/agent-1/semantic-plan'));
  expect(aiCall).toBeDefined();
  expect(JSON.parse(String(aiCall!.init?.body))).toEqual({ plan_token: 'plan-1' });

  const nameBox = screen.getByRole('checkbox', { name: /姓名/ }) as HTMLInputElement;
  const originBox = screen.getByRole('checkbox', { name: /生源地/ }) as HTMLInputElement;
  expect(nameBox.checked).toBe(true);
  expect(originBox.checked).toBe(false);

  fireEvent.click(screen.getByRole('button', { name: '填写已确认项' }));
  await waitFor(() => {
    const fill = calls.find((call) => call.url.endsWith('/api/browser-agent/sessions/agent-1/fill'));
    expect(fill).toBeDefined();
    expect(JSON.parse(String(fill!.init?.body))).toEqual({ plan_token: 'plan-ai', field_ids: ['f-name'] });
  });
});


it('loads CRM timeline lazily alongside Moka resume support', async () => {
  const application = {
    id: 7,
    job_id: 'job-7',
    job_title: '视觉设计',
    company_name: '中国联通',
    job_status: 'VERIFIED_OPEN',
    status: 'SUBMITTED',
    allowed_next_statuses: ['INTERVIEWING', 'OFFER', 'REJECTED', 'ABANDONED'],
    channel: 'manual',
    resume_version_id: 'resume-v3',
    opened_url: 'https://ats.example.com/apply/7',
    opened_at: '2026-09-20T08:00:00',
    updated_at: '2026-09-20T09:00:00',
  };
  const events = [
    {
      id: 1,
      application_id: 7,
      event_type: 'CREATED',
      from_status: null,
      to_status: 'OPENED',
      note: null,
      created_at: '2026-09-20T08:00:00',
    },
    {
      id: 2,
      application_id: 7,
      event_type: 'STATUS_CHANGED',
      from_status: 'OPENED',
      to_status: 'SUBMITTED',
      note: '官网确认提交成功',
      created_at: '2026-09-20T09:00:00',
    },
  ];

  const calls: string[] = [];
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    calls.push(url);
    if (url.endsWith('/api/applications')) {
      return Promise.resolve(new Response(JSON.stringify([application]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }));
    }
    if (url.endsWith('/api/browser-agent/sessions')) {
      return Promise.resolve(new Response(JSON.stringify([]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }));
    }
    if (url.endsWith('/api/resumes')) {
      return Promise.resolve(new Response(JSON.stringify([]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }));
    }
    if (url.endsWith('/api/applications/7/events')) {
      return Promise.resolve(new Response(JSON.stringify(events), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }));
    }
    return Promise.resolve(new Response('{}', {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
  }));

  render(<ApplicationsPage />);
  await waitFor(() => expect(screen.getByText('中国联通')).toBeInTheDocument());

  const statusSelect = screen.getByRole('combobox', { name: '投递状态' }) as HTMLSelectElement;
  expect(Array.from(statusSelect.options).map((option) => option.value)).toEqual([
    'SUBMITTED',
    'INTERVIEWING',
    'OFFER',
    'REJECTED',
    'ABANDONED',
  ]);
  expect(screen.getByText('resume-v3')).toBeInTheDocument();
  expect(calls.some((url) => url.endsWith('/api/applications/7/events'))).toBe(false);

  fireEvent.click(screen.getByRole('button', { name: '查看时间线' }));

  await waitFor(() => expect(screen.getByText('官网确认提交成功')).toBeInTheDocument());
  expect(screen.getByText('创建投递记录')).toBeInTheDocument();
  expect(screen.getByText('已打开入口 → 已投递')).toBeInTheDocument();
  expect(calls.filter((url) => url.endsWith('/api/applications/7/events'))).toHaveLength(1);
});
