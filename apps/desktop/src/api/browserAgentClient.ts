import { CoreApiError, authHeaders, coreRuntime } from './coreClient';

export interface BrowserAgentSession {
  id: string;
  application_id: number;
  url: string;
  status: string;
  browser: string;
  mode: 'verify' | 'fill';
}

export interface BrowserFillPlanItem {
  field_id: string;
  label: string;
  control_type: string;
  value: unknown;
  source_path: string;
  confidence: number;
  reason: string;
  requires_confirmation: boolean;
}

export interface BrowserAttachmentPlanItem {
  field_id: string;
  label: string;
  kind: string;
  required: boolean;
}

export interface BrowserPlanFieldSummary {
  field_id: string;
  label: string;
  control_type: string;
}

export interface BrowserFillPlan {
  token: string;
  session_id: string;
  page_url: string;
  page_revision: string;
  adapter_id: string;
  adapter_display_name: string;
  adapter_implementation: string;
  adapter_capabilities: string[];
  adapter_limitations: string[];
  items: BrowserFillPlanItem[];
  attachments: BrowserAttachmentPlanItem[];
  unmatched: BrowserPlanFieldSummary[];
  blocked: BrowserPlanFieldSummary[];
}

export interface BrowserFillFieldResult {
  field_id: string;
  requested: unknown;
  observed: unknown | null;
  status: 'VERIFIED' | 'FAILED' | 'UNCERTAIN' | 'SKIPPED';
  reason: string;
}

export interface BrowserFillResult {
  filled_count: number;
  skipped_count: number;
  verified_count: number;
  failed_count: number;
  uncertain_count: number;
  results: BrowserFillFieldResult[];
  status: string;
}

export interface BrowserResumeUploadResult {
  field_id: string;
  resume_version_id: string;
  filename: string;
  status: string;
}

export interface BrowserVerificationResult {
  verified: boolean;
  job_status: string;
  page_url: string;
  evidence_count: number;
  page_revision: string;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  for (const [key, value] of Object.entries(authHeaders())) headers.set(key, value);
  const response = await fetch(`${coreRuntime().baseUrl}${path}`, { ...init, headers });
  if (!response.ok) {
    let message = `Core API returned HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep HTTP fallback for browser/DevTools failures.
    }
    throw new CoreApiError(response.status, message);
  }
  return (await response.json()) as T;
}

export function startBrowserAgentSession(
  applicationId: number,
  mode: 'verify' | 'fill' = 'fill',
): Promise<BrowserAgentSession> {
  return requestJson<BrowserAgentSession>('/api/browser-agent/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ application_id: applicationId, mode }),
  });
}

export function getBrowserAgentSessions(): Promise<BrowserAgentSession[]> {
  return requestJson<BrowserAgentSession[]>('/api/browser-agent/sessions');
}

export function getBrowserFillPlan(sessionId: string): Promise<BrowserFillPlan> {
  return requestJson<BrowserFillPlan>(`/api/browser-agent/sessions/${encodeURIComponent(sessionId)}/plan`, {
    method: 'POST',
  });
}

export function getBrowserSemanticPlan(
  sessionId: string,
  planToken: string,
): Promise<BrowserFillPlan> {
  return requestJson<BrowserFillPlan>(
    `/api/browser-agent/sessions/${encodeURIComponent(sessionId)}/semantic-plan`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan_token: planToken }),
    },
  );
}

export function fillBrowserAgentPlan(
  sessionId: string,
  planToken: string,
  fieldIds: string[],
): Promise<BrowserFillResult> {
  return requestJson<BrowserFillResult>(`/api/browser-agent/sessions/${encodeURIComponent(sessionId)}/fill`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan_token: planToken, field_ids: fieldIds }),
  });
}

export function uploadBrowserAgentResume(
  sessionId: string,
  planToken: string,
  fieldId: string,
  resumeVersionId: string,
): Promise<BrowserResumeUploadResult> {
  return requestJson<BrowserResumeUploadResult>(
    `/api/browser-agent/sessions/${encodeURIComponent(sessionId)}/resume-upload`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        plan_token: planToken,
        field_id: fieldId,
        resume_version_id: resumeVersionId,
      }),
    },
  );
}

export function confirmBrowserAgentVerification(sessionId: string): Promise<BrowserVerificationResult> {
  return requestJson<BrowserVerificationResult>(
    `/api/browser-agent/sessions/${encodeURIComponent(sessionId)}/verify`,
    { method: 'POST' },
  );
}

export function closeBrowserAgentSession(sessionId: string): Promise<{ closed: boolean }> {
  return requestJson<{ closed: boolean }>(`/api/browser-agent/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  });
}
