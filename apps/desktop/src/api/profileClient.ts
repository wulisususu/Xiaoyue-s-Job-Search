import { CoreApiError, authHeaders, coreRuntime } from './coreClient';

const CORE_API_BASE = () => coreRuntime().baseUrl;

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

export interface ProfileCollectionFieldDefinition {
  key: string;
  label: string;
  value_type: string;
  required: boolean;
  multiple: boolean;
}

export interface ProfileCollectionDefinition {
  kind: string;
  label: string;
  fields: ProfileCollectionFieldDefinition[];
}

export interface ProfileCollectionItem {
  id: number;
  kind: string;
  position: number;
  payload: Record<string, unknown>;
  source_type: string;
  source_ref: string | null;
  confidence: number | null;
  confirmed: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProfileCollectionDraft {
  id: number;
  resume_version_id: string;
  resume_version_number: number;
  resume_filename: string;
  kind: string;
  label: string;
  payload: Record<string, unknown>;
  confidence: number | null;
  extractor_name: string;
  status: string;
  created_at: string;
  reviewed_at: string | null;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${CORE_API_BASE()}${path}`;
  const auth = authHeaders();
  const authEntries = Object.entries(auth);
  let requestInit = init;
  if (authEntries.length > 0) {
    const headers = new Headers(init?.headers);
    for (const [key, value] of authEntries) headers.set(key, value);
    requestInit = { ...init, headers };
  }

  const response = requestInit ? await fetch(url, requestInit) : await fetch(url);
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
  return requestJson<ProfileDefinition[]>('/api/profile/definitions');
}

export function getProfileFields(): Promise<ProfileField[]> {
  return requestJson<ProfileField[]>('/api/profile/fields');
}

export function getPendingProfileDrafts(): Promise<ProfileDraft[]> {
  return requestJson<ProfileDraft[]>('/api/profile/drafts?status=PENDING');
}

export function acceptProfileDraft(draftId: number): Promise<ProfileField> {
  return requestJson<ProfileField>(`/api/profile/drafts/${draftId}/accept`, {
    method: 'POST',
  });
}

export function rejectProfileDraft(draftId: number): Promise<ProfileDraft> {
  return requestJson<ProfileDraft>(`/api/profile/drafts/${draftId}/reject`, {
    method: 'POST',
  });
}

export function saveProfileField(fieldKey: string, value: unknown): Promise<ProfileField> {
  return requestJson<ProfileField>(`/api/profile/fields/${encodeURIComponent(fieldKey)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value }),
  });
}

export function getProfileCollectionDefinitions(): Promise<ProfileCollectionDefinition[]> {
  return requestJson<ProfileCollectionDefinition[]>('/api/profile/collections/definitions');
}

export function getProfileCollection(kind: string): Promise<ProfileCollectionItem[]> {
  return requestJson<ProfileCollectionItem[]>(`/api/profile/collections/${encodeURIComponent(kind)}`);
}

export function createProfileCollectionItem(
  kind: string,
  payload: Record<string, unknown>,
): Promise<ProfileCollectionItem> {
  return requestJson<ProfileCollectionItem>(`/api/profile/collections/${encodeURIComponent(kind)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ payload }),
  });
}

export function updateProfileCollectionItem(
  kind: string,
  itemId: number,
  payload: Record<string, unknown>,
): Promise<ProfileCollectionItem> {
  return requestJson<ProfileCollectionItem>(`/api/profile/collections/${encodeURIComponent(kind)}/${itemId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ payload }),
  });
}

export function deleteProfileCollectionItem(kind: string, itemId: number): Promise<{ deleted_id: number }> {
  return requestJson<{ deleted_id: number }>(`/api/profile/collections/${encodeURIComponent(kind)}/${itemId}`, {
    method: 'DELETE',
  });
}

export function reorderProfileCollectionItems(kind: string, itemIds: number[]): Promise<ProfileCollectionItem[]> {
  return requestJson<ProfileCollectionItem[]>(`/api/profile/collections/${encodeURIComponent(kind)}/order`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ item_ids: itemIds }),
  });
}

export function getPendingProfileCollectionDrafts(): Promise<ProfileCollectionDraft[]> {
  return requestJson<ProfileCollectionDraft[]>('/api/profile/collection-drafts?status=PENDING');
}

export function acceptProfileCollectionDraft(draftId: number): Promise<ProfileCollectionItem> {
  return requestJson<ProfileCollectionItem>(`/api/profile/collection-drafts/${draftId}/accept`, {
    method: 'POST',
  });
}

export function rejectProfileCollectionDraft(draftId: number): Promise<ProfileCollectionDraft> {
  return requestJson<ProfileCollectionDraft>(`/api/profile/collection-drafts/${draftId}/reject`, {
    method: 'POST',
  });
}
