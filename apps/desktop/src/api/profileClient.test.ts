import { afterEach, expect, it, vi } from 'vitest';

import {
  acceptProfileCollectionDraft,
  acceptProfileDraft,
  createProfileCollectionItem,
  deleteProfileCollectionItem,
  getPendingProfileCollectionDrafts,
  getPendingProfileDrafts,
  getProfileCollection,
  getProfileCollectionDefinitions,
  getProfileDefinitions,
  getProfileFields,
  rejectProfileCollectionDraft,
  rejectProfileDraft,
  reorderProfileCollectionItems,
  saveProfileField,
  updateProfileCollectionItem,
} from './profileClient';

afterEach(() => {
  vi.unstubAllGlobals();
  delete window.__XIAOYUE_CORE__;
});

it('loads the server-owned field registry, confirmed fields and pending drafts', async () => {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith('/api/profile/definitions')) {
      return Promise.resolve(new Response(JSON.stringify([{ field_key: 'identity.name', label: '姓名', category: '身份信息', value_type: 'string', multiple: false }]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/fields')) {
      return Promise.resolve(new Response(JSON.stringify([{ field_key: 'identity.name', label: '姓名', category: '身份信息', value: '赵新悦', value_type: 'string', source_type: 'manual', source_ref: null, confidence: 1, confirmed: true, created_at: '2026-09-16T10:00:00', updated_at: '2026-09-16T10:00:00' }]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    return Promise.resolve(new Response(JSON.stringify([{ id: 11, resume_version_id: 'resume-1', resume_version_number: 2, resume_filename: '基础简历.pdf', field_key: 'contact.email', label: '邮箱', category: '联系方式', value: 'name@example.com', value_type: 'string', confidence: 0.99, extractor_name: 'deterministic', status: 'PENDING', created_at: '2026-09-16T10:00:00', reviewed_at: null }]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
  });
  vi.stubGlobal('fetch', fetchMock);

  const [definitions, fields, drafts] = await Promise.all([
    getProfileDefinitions(),
    getProfileFields(),
    getPendingProfileDrafts(),
  ]);

  expect(definitions[0].field_key).toBe('identity.name');
  expect(fields[0].value).toBe('赵新悦');
  expect(drafts[0].resume_version_number).toBe(2);
  expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8765/api/profile/drafts?status=PENDING');
});

it('accepts, rejects and manually saves profile data through explicit review actions', async () => {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith('/accept')) {
      return Promise.resolve(new Response(JSON.stringify({ field_key: 'contact.email', label: '邮箱', category: '联系方式', value: 'name@example.com', value_type: 'string', source_type: 'resume', source_ref: 'resume-1', confidence: 0.99, confirmed: true, created_at: '2026-09-16T10:00:00', updated_at: '2026-09-16T10:00:00' }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/reject')) {
      return Promise.resolve(new Response(JSON.stringify({ id: 12, resume_version_id: 'resume-1', resume_version_number: 2, resume_filename: '基础简历.pdf', field_key: 'contact.phone', label: '手机号', category: '联系方式', value: '13800138000', value_type: 'string', confidence: 0.99, extractor_name: 'deterministic', status: 'REJECTED', created_at: '2026-09-16T10:00:00', reviewed_at: '2026-09-16T10:10:00' }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    return Promise.resolve(new Response(JSON.stringify({ field_key: 'identity.name', label: '姓名', category: '身份信息', value: '赵新悦（更新）', value_type: 'string', source_type: 'manual', source_ref: null, confidence: 1, confirmed: true, created_at: '2026-09-16T10:00:00', updated_at: '2026-09-16T10:20:00' }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
  });
  vi.stubGlobal('fetch', fetchMock);

  await acceptProfileDraft(11);
  await rejectProfileDraft(12);
  await saveProfileField('identity.name', '赵新悦（更新）');

  expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8765/api/profile/drafts/11/accept', { method: 'POST' });
  expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8765/api/profile/drafts/12/reject', { method: 'POST' });
  expect(fetchMock).toHaveBeenCalledWith(
    'http://127.0.0.1:8765/api/profile/fields/identity.name',
    expect.objectContaining({ method: 'PUT', body: JSON.stringify({ value: '赵新悦（更新）' }) }),
  );
});

it('uses the sidecar runtime and session token for structured collection CRUD', async () => {
  window.__XIAOYUE_CORE__ = { baseUrl: 'http://127.0.0.1:9988', sessionToken: 'session-secret' };
  const item = {
    id: 7,
    kind: 'education',
    position: 0,
    payload: { school: '三江学院' },
    source_type: 'manual',
    source_ref: null,
    confidence: 1,
    confirmed: true,
    created_at: '2026-09-17T10:00:00',
    updated_at: '2026-09-17T10:00:00',
  };
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    if (url.endsWith('/api/profile/collections/definitions')) {
      return Promise.resolve(new Response(JSON.stringify([{ kind: 'education', label: '教育经历', fields: [] }]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/collections/education/order')) {
      return Promise.resolve(new Response(JSON.stringify([item]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/collections/education/7') && method === 'DELETE') {
      return Promise.resolve(new Response(JSON.stringify({ deleted_id: 7 }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/collections/education/7')) {
      return Promise.resolve(new Response(JSON.stringify(item), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/collections/education') && method === 'GET') {
      return Promise.resolve(new Response(JSON.stringify([item]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/collections/education')) {
      return Promise.resolve(new Response(JSON.stringify(item), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    return Promise.resolve(new Response('{}', { status: 404, headers: { 'Content-Type': 'application/json' } }));
  });
  vi.stubGlobal('fetch', fetchMock);

  await getProfileCollectionDefinitions();
  await getProfileCollection('education');
  await createProfileCollectionItem('education', { school: '三江学院' });
  await updateProfileCollectionItem('education', 7, { school: '三江学院' });
  await reorderProfileCollectionItems('education', [7]);
  await deleteProfileCollectionItem('education', 7);

  const calls = fetchMock.mock.calls.filter(([input]) => String(input).includes('/api/profile/collections/'));
  expect(calls).toHaveLength(6);
  for (const [, init] of calls) {
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer session-secret');
  }
  expect(fetchMock).toHaveBeenCalledWith(
    'http://127.0.0.1:9988/api/profile/collections/education',
    expect.objectContaining({ method: 'POST', body: JSON.stringify({ payload: { school: '三江学院' } }) }),
  );
  expect(fetchMock).toHaveBeenCalledWith(
    'http://127.0.0.1:9988/api/profile/collections/education/order',
    expect.objectContaining({ method: 'PUT', body: JSON.stringify({ item_ids: [7] }) }),
  );
});

it('reviews structured collection drafts through the sidecar-authenticated Profile API', async () => {
  window.__XIAOYUE_CORE__ = { baseUrl: 'http://127.0.0.1:9988', sessionToken: 'session-secret' };
  const draft = {
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
  const item = {
    id: 7,
    kind: 'education',
    position: 0,
    payload: draft.payload,
    source_type: 'resume',
    source_ref: 'resume-1',
    confidence: 0.96,
    confirmed: true,
    created_at: '2026-09-17T10:01:00',
    updated_at: '2026-09-17T10:01:00',
  };
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith('/api/profile/collection-drafts?status=PENDING')) {
      return Promise.resolve(new Response(JSON.stringify([draft]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/collection-drafts/21/accept')) {
      return Promise.resolve(new Response(JSON.stringify(item), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/profile/collection-drafts/21/reject')) {
      return Promise.resolve(new Response(JSON.stringify({ ...draft, status: 'REJECTED', reviewed_at: '2026-09-17T10:02:00' }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    return Promise.resolve(new Response('{}', { status: 404, headers: { 'Content-Type': 'application/json' } }));
  });
  vi.stubGlobal('fetch', fetchMock);

  const drafts = await getPendingProfileCollectionDrafts();
  const accepted = await acceptProfileCollectionDraft(21);
  const rejected = await rejectProfileCollectionDraft(21);

  expect(drafts[0].payload.school).toBe('三江学院');
  expect(accepted.source_type).toBe('resume');
  expect(rejected.status).toBe('REJECTED');

  const reviewCalls = fetchMock.mock.calls.filter(([input]) => String(input).includes('/api/profile/collection-drafts'));
  expect(reviewCalls).toHaveLength(3);
  for (const [, init] of reviewCalls) {
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer session-secret');
  }
  expect(fetchMock).toHaveBeenCalledWith(
    'http://127.0.0.1:9988/api/profile/collection-drafts/21/accept',
    expect.objectContaining({ method: 'POST' }),
  );
  expect(fetchMock).toHaveBeenCalledWith(
    'http://127.0.0.1:9988/api/profile/collection-drafts/21/reject',
    expect.objectContaining({ method: 'POST' }),
  );
});
