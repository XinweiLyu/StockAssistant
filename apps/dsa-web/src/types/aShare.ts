import type { PriceScenarioResult } from './aShareMarket';
export type ResearchMode = 'demo' | 'free' | 'tushare2000' | 'tushare5000';
export interface AssistantSettings {
  mode: ResearchMode; research_scope?: 'limited' | 'all'; pool_size: number; watchlist: string[]; account_id: number | null;
  snapshot_provider: 'akshare' | 'tushare'; realtime_entitled: boolean; news_entitled: boolean;
  announcements_entitled: boolean; free_fallback: boolean; research_enabled: boolean;
  model: string; daily_model_calls: number;
  risk: { stock_cap: number; sector_cap: number; total_cap: number; risk_per_trade: number;
    commission: number; minimum_fee: number; transfer_fee: number };
}
export interface Candidate {
  code: string; name: string; sector: string; strategy: string; score: number;
  r20: number; r60: number; v20: number; close: number; high: number; atr: number;
  sma20: number; sma60: number; valid_date: string | null; source: string;
  check?: { status: string; reasons: string[] }; plan?: { entry?: number; quantity: number | null; stop: number | null; reasons: string[]; planned_risk?: number };
}
export interface ResearchReport {
  demo: boolean; as_of: string; generated_at: string; market_ok: boolean | null;
  sample_size: number; sector_ready: boolean; input_hash: string; candidates: Candidate[];
  sectors: { code: string; name: string; strength?: number; r20: number; classification: string }[];
  limitations: string[]; exclusions: { code: string; reason: string }[];
}
export interface Journal<T> { id: number; created_at: string; key: string; payload: T }
export interface Evidence {
  title: string; content: string; code?: string; related_code?: string; source: string; url?: string;
  published_at?: string; precision?: string; coverage?: string; revision: number; first_seen: string;
  tags?: string[]; verification?: { major_risk: boolean; note: string; code: string };
}
export interface RoleResearch {
  price_scenarios?: PriceScenarioResult;
  code: string; status: string; model: string; limitations: string[];
  roles: { role: string; status: string; message?: string; claims: { text: string; sources: string[] }[] }[];
  evidence: { id: string; content: string; url?: string; source?: string }[];
}
export interface AssistantBoard {
  settings: AssistantSettings; report: ResearchReport | null;
  portfolio: { nav: number | null; cash: number | null; total_value?: number; complete: boolean; demo: boolean;
    positions: { code: string; quantity: number; market_value: number; sector: string; avg_cost: number }[];
    limitations?: string[]; realized_pnl?: number; fees?: number; tax?: number };
  holdings: { code: string; action: string; quantity: number; sellable: number | null; stop: number | null; reasons: string[]; executable: boolean }[];
  events: Journal<Evidence>[]; history: Journal<ResearchReport>[];
  alerts: Journal<{ message: string; code?: string; reasons?: string[]; timestamp: string }>[];
  health: { kind: string; status: string; source: string; fetched_at: string; error?: string; reason?: string; count?: number }[];
  research: Journal<RoleResearch>[]; model_usage: number; manual_model_usage?: number; calendar_covered: boolean;
  job: { state: string; completed: number; total: number; errors: string[]; message: string };
  sources: Record<string, string>; schedule: { running: boolean }; limitations: string[];
}
export interface Observation { report_id: number; code: string; strategy: string; saved_date: string;
  results: { horizon: number; start_date: string | null; end_date: string | null; return: number | null; limitation: string | null }[] }
