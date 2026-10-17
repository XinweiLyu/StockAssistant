import apiClient from './index';

export interface CurrentChip {
  code: string;
  date: string;
  source: string;
  profit_ratio: number;
  avg_cost: number;
  cost_90_low: number;
  cost_90_high: number;
  concentration_90: number;
  cost_70_low: number;
  cost_70_high: number;
  concentration_70: number;
}

export async function getCurrentChip(code: string, signal?: AbortSignal): Promise<CurrentChip | null> {
  const response = await apiClient.get<{ status: 'available' | 'missing'; chip: CurrentChip | null }>(
    `/api/v1/a-share/chip/${encodeURIComponent(code)}`,
    { signal, timeout: 45000 },
  );
  return response.data.chip;
}
