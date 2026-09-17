export interface CoreHealth {
  status: 'ok';
  database: 'ok';
  version: string;
}

export class CoreApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = 'CoreApiError';
  }
}

/** Injected by the Tauri shell: the sidecar's dynamic endpoint and the
 *  per-launch session token. In dev (core started by scripts/dev.ps1) it is
 *  absent and we fall back to the fixed local dev endpoint. */
interface CoreRuntime {
  baseUrl: string;
  sessionToken: string;
}

declare global {
  interface Window {
    __XIAOYUE_CORE__?: Partial<CoreRuntime>;
  }
}

const DEFAULT_BASE_URL = 'http://127.0.0.1:8765';

export function coreRuntime(): CoreRuntime {
  const injected = typeof window !== 'undefined' ? window.__XIAOYUE_CORE__ : undefined;
  return {
    baseUrl: injected?.baseUrl || DEFAULT_BASE_URL,
    sessionToken: injected?.sessionToken || '',
  };
}

export function authHeaders(): Record<string, string> {
  const { sessionToken } = coreRuntime();
  return sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {};
}

export async function getCoreHealth(baseUrl?: string): Promise<CoreHealth> {
  const base = baseUrl ?? coreRuntime().baseUrl;
  const response = await fetch(`${base}/api/health`);
  if (!response.ok) throw new CoreApiError(response.status, `Core API returned HTTP ${response.status}`);
  return (await response.json()) as CoreHealth;
}
