import { CoreApiError } from './coreClient';

const CORE_API_BASE = 'http://127.0.0.1:8765';

export interface ProfileDefinition {
  field_key: string;
  label: string;
  category: string;
  value_type: string;
  multiple: boolean;
}

export interface ProfileField {
  field_key: string;
  label: string;
  category: string;
  value: unknown;
  value_type: string;
  source_type: string;
  source_ref: string | null;
  confidence: number | null;
  confirmed: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProfileDraft {
  id: number;
  resume_version_id: string;
  resume_version_number: number;
  resume_filename: string;
  field_key: string;
  label: string;
  category: string;
  value: unknown;
  value_type: string;
  confidence: number | null;
  extractor_name: string;
  status: string;
  created_at: string;
  reviewed_at: string | null;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = init ? await fetch(url, init) : await fetch(url);
  if (!response.ok) {
    let message = `Core API returned HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the status-based fallback for non-JSON responses.
    }
    throw new CoreApiError(response.status, message);
  }
  return (await response.json()) as T;
}

export function getProfileDefinitions(): Promise<ProfileDefinition[]> {
  return requestJson<ProfileDefinition[]>(`${CORE_API_BASE}/api/profile/definitions`);
}

export function getProfileFields(): Promise<ProfileField[]> {
  return requestJson<ProfileField[]>(`${CORE_API_BASE}/api/profile/fields`);
}

export function getPendingProfileDrafts(): Promise<ProfileDraft[]> {
  return requestJson<ProfileDraft[]>(`${CORE_API_BASE}/api/profile/drafts?status=PENDING`);
}

export function acceptProfileDraft(draftId: number): Promise<ProfileField> {
  return requestJson<ProfileField>(`${CORE_API_BASE}/api/profile/drafts/${draftId}/accept`, {
    method: 'POST',
  });
}

export function rejectProfileDraft(draftId: number): Promise<ProfileDraft> {
  return requestJson<ProfileDraft>(`${CORE_API_BASE}/api/profile/drafts/${draftId}/reject`, {
    method: 'POST',
  });
}

export function saveProfileField(fieldKey: string, value: unknown): Promise<ProfileField> {
  return requestJson<ProfileField>(`${CORE_API_BASE}/api/profile/fields/${encodeURIComponent(fieldKey)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value }),
  });
}
