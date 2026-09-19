import { CoreApiError, authHeaders, coreRuntime } from './coreClient';

export interface AIProviderConfig {
  id: string;
  provider_name: string;
  base_url: string;
  text_model: string;
  vision_model: string | null;
  temperature: number;
  timeout_seconds: number;
  supports_json_schema: boolean;
  supports_vision: boolean;
  has_api_key: boolean;
  created_at: string;
  updated_at: string;
}

export interface AIProviderWrite {
  provider_name: string;
  base_url: string;
  text_model: string;
  vision_model: string | null;
  temperature: number;
  timeout_seconds: number;
  supports_json_schema: boolean;
  supports_vision: boolean;
}

export interface AIProviderTestResult {
  ok: boolean;
  provider_name: string;
  model: string;
  latency_ms: number;
}

export interface AIExtractionRun {
  id: number;
  resume_version_id: string;
  provider: string;
  model: string;
  prompt_version: string;
  schema_version: string;
  status: string;
  input_hash: string | null;
  error: string | null;
  created_at: string;
  completed_at: string | null;
  scalar_draft_count: number;
  collection_draft_count: number;
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
      // Preserve the status fallback for non-JSON provider/proxy failures.
    }
    throw new CoreApiError(response.status, message);
  }
  return (await response.json()) as T;
}

export function getAIProvider(): Promise<AIProviderConfig | null> {
  return requestJson<AIProviderConfig | null>('/api/ai/provider');
}

export function saveAIProvider(config: AIProviderWrite): Promise<AIProviderConfig> {
  return requestJson<AIProviderConfig>('/api/ai/provider', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
}

export function saveAIProviderApiKey(apiKey: string): Promise<AIProviderConfig> {
  return requestJson<AIProviderConfig>('/api/ai/provider/api-key', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export function deleteAIProviderApiKey(): Promise<AIProviderConfig> {
  return requestJson<AIProviderConfig>('/api/ai/provider/api-key', { method: 'DELETE' });
}

export function testAIProvider(): Promise<AIProviderTestResult> {
  return requestJson<AIProviderTestResult>('/api/ai/provider/test', { method: 'POST' });
}

export function createExtractionRun(resumeVersionId: string): Promise<AIExtractionRun> {
  return requestJson<AIExtractionRun>('/api/ai/extraction-runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resume_version_id: resumeVersionId }),
  });
}
