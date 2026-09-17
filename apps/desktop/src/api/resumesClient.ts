import { CoreApiError, authHeaders, coreRuntime } from './coreClient';

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
  const headers = new Headers(init?.headers);
  for (const [key, value] of Object.entries(authHeaders())) {
    headers.set(key, value);
  }
  const response = init ? await fetch(url, { ...init, headers }) : await fetch(url, { headers });
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

/** All core clients must resolve the endpoint through coreRuntime() so the
 *  packaged app targets the sidecar's dynamic port, and must merge
 *  authHeaders() so the session token guard lets them through. */
export function getResumes(): Promise<ResumeVersion[]> {
  return requestJson<ResumeVersion[]>(`${coreRuntime().baseUrl}/api/resumes`);
}

export function importResume(file: File): Promise<ResumeImportResult> {
  const body = new FormData();
  body.append('file', file);
  return requestJson<ResumeImportResult>(`${coreRuntime().baseUrl}/api/resumes/import`, {
    method: 'POST',
    body,
  });
}
