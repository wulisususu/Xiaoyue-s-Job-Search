import { CoreApiError } from './coreClient';

const CORE_API_BASE = 'http://127.0.0.1:8765';

export interface ResumeVersion {
  id: string;
  sha256: string;
  original_filename: string;
  file_ext: string;
  mime_type: string;
  size_bytes: number;
  version_number: number;
  extraction_status: string;
  parser_name: string | null;
  parser_version: string | null;
  extraction_error: string | null;
  created_at: string;
  pending_draft_count: number;
}

export interface ResumeImportResult extends ResumeVersion {
  deduplicated: boolean;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = init ? await fetch(url, init) : await fetch(url);
  if (!response.ok) {
    let message = `Core API returned HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the status-based fallback when the response is not JSON.
    }
    throw new CoreApiError(response.status, message);
  }
  return (await response.json()) as T;
}

export function getResumes(): Promise<ResumeVersion[]> {
  return requestJson<ResumeVersion[]>(`${CORE_API_BASE}/api/resumes`);
}

export function importResume(file: File): Promise<ResumeImportResult> {
  const body = new FormData();
  body.append('file', file);
  return requestJson<ResumeImportResult>(`${CORE_API_BASE}/api/resumes/import`, {
    method: 'POST',
    body,
  });
}
