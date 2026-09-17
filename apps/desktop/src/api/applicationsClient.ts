import { CoreApiError, authHeaders, coreRuntime } from './coreClient';

export interface ApplicationRecord {
  id: number;
  job_id: string;
  job_title: string;
  company_name: string;
  status: string;
  channel: string;
  opened_url: string;
  opened_at: string;
  updated_at: string;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  for (const [key, value] of Object.entries(authHeaders())) {
    headers.set(key, value);
  }
  const response = await fetch(url, { ...init, headers });
  if (!response.ok) {
    throw new CoreApiError(response.status, `Core API returned HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export function startApplication(jobId: string): Promise<ApplicationRecord> {
  return requestJson<ApplicationRecord>(`${coreRuntime().baseUrl}/api/applications`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id: jobId }),
  });
}

export function getApplications(): Promise<ApplicationRecord[]> {
  return requestJson<ApplicationRecord[]>(`${coreRuntime().baseUrl}/api/applications`);
}

export function updateApplicationStatus(id: number, status: string): Promise<ApplicationRecord> {
  return requestJson<ApplicationRecord>(`${coreRuntime().baseUrl}/api/applications/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
}
