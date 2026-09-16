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
  canonical_url: string;
  status: string;
  verification_health: string | null;
  ats: string | null;
  last_verified_at: string | null;
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
  verified_open: number;
  rediscovery_required: number;
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

export interface SourceStatus {
  source_name: string;
  last_run_status: string | null;
  last_run_at: string | null;
  last_good_version: string | null;
  last_good_hash: string | null;
  last_error: string | null;
}

export interface SourceSyncResult {
  source_name: string;
  status: string;
  version?: string | null;
  content_hash?: string | null;
  items_seen?: number;
  items_created?: number;
  items_updated?: number;
  error?: string | null;
}

export interface JobVerificationResult {
  job_id: string;
  health: string;
  final_url: string;
  ats: string | null;
  page_type: string;
  promoted: boolean;
  rediscovery_candidates?: number;
}

export interface VerificationBatchResult {
  checked: number;
  verified_open: number;
  rediscovery_required: number;
  failed: number;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = init ? await fetch(url, init) : await fetch(url);
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
  return requestJson<JobListResponse>(`${CORE_API_BASE}/api/jobs${query ? `?${query}` : ''}`);
}

export function getJobStats(): Promise<JobStats> {
  return requestJson<JobStats>(`${CORE_API_BASE}/api/jobs/stats`);
}

export function getSourceStatus(): Promise<SourceStatus[]> {
  return requestJson<SourceStatus[]>(`${CORE_API_BASE}/api/sources/status`);
}

export function syncTencentSource(): Promise<SourceSyncResult> {
  return requestJson<SourceSyncResult>(`${CORE_API_BASE}/api/sources/tencent/sync`, { method: 'POST' });
}

export function syncWorkfindSource(): Promise<SourceSyncResult> {
  return requestJson<SourceSyncResult>(`${CORE_API_BASE}/api/sources/workfind/sync`, { method: 'POST' });
}

export function syncDueSources(): Promise<SourceSyncResult[]> {
  return requestJson<SourceSyncResult[]>(`${CORE_API_BASE}/api/sources/sync-due`, { method: 'POST' });
}

export function verifyJob(jobId: string): Promise<JobVerificationResult> {
  return requestJson<JobVerificationResult>(`${CORE_API_BASE}/api/verification/jobs/${encodeURIComponent(jobId)}`, { method: 'POST' });
}

export function runDueVerification(limit = 50): Promise<VerificationBatchResult> {
  return requestJson<VerificationBatchResult>(`${CORE_API_BASE}/api/verification/run-due?limit=${limit}`, { method: 'POST' });
}
