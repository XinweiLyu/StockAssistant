import type {Sector} from './aShareMarket';
export type FlowCategory='main'|'super'|'large'|'medium'|'small';
export type FlowValues=Record<FlowCategory,number|null>;
export interface FlowPoint {source_date?:string|null;session_day?:string;observed_at:string|null;source_time?:string|null;values:FlowValues;ratios?:Partial<FlowValues>;change?:number|null;close?:number|null}
export interface FlowMember {code:string;name:string;values:FlowValues;ratios:Partial<FlowValues>;observed_at:string}
export interface FlowHealth {status?:string;error?:string;observed_at?:string;checked_at?:string}
export interface SectorFundFlow {sector:Sector;period:number;unit:string;source:string;measure:string;points:FlowPoint[];complete:boolean;summary:{main_net:number|null;net_5d?:number|null;net_20d?:number|null;consecutive_positive?:number|null;acceleration_3d?:number|null;positive_days?:number|null;covered:number;required:number|null;cumulative?:number|null};member_flows:FlowMember[];member_observed_at?:string|null;observed_at?:string|null;rank_observed_at?:string|null;anchor_date?:string|null;active:boolean;calendar_available:boolean;task_ids:string[];poll_pending?:boolean;health:Record<string,FlowHealth>;limitations:string[]}
export interface SectorFlowRank {items:(FlowPoint&{sector_id:string;name:string})[];observed_at?:string|null;source:string;source_time?:string|null;unit:string;task_id?:string|null;poll_pending?:boolean;health:FlowHealth;limitations:string[]}
export interface FlowComparisonSeries {sector:Sector;points:FlowPoint[];latest:FlowPoint|null}
export interface SectorFlowComparison {kind:'industry'|'concept';day:string;profile?:string;series:FlowComparisonSeries[];unit:string;measure:string;source:string;source_date_verified:boolean;active:boolean;calendar_available:boolean;task_id?:string|null;poll_pending:boolean;health:FlowHealth;observed_at?:string|null;limitations:string[]}
