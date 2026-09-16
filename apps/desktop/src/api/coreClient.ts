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

export async function getCoreHealth(baseUrl = 'http://127.0.0.1:8765'): Promise<CoreHealth> {
  const response = await fetch(`${baseUrl}/api/health`);
  if (!response.ok) throw new CoreApiError(response.status, `Core API returned HTTP ${response.status}`);
  return (await response.json()) as CoreHealth;
}
