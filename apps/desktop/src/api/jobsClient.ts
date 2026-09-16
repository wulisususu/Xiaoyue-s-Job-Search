import { CoreApiError } from './coreClient';

const CORE_API_BASE = 'http://127.0.0.1:8765';

export interface JobCompany {
  id: number;
  name: string;
  ownership: 'central_soe' | 'local_soe' | 'unknown' | string;
  province: string | null;
  level: string | null;
}

export interface RadarJob {
  id: string;
  company: JobCompany;
  title: string;
  location: string;
  industry: string;
  recruitment_batch: string;
  deadline_text: string;
  apply_url: string;
  status: string;
  source_updated_at: string | null;
  sources: string[];
}

export interface JobListResponse {
  items: RadarJob[];
  total: number;
  limit: number;
  offset: number;
}

export interface JobStats {
  total: number;
  with_url_unverified: number;
  without_url: number;
  central_soe: number;
  local_soe: number;
  unknown: number;
}

export interface JobFilters {
  ownership?: string;
  q?: string;
  location?: string;
  status?: string;
  industry?: string;
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new CoreApiError(response.status, `Core API returned HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export function getJobs(filters: JobFilters = {}): Promise<JobListResponse> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value?.trim()) params.set(key, value.trim());
  }
  const query = params.toString();
  return getJson<JobListResponse>(`${CORE_API_BASE}/api/jobs${query ? `?${query}` : ''}`);
}

export function getJobStats(): Promise<JobStats> {
  return getJson<JobStats>(`${CORE_API_BASE}/api/jobs/stats`);
}
