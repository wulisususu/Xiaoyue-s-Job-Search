import { CoreApiError, authHeaders, coreRuntime } from './coreClient';

export interface BrowserAgentSession {
  id: string;
  application_id: number;
  url: string;
  status: string;
  browser: string;
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

export interface BrowserPlanFieldSummary {
  field_id: string;
  label: string;
  control_type: string;
}

export interface BrowserFillPlan {
  token: string;
  session_id: string;
  page_url: string;
  items: BrowserFillPlanItem[];
  unmatched: BrowserPlanFieldSummary[];
  blocked: BrowserPlanFieldSummary[];
}

export interface BrowserFillResult {
  filled_count: number;
  skipped_count: number;
  status: string;
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

export function startBrowserAgentSession(applicationId: number): Promise<BrowserAgentSession> {
  return requestJson<BrowserAgentSession>('/api/browser-agent/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ application_id: applicationId }),
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

export function closeBrowserAgentSession(sessionId: string): Promise<{ closed: boolean }> {
  return requestJson<{ closed: boolean }>(`/api/browser-agent/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  });
}
