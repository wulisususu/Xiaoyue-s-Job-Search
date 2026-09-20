import { CoreApiError, authHeaders, coreRuntime } from './coreClient';

export interface ApplicationRecord {
  id: number;
  job_id: string;
  job_title: string;
  company_name: string;
  status: string;
  allowed_next_statuses: string[];
  channel: string;
  resume_version_id: string | null;
  opened_url: string;
  opened_at: string;
  updated_at: string;
}

export interface ApplicationEventRecord {
  id: number;
  application_id: number;
  event_type: string;
  from_status: string | null;
  to_status: string;
  note: string | null;
  created_at: string;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  for (const [key, value] of Object.entries(authHeaders())) {
    headers.set(key, value);
  }
  const response = await fetch(url, { ...init, headers });
  if (!response.ok) {
    let message = `Core API returned HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Preserve the HTTP fallback.
    }
    throw new CoreApiError(response.status, message);
  }
  return (await response.json()) as T;
}

export function startApplication(
  jobId: string,
  channel: 'manual' | 'browser_agent' = 'manual',
  resumeVersionId?: string,
): Promise<ApplicationRecord> {
  return requestJson<ApplicationRecord>(`${coreRuntime().baseUrl}/api/applications`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      job_id: jobId,
      channel,
      ...(resumeVersionId ? { resume_version_id: resumeVersionId } : {}),
    }),
  });
}

export function getApplications(): Promise<ApplicationRecord[]> {
  return requestJson<ApplicationRecord[]>(`${coreRuntime().baseUrl}/api/applications`);
}

export function getApplicationEvents(id: number): Promise<ApplicationEventRecord[]> {
  return requestJson<ApplicationEventRecord[]>(
    `${coreRuntime().baseUrl}/api/applications/${id}/events`,
  );
}

export function updateApplicationStatus(
  id: number,
  status: string,
  note?: string,
): Promise<ApplicationRecord> {
  return requestJson<ApplicationRecord>(`${coreRuntime().baseUrl}/api/applications/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, ...(note ? { note } : {}) }),
  });
}
