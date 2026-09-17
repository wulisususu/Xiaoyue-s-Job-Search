import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { ProfilePage } from './ProfilePage';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete window.__XIAOYUE_CORE__;
});

it('reviews resume drafts explicitly and keeps confirmed profile as the SSOT', async () => {
  const definitions = [
    { field_key: 'identity.name', label: '姓名', category: '身份信息', value_type: 'string', multiple: false },
    { field_key: 'contact.email', label: '邮箱', category: '联系方式', value_type: 'string', multiple: false },
    { field_key: 'contact.phone', label: '手机号', category: '联系方式', value_type: 'string', multiple: false },
  ];
  const fields = [
    { field_key: 'identity.name', label: '姓名', category: '身份信息', value: '赵新悦', value_type: 'string', source_type: 'manual', source_ref: null, confidence: 1, confirmed: true, created_at: '2026-09-16T10:00:00', updated_at: '2026-09-16T10:00:00' },
  ];
  const drafts = [
    { id: 11, resume_version_id: 'resume-1', resume_version_number: 2, resume_filename: '基础简历.pdf', field_key: 'contact.email', label: '邮箱', category: '联系方式', value: 'name@example.com', value_type: 'string', confidence: 0.99, extractor_name: 'deterministic', status: 'PENDING', created_at: '2026-09-16T10:00:00', reviewed_at: null },
    { id: 12, resume_version_id: 'resume-1', resume_version_number: 2, resume_filename: '基础简历.pdf', field_key: 'contact.phone', label: '手机号', category: '联系方式', value: '13800138000', value_type: 'string', confidence: 0.98, extractor_name: 'deterministic', status: 'PENDING', created_at: '2026-09-16T10:00:00', reviewed_at: null },
  ];

  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith('/api/profile/collections/definitions')) {
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/collection-drafts?status=PENDING')) {
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/definitions')) {
      return Promise.resolve(new Response(JSON.stringify(definitions), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/fields') && !init) {
      return Promise.resolve(new Response(JSON.stringify(fields), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/drafts?status=PENDING')) {
      return Promise.resolve(new Response(JSON.stringify(drafts), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/drafts/11/accept')) {
      return Promise.resolve(new Response(JSON.stringify({ field_key: 'contact.email', label: '邮箱', category: '联系方式', value: 'name@example.com', value_type: 'string', source_type: 'resume', source_ref: 'resume-1', confidence: 0.99, confirmed: true, created_at: '2026-09-16T10:00:00', updated_at: '2026-09-16T10:10:00' }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/drafts/12/reject')) {
      return Promise.resolve(new Response(JSON.stringify({ ...drafts[1], status: 'REJECTED', reviewed_at: '2026-09-16T10:11:00' }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/fields/identity.name') && init?.method === 'PUT') {
      return Promise.resolve(new Response(JSON.stringify({ ...fields[0], value: '赵新悦（更新）', updated_at: '2026-09-16T10:12:00' }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    return Promise.resolve(new Response('{}', { status: 404, headers: { 'Content-Type': 'application/json' } }));
  });
  vi.stubGlobal('fetch', fetchMock);

  render(<ProfilePage />);

  await waitFor(() => expect(screen.getByDisplayValue('赵新悦')).toBeInTheDocument());
  expect(screen.getByText('待审核候选')).toBeInTheDocument();
  expect(screen.getByText('name@example.com')).toBeInTheDocument();
  expect(screen.getByText('13800138000')).toBeInTheDocument();
  expect(screen.getAllByText('基础简历.pdf · V2')).toHaveLength(2);

  fireEvent.click(screen.getByRole('button', { name: '接受 邮箱' }));
  await waitFor(() => expect(screen.queryByRole('button', { name: '接受 邮箱' })).not.toBeInTheDocument());
  expect(screen.getByDisplayValue('name@example.com')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: '拒绝 手机号' }));
  await waitFor(() => expect(screen.queryByRole('button', { name: '拒绝 手机号' })).not.toBeInTheDocument());
  expect(screen.queryByText('13800138000')).not.toBeInTheDocument();

  const nameRow = screen.getByTestId('profile-field-identity.name');
  const nameInput = within(nameRow).getByLabelText('姓名');
  fireEvent.change(nameInput, { target: { value: '赵新悦（更新）' } });
  fireEvent.click(within(nameRow).getByRole('button', { name: '保存 姓名' }));

  await waitFor(() => expect(screen.getByDisplayValue('赵新悦（更新）')).toBeInTheDocument());
  expect(fetchMock).toHaveBeenCalledWith(
    'http://127.0.0.1:8765/api/profile/fields/identity.name',
    expect.objectContaining({ method: 'PUT', body: JSON.stringify({ value: '赵新悦（更新）' }) }),
  );
});

it('renders every server-defined profile field even before it has a confirmed value', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/profile/collections/definitions')) {
        return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
      }
      if (url.endsWith('/api/profile/collection-drafts?status=PENDING')) {
        return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
      }
      if (url.endsWith('/api/profile/definitions')) {
        return Promise.resolve(new Response(JSON.stringify([
          { field_key: 'education.school', label: '学校', category: '教育经历', value_type: 'string', multiple: false },
          { field_key: 'job.target_roles', label: '目标岗位', category: '求职偏好', value_type: 'string_list', multiple: true },
        ]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
      }
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }),
  );

  render(<ProfilePage />);

  await waitFor(() => expect(screen.getByLabelText('学校')).toBeInTheDocument());
  expect(screen.getByLabelText('目标岗位')).toBeInTheDocument();
  expect(screen.getByText('尚未确认')).toBeInTheDocument();
});

it('edits repeatable education records independently and preserves server order', async () => {
  const collectionDefinitions = [
    {
      kind: 'education',
      label: '教育经历',
      fields: [
        { key: 'school', label: '学校', value_type: 'string', required: true, multiple: false },
        { key: 'degree', label: '学历/学位', value_type: 'string', required: false, multiple: false },
      ],
    },
  ];
  const first = {
    id: 1,
    kind: 'education',
    position: 0,
    payload: { school: '三江学院', degree: '本科' },
    source_type: 'manual',
    source_ref: null,
    confidence: 1,
    confirmed: true,
    created_at: '2026-09-17T10:00:00',
    updated_at: '2026-09-17T10:00:00',
  };
  const second = {
    id: 2,
    kind: 'education',
    position: 1,
    payload: { school: '第二学校' },
    source_type: 'manual',
    source_ref: null,
    confidence: 1,
    confirmed: true,
    created_at: '2026-09-17T10:01:00',
    updated_at: '2026-09-17T10:01:00',
  };
  const updatedFirst = { ...first, payload: { school: '三江学院（更新）', degree: '本科' }, updated_at: '2026-09-17T10:10:00' };
  const third = {
    id: 3,
    kind: 'education',
    position: 1,
    payload: { school: '新学校' },
    source_type: 'manual',
    source_ref: null,
    confidence: 1,
    confirmed: true,
    created_at: '2026-09-17T10:11:00',
    updated_at: '2026-09-17T10:11:00',
  };

  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    if (url.endsWith('/api/profile/collections/definitions')) {
      return Promise.resolve(new Response(JSON.stringify(collectionDefinitions), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/collection-drafts?status=PENDING')) {
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/collections/education/order') && method === 'PUT') {
      return Promise.resolve(new Response(JSON.stringify([
        { ...third, position: 0 },
        { ...updatedFirst, position: 1 },
      ]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/collections/education/1') && method === 'PUT') {
      return Promise.resolve(new Response(JSON.stringify(updatedFirst), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/collections/education/2') && method === 'DELETE') {
      return Promise.resolve(new Response(JSON.stringify({ deleted_id: 2 }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/collections/education') && method === 'POST') {
      return Promise.resolve(new Response(JSON.stringify(third), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/collections/education')) {
      return Promise.resolve(new Response(JSON.stringify([first, second]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/definitions') || url.endsWith('/api/profile/fields') || url.endsWith('/api/profile/drafts?status=PENDING')) {
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    return Promise.resolve(new Response('{}', { status: 404, headers: { 'Content-Type': 'application/json' } }));
  });
  vi.stubGlobal('fetch', fetchMock);

  render(<ProfilePage />);

  await waitFor(() => expect(screen.getByDisplayValue('三江学院')).toBeInTheDocument());
  expect(screen.getByDisplayValue('第二学校')).toBeInTheDocument();

  const firstCard = screen.getByTestId('profile-collection-education-1');
  fireEvent.change(within(firstCard).getByLabelText('教育经历 1 学校'), { target: { value: '三江学院（更新）' } });
  fireEvent.click(within(firstCard).getByRole('button', { name: '保存 教育经历 1' }));
  await waitFor(() => expect(screen.getByDisplayValue('三江学院（更新）')).toBeInTheDocument());

  const secondCard = screen.getByTestId('profile-collection-education-2');
  fireEvent.click(within(secondCard).getByRole('button', { name: '删除 教育经历 2' }));
  await waitFor(() => expect(screen.queryByTestId('profile-collection-education-2')).not.toBeInTheDocument());

  fireEvent.click(screen.getByRole('button', { name: '新增教育经历' }));
  fireEvent.change(screen.getByLabelText('新增教育经历 学校'), { target: { value: '新学校' } });
  fireEvent.click(screen.getByRole('button', { name: '保存新增教育经历' }));
  await waitFor(() => expect(screen.getByTestId('profile-collection-education-3')).toBeInTheDocument());

  const newCard = screen.getByTestId('profile-collection-education-3');
  fireEvent.click(within(newCard).getByRole('button', { name: '上移 教育经历 2' }));

  await waitFor(() => {
    const section = screen.getByTestId('profile-collection-education');
    const cards = within(section).getAllByTestId(/profile-collection-education-\d+/);
    expect(within(cards[0]).getByDisplayValue('新学校')).toBeInTheDocument();
    expect(within(cards[1]).getByDisplayValue('三江学院（更新）')).toBeInTheDocument();
  });
  expect(fetchMock).toHaveBeenCalledWith(
    'http://127.0.0.1:8765/api/profile/collections/education/order',
    expect.objectContaining({ method: 'PUT', body: JSON.stringify({ item_ids: [3, 1] }) }),
  );
});

it('reviews structured collection drafts and only exposes accepted records to the SSOT editor', async () => {
  const collectionDefinitions = [
    {
      kind: 'education',
      label: '教育经历',
      fields: [
        { key: 'school', label: '学校', value_type: 'string', required: true, multiple: false },
        { key: 'major', label: '专业', value_type: 'string', required: false, multiple: false },
      ],
    },
  ];
  const firstDraft = {
    id: 21,
    resume_version_id: 'resume-1',
    resume_version_number: 2,
    resume_filename: '基础简历.pdf',
    kind: 'education',
    label: '教育经历',
    payload: { school: '三江学院', major: '视觉传达设计' },
    confidence: 0.96,
    extractor_name: 'openai-compatible-v1',
    status: 'PENDING',
    created_at: '2026-09-17T10:00:00',
    reviewed_at: null,
  };
  const secondDraft = {
    ...firstDraft,
    id: 22,
    payload: { school: '第二候选学校' },
    confidence: 0.82,
  };
  const acceptedItem = {
    id: 7,
    kind: 'education',
    position: 0,
    payload: firstDraft.payload,
    source_type: 'resume',
    source_ref: 'resume-1',
    confidence: 0.96,
    confirmed: true,
    created_at: '2026-09-17T10:01:00',
    updated_at: '2026-09-17T10:01:00',
  };
  let accepted = false;

  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith('/api/profile/collections/definitions')) {
      return Promise.resolve(new Response(JSON.stringify(collectionDefinitions), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/collection-drafts?status=PENDING')) {
      return Promise.resolve(new Response(JSON.stringify([firstDraft, secondDraft]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/collection-drafts/21/accept')) {
      accepted = true;
      return Promise.resolve(new Response(JSON.stringify(acceptedItem), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/collection-drafts/22/reject')) {
      return Promise.resolve(new Response(JSON.stringify({ ...secondDraft, status: 'REJECTED', reviewed_at: '2026-09-17T10:02:00' }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/collections/education')) {
      return Promise.resolve(new Response(JSON.stringify(accepted ? [acceptedItem] : []), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/definitions') || url.endsWith('/api/profile/fields') || url.endsWith('/api/profile/drafts?status=PENDING')) {
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    return Promise.resolve(new Response('{}', { status: 404, headers: { 'Content-Type': 'application/json' } }));
  });
  vi.stubGlobal('fetch', fetchMock);

  render(<ProfilePage />);

  await waitFor(() => expect(screen.getByRole('button', { name: '接受 教育经历候选 1' })).toBeInTheDocument());
  expect(screen.getByText('三江学院')).toBeInTheDocument();
  expect(screen.getByText('视觉传达设计')).toBeInTheDocument();
  expect(screen.getByText('第二候选学校')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: '接受 教育经历候选 1' }));
  await waitFor(() => expect(screen.queryByRole('button', { name: '接受 教育经历候选 1' })).not.toBeInTheDocument());
  await waitFor(() => expect(screen.getByDisplayValue('三江学院')).toBeInTheDocument());

  fireEvent.click(screen.getByRole('button', { name: '拒绝 教育经历候选 2' }));
  await waitFor(() => expect(screen.queryByRole('button', { name: '拒绝 教育经历候选 2' })).not.toBeInTheDocument());
  expect(screen.queryByText('第二候选学校')).not.toBeInTheDocument();
});
