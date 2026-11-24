import apiClient from './index';

const BASE = '/api/v1/intelligence';
export type NewsMarket = 'cn' | 'hk' | 'us';
export type NewsView = 'hot' | 'news' | 'watchlist';
export interface NewsItem {
  id: number; title: string; summary?: string | null; url: string;
  source?: string | null; source_name?: string | null; source_type: string;
  published_at?: string | null; fetched_at?: string | null;
  market: string; scope_type: string; scope_value?: string | null;
}
export interface NewsSource {
  id: number; name: string; enabled: boolean; market: string; source_type: string;
  last_status?: string | null; last_error?: string | null; last_fetched_at?: string | null;
}
export interface NewsRefresh {
  running: boolean; processed: number; total: number; failed: number; saved_count: number;
  started_at?: string | null; finished_at?: string | null; next_allowed_at?: string | null; error?: string | null;
}
export const intelligenceApi = {
  items: async (params: Record<string, string | number | boolean>, signal?: AbortSignal) =>
    (await apiClient.get<{ items: NewsItem[]; total: number }>(`${BASE}/items`, { params, signal })).data,
  sources: async (signal?: AbortSignal) => {
    const all: NewsSource[] = [];
    for (let page = 1; ; page++) {
      const { data } = await apiClient.get<{ items: NewsSource[]; total: number }>(`${BASE}/sources`, { params: { page, page_size: 100 }, signal });
      all.push(...data.items);
      if (all.length >= data.total || !data.items.length) return all;
    }
  },
  status: async (signal?: AbortSignal) => (await apiClient.get<NewsRefresh>(`${BASE}/refresh`, { signal })).data,
  refresh: async (signal?: AbortSignal) => (await apiClient.post<NewsRefresh>(`${BASE}/refresh`, undefined, { signal })).data,
  addDefaults: async () => apiClient.post(`${BASE}/sources/defaults`, { enabled: true }),
  toggle: async (id: number, enabled: boolean) => apiClient.patch(`${BASE}/sources/${id}`, { enabled }),
};
