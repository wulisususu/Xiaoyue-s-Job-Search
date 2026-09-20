import { CoreApiError, authHeaders, coreRuntime } from './coreClient';

export interface DashboardSummary {
  total_jobs: number;
  new_jobs_today: number;
  verified_open: number;
  central_soe_jobs: number;
  applications_total: number;
  in_progress: number;
  submitted: number;
  interviewing: number;
  offers: number;
}

export async function getDashboardSummary(): Promise<DashboardSummary> {
  const response = await fetch(`${coreRuntime().baseUrl}/api/dashboard/summary`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new CoreApiError(response.status, `Core API returned HTTP ${response.status}`);
  }
  return (await response.json()) as DashboardSummary;
}
