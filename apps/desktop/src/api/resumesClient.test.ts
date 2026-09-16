import { afterEach, expect, it, vi } from 'vitest';

import { getResumes, importResume } from './resumesClient';

afterEach(() => vi.unstubAllGlobals());

it('loads resume metadata from the local core api', async () => {
  const payload = [
    {
      id: 'resume-1',
      sha256: 'a'.repeat(64),
      original_filename: '基础简历.pdf',
      file_ext: '.pdf',
      mime_type: 'application/pdf',
      size_bytes: 1024,
      version_number: 2,
      extraction_status: 'EXTRACTED',
      parser_name: 'pypdf',
      parser_version: '6.19.0',
      extraction_error: null,
      created_at: '2026-09-16T11:00:00',
      pending_draft_count: 2,
    },
  ];
  const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } })));
  vi.stubGlobal('fetch', fetchMock);

  const result = await getResumes();

  expect(result).toEqual(payload);
  expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8765/api/resumes');
});

it('uploads a selected resume with multipart form data', async () => {
  const responseBody = {
    id: 'resume-2',
    sha256: 'b'.repeat(64),
    original_filename: '设计简历.docx',
    file_ext: '.docx',
    mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    size_bytes: 2048,
    version_number: 3,
    extraction_status: 'EXTRACTED',
    parser_name: 'python-docx',
    parser_version: '1.2.0',
    extraction_error: null,
    created_at: '2026-09-16T11:10:00',
    pending_draft_count: 1,
    deduplicated: false,
  };
  const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify(responseBody), { status: 200, headers: { 'Content-Type': 'application/json' } })));
  vi.stubGlobal('fetch', fetchMock);
  const file = new File(['resume'], '设计简历.docx', { type: responseBody.mime_type });

  const result = await importResume(file);

  expect(result).toEqual(responseBody);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe('http://127.0.0.1:8765/api/resumes/import');
  expect(init.method).toBe('POST');
  expect(init.body).toBeInstanceOf(FormData);
  expect((init.body as FormData).get('file')).toBe(file);
});
