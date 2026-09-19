import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { ResumesPage } from './ResumesPage';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it('shows immutable resume versions and imports a new PDF or DOCX', async () => {
  const initial = [
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
  const imported = {
    id: 'resume-2',
    sha256: 'b'.repeat(64),
    original_filename: '视觉设计简历.docx',
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

  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith('/api/resumes/import') && init?.method === 'POST') {
      return Promise.resolve(new Response(JSON.stringify(imported), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    return Promise.resolve(new Response(JSON.stringify(initial), { status: 200, headers: { 'Content-Type': 'application/json' } }));
  });
  vi.stubGlobal('fetch', fetchMock);

  render(<ResumesPage />);

  await waitFor(() => expect(screen.getByText('基础简历.pdf')).toBeInTheDocument());
  expect(screen.getByText('V2')).toBeInTheDocument();
  expect(screen.getByText('已提取')).toBeInTheDocument();
  expect(screen.getByText('2 项待审核')).toBeInTheDocument();
  expect(screen.queryByText(/vault_relpath/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/vault[\\/]resumes/i)).not.toBeInTheDocument();

  const input = screen.getByLabelText('导入简历') as HTMLInputElement;
  expect(input.accept).toContain('.pdf');
  expect(input.accept).toContain('.docx');
  const file = new File(['resume'], '视觉设计简历.docx', { type: imported.mime_type });
  fireEvent.change(input, { target: { files: [file] } });

  await waitFor(() => expect(screen.getByText('视觉设计简历.docx')).toBeInTheDocument());
  expect(screen.getByText('V3')).toBeInTheDocument();
  expect(screen.getByText('1 项待审核')).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith(
    'http://127.0.0.1:8765/api/resumes/import',
    expect.objectContaining({ method: 'POST', body: expect.any(FormData) }),
  );
});

it('explains when a scanned PDF needs OCR before profile extraction', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(new Response(JSON.stringify([
      {
        id: 'resume-scan',
        sha256: 'c'.repeat(64),
        original_filename: '扫描简历.pdf',
        file_ext: '.pdf',
        mime_type: 'application/pdf',
        size_bytes: 4096,
        version_number: 1,
        extraction_status: 'OCR_REQUIRED',
        parser_name: 'pypdf',
        parser_version: '6.19.0',
        extraction_error: null,
        created_at: '2026-09-16T11:20:00',
        pending_draft_count: 0,
      },
    ]), { status: 200, headers: { 'Content-Type': 'application/json' } }))),
  );

  render(<ResumesPage />);

  await waitFor(() => expect(screen.getByText('扫描简历.pdf')).toBeInTheDocument());
  expect(screen.getByText('需要 OCR')).toBeInTheDocument();
  expect(screen.getByText(/当前版本没有可用文本层/)).toBeInTheDocument();
});


it('can launch AI profile extraction from an extracted resume and refresh pending drafts', async () => {
  let listed = 0;
  const resume = {
    id: 'resume-ai',
    sha256: 'd'.repeat(64),
    original_filename: 'AI简历.pdf',
    file_ext: '.pdf',
    mime_type: 'application/pdf',
    size_bytes: 4096,
    version_number: 4,
    extraction_status: 'EXTRACTED',
    parser_name: 'pypdf',
    parser_version: '6.19.0',
    extraction_error: null,
    created_at: '2026-09-19T10:00:00',
    pending_draft_count: 0,
  };

  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith('/api/ai/extraction-runs') && init?.method === 'POST') {
      expect(JSON.parse(String(init.body))).toEqual({ resume_version_id: 'resume-ai' });
      return Promise.resolve(new Response(JSON.stringify({
        id: 9,
        resume_version_id: 'resume-ai',
        provider: 'openai_compatible',
        model: 'deepseek-flash',
        prompt_version: 'registry-prompt-v2',
        schema_version: 'bundle-v1',
        status: 'SUCCEEDED',
        input_hash: 'hash',
        error: null,
        created_at: '2026-09-19T10:01:00',
        completed_at: '2026-09-19T10:01:02',
        scalar_draft_count: 3,
        collection_draft_count: 2,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    listed += 1;
    return Promise.resolve(new Response(JSON.stringify([
      { ...resume, pending_draft_count: listed > 1 ? 5 : 0 },
    ]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
  });
  vi.stubGlobal('fetch', fetchMock);

  render(<ResumesPage />);
  await waitFor(() => expect(screen.getByText('AI简历.pdf')).toBeInTheDocument());

  fireEvent.click(screen.getByRole('button', { name: 'AI 解析资料' }));

  await waitFor(() => expect(screen.getByText(/已生成 5 项资料候选/)).toBeInTheDocument());
  expect(screen.getByText('5 项待审核')).toBeInTheDocument();
});
