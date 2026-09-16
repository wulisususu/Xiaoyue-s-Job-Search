import { afterEach, expect, it, vi } from 'vitest';

import {
  acceptProfileDraft,
  getPendingProfileDrafts,
  getProfileDefinitions,
  getProfileFields,
  rejectProfileDraft,
  saveProfileField,
} from './profileClient';

afterEach(() => vi.unstubAllGlobals());

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
