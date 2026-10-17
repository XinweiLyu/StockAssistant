export type Adjust = 'raw' | 'qfq';
export interface MarketBar { date: string; open: number; high: number; low: number; close: number; volume?: number | null; amount?: number | null }
export interface MarketQuote { price: number; change?: number | null; source: string; source_time?: string | null; fetched_at: string; trade_date?: string | null }
export interface Sector { sector_id: string; name: string; code: string; kind: 'industry'|'concept'; classification: string; source: string; change: number|null; fetched_at: string; source_time?: string|null; history_as_of?: string; membership_version?: string|null; member_breadth?: { total:number;up:number;down:number;flat:number;unknown:number } }
export interface MarketStock { code: string; name: string; board?: string; exchange?: string; st?: boolean|null; identity_verified?: boolean; source: string; quote: MarketQuote|null; industries: Sector[]; concepts: Sector[]; demo?: boolean }
export interface Coverage { catalog_total:number; attempted:number; valid:number; excluded:number; unverified:number; failed:number; pending:number; state:string; as_of?:string|null }
export interface CatalogPage { items:MarketStock[];total:number;page:number;page_size:number;demo?:boolean;coverage?:Coverage }
export interface SectorMembersPage extends CatalogPage { membership:{codes:string[];version:string|null;fetched_at?:string|null;state:'pending'|'ready'} }
export interface HistoryPage { code:string; items:MarketBar[]; warmup_items?:MarketBar[]; adjust:Adjust; source?:string|null; adjustment_basis?:string|null; requested_start:string;requested_end:string;actual_start?:string|null;actual_end?:string|null;state:string;fetched_at?:string|null;task_id?:string|null;demo?:boolean;limitations:string[] }
export interface PriceContext { code:string;anchor_date:string;reference_price:number;currency:'CNY';price_basis:'raw';data_hash:string;adjustment_basis:string;raw_anchor?:number|null;qfq_anchor?:number|null;demo?:boolean }
export interface AITradeLevels { horizon_sessions:number;entry_low:number;entry_high:number;stop_reference:number;sell_low:number;sell_high:number;conditions:string[];invalidation:string[];sources:string[] }
export interface PriceForecast { scenario:'bear'|'base'|'bull';horizon_sessions:number;low:number;high:number;conditions:string[];sources:string[] }
export interface PriceScenarioResult { context?:PriceContext|null;trade_levels:AITradeLevels|null;forecasts:PriceForecast[];status:string;model?:string;generated_at?:string;message?:string;limitations?:string[] }
export type IndicatorName = 'MA5'|'MA10'|'MA20'|'MA60'|'MA120'|'MA250'|'BOLL'|'volume'|'MACD'|'RSI'|'ATR20';
export type IndicatorSelection = Partial<Record<IndicatorName,boolean>>;
export interface ChartPriceLevel { id:string;source:'rule'|'ai'|'report'|'quant'|'integrated';kind:string;low:number;high?:number|null;label:string;active:boolean;anchor_date?:string;horizon?:number }
export interface MarketJobs { paused:boolean;counts:Record<string,number>;coverage:Coverage;health?:Record<string,{status:string;fetched_at:string}>;tasks?:{id:string;kind:string;state:string;error?:string}[] }

export interface QuantForecastPoint { sessions:number;date:string|null;low:number;median:number;high:number }
export interface QuantForecast {
  horizon_sessions:number;target_date:string|null;low:number;median:number;high:number;sample_size:number;method:string;nominal_coverage:number;calibration_state:'historical'|'insufficient';
  validation:{state:'measured'|'insufficient';samples:number;coverage_samples?:number|null;coverage:number|null;mean_absolute_error:number|null;baseline_mean_absolute_error:number|null;method:string};
  points:QuantForecastPoint[];
}
export interface QuantOutlook {
  code:string;status:'pending'|'ready'|'partial'|'insufficient'|'failed';version:string;as_of:string;generated_at:string;history_sessions:number;
  reference_price:number|null;price_basis:'raw';source:string|null;adjustment_basis:string|null;raw_anchor:number|null;qfq_anchor:number|null;data_hash:string;demo:boolean;
  trends:{period:number;ma:number|null;distance:number|null;slope:number|null;state:'up'|'down'|'range'|'insufficient'}[];
  weekly:{as_of:string|null;ma10:number|null;ma30:number|null;state:'up'|'down'|'range'|'insufficient'};
  environment:{market_state:'up'|'down'|'range'|'unknown';relative20:number|null;relative60:number|null;sector_relative20:number|null;sector_relative60:number|null};
  forecasts:QuantForecast[];
  plan:{status:'observe'|'conditional';horizon_sessions:number;entry_low:number|null;entry_high:number|null;stop:number|null;target_low:number|null;target_high:number|null;reward_risk:number|null;min_reward_risk:number;valid_until:string|null;conditions:string[];invalidation:string[];reasons:string[]};
  events:{id:string;title:string;url:string|null;date:string|null;published_at:string|null;first_seen:string|null;kind:string;verified:boolean;impact:{state:'observed'|'insufficient';samples:number;horizon_sessions:number;median_excess:number|null;low:number|null;high:number|null;reason:string}}[];
  archive:{snapshots:number;matured:number;coverage:number|null;mean_absolute_error:number|null};limitations:string[];
}
export interface ChartForecast {
  code:string;anchor_date:string;anchor_price:number;horizon_sessions:number;target_date:string|null;nominal_coverage:number;points:QuantForecastPoint[];
}

export interface ChartEvent { id:string;title:string;date:string|null;verified:boolean }

export interface LiveHistoryBinding { source:string|null;adjustment_basis:string|null;fetched_at:string|null;anchor_date:string;anchor_close:number }
export interface LivePriceResult {
  code:string;state:'pending'|'ready'|'failed'|'unavailable';task_id?:string|null;requested_at?:string|null;fetched_at?:string|null;
  quote:MarketQuote|null;bars:{raw:MarketBar|null;qfq:MarketBar|null};provisional:boolean;source:string|null;adjustment_basis:string|null;
  message:string;completed_day:string;history_updated:boolean;history_binding?:Partial<Record<Adjust,LiveHistoryBinding|null>>;demo:boolean;
}
export interface ChartLiveBar { code:string;bar:MarketBar;fetched_at:string|null }

export interface IntegratedHistoryBinding {
  anchor_date:string;source:string;raw_anchor:number;qfq_anchor:number;adjustment_basis:string;
  raw_fetched_at:string|null;qfq_fetched_at:string|null;
}
export interface IntegratedFact {
  fact_id:string;category:string;source:string;url?:string|null;report_period?:string|null;
  published_at?:string|null;available_at?:string;vintage_quality?:string;values:Record<string,unknown>;
}
export interface EventCaseStats {
  sample_size:number;companies:number;numerical_eligible:boolean;median_return?:number|null;
  median_market_excess?:number|null;median_industry_excess?:number|null;median_adverse?:number|null;
  reason:string;concentration_warning?:boolean;
}
export interface IntegratedForecast extends PriceForecast { basis_ids:string[];derivation:string }
export interface IntegratedPlan {
  horizon_sessions:number;strategy_kind:string;status:'conditional'|'observe';entry_low:number|null;entry_high:number|null;stop_reference:number|null;
  second_entry:{low:number;high:number;conditions:string[];invalidation:string[]}|null;targets:number[];
  conditions:string[];invalidation:string[];valid_until:string;sources:string[];basis_ids:string[];derivation:string;
  reward_risk:number|null;net_reward_risk?:number|null;min_reward_risk:number;rejection_reasons:string[];
}
export interface IntegratedRole {role:string;label:string;status:string;claims:{text:string;sources:string[]}[];message?:string}
export interface IntegratedReport {
  code:string;data_hash:string;status:string;model?:string;generated_at:string;anchor_date:string;reference_price:number;
  history_binding:IntegratedHistoryBinding;calibrated:boolean;calls:number;extraction_calls:number;expected_calls:number;cached:boolean;
  timing?:{started_at:string;elapsed_seconds:number;role_durations:Record<string,number>};
  roles:IntegratedRole[];forecasts:IntegratedForecast[];plans:IntegratedPlan[];limitations:string[];stale?:boolean;error?:string;
  evidence:{id:string;category:string;source?:string;url?:string|null;values?:Record<string,unknown>}[];
  role_evidence?:Record<string,{sent_ids:string[];omitted_ids:string[]}>;
  rejected?:number;rejections?:{kind:string;horizon:number|null;reason:string}[];
}
export interface IntegratedBundle {
  code:string;name:string;data_hash:string;anchor_date:string;cutoff:string;reference_price:number;source:string;history_binding:IntegratedHistoryBinding;
  facts:IntegratedFact[];events:{id:string;title:string;url?:string;published_at?:string;text_status?:string;text?:string;direction?:string;intensity?:number|null}[];
  cases:{horizons:Record<string,EventCaseStats>;cases:Record<string,unknown>[];reference_cases:Record<string,unknown>[];excluded:Record<string,number>;missing_dimensions:string[];limitations:string[];optional_missing?:string[]};
  coverage:{category:string;status:string;count:number;texts?:number;sources?:string[];source?:string;limitations?:string[]}[];
  missing:string[];context:Record<string,unknown>&{financial_coverage?:{report_period:string|null;fields:Record<string,{status:string;reason:string;values?:unknown[];fact_ids:string[];value?:number|null;observations?:{fact_id:string;source:string;report_type:string|null;value:number}[]}>}};baseline:Partial<QuantOutlook>;
}
export interface IntegratedResearchResult {
  code:string;status:string;bundle:IntegratedBundle|null;report:IntegratedReport|null;demo:boolean;message:string;
  progress:{completed:number;expected:number;current?:string|null;calls?:number;message:string;phase?:string;percent?:number;started_at?:string;elapsed_seconds?:number|null;eta_seconds?:[number,number]|null;eta_samples?:number;estimate_overrun?:boolean;steps?:{role:string;label:string;status:string;duration_seconds?:number|null}[]}|null;
  task:{id:string;state:string;error?:string|null;updated_at?:string}|null;
  validation?:IntegratedValidation|null;
  peer_progress?:{total:number;complete:number;pending:number;running:number;failed:number;next_offset:number};
}
export interface IntegratedValidation {
  status:string;snapshots:number;portfolio_return:null;costs_verified:boolean;limitations:string[];
  horizons:Record<string,{matured:number;non_overlapping_samples:number;status:string;mean_absolute_error:number|null;direction_accuracy:number|null;observed_scenario_coverage:number|null;mean_adverse:number|null}>;
  comparison:{horizons:Record<string,{samples:number;unchanged_price_mae:number|null;price_model_mae:number|null;integrated_mae:number|null}>};
}
export interface ResearchAction {accepted:boolean;status:string;message?:string;task_id?:string;expected_calls?:number;cached?:boolean}
export interface ChartIntegratedScenario {
  scenario:'bear'|'base'|'bull';
  // median is a chart coordinate: the arithmetic interval midpoint, not a calibrated median.
  points:(QuantForecastPoint&{conditions:string[];sources:string[]})[];
}
export type ChartIntegratedForecast=Omit<ChartForecast,'nominal_coverage'>&{
  scenarios?:ChartIntegratedScenario[];
  missing_nodes?:{sessions:number;scenario:'bear'|'base'|'bull'}[];
};
