import type {ValueResearchResult,ValueAction,ValueAssumptions,ValueReport,ValueSnapshot,ValueSupplement} from '../types/aShareValue';
import apiClient from './index';
import type { Adjust, CatalogPage, HistoryPage, MarketJobs, MarketStock, PriceScenarioResult, QuantOutlook, LivePriceResult, Sector, SectorMembersPage, IntegratedResearchResult, ResearchAction } from '../types/aShareMarket';
const BASE='/api/v1/a-share/market';
async function get<T>(path:string,params?:Record<string,unknown>,signal?:AbortSignal):Promise<T>{ return (await apiClient.get<T>(BASE+path,{params,signal})).data; }
export const aShareMarketApi={
  getValue:(code:string,signal?:AbortSignal)=>get<ValueResearchResult>('/stocks/'+encodeURIComponent(code)+'/value-research',undefined,signal),
  prepareValue:async(code:string,peerOffset=0,refresh=false,signal?:AbortSignal):Promise<ValueAction>=>(await apiClient.post<ValueAction>(BASE+'/stocks/'+encodeURIComponent(code)+'/value-data',{peer_offset:peerOffset,refresh},{signal})).data,
  generateValue:async(code:string,snapshotId:string,force=false,signal?:AbortSignal):Promise<ValueAction>=>(await apiClient.post<ValueAction>(BASE+'/stocks/'+encodeURIComponent(code)+'/value-research',{snapshot_id:snapshotId,force},{signal})).data,
  saveValueAssumptions:async(code:string,snapshotId:string,revision:number,assumptions:ValueAssumptions,confirmed:boolean,signal?:AbortSignal):Promise<ValueAssumptions>=>(await apiClient.put<ValueAssumptions>(BASE+'/stocks/'+encodeURIComponent(code)+'/value-assumptions',{snapshot_id:snapshotId,expected_revision:revision,assumptions,confirmed},{signal})).data,
  evaluateValue:async(code:string,snapshotId:string,revision:number,signal?:AbortSignal):Promise<ValueReport>=>(await apiClient.post<ValueReport>(BASE+'/stocks/'+encodeURIComponent(code)+'/value-evaluate',{snapshot_id:snapshotId,assumptions_revision:revision},{signal})).data,
  supplementValue:async(code:string,snapshotId:string,facts:ValueSupplement[],signal?:AbortSignal):Promise<ValueSnapshot>=>(await apiClient.post<ValueSnapshot>(BASE+'/stocks/'+encodeURIComponent(code)+'/value-supplement',{snapshot_id:snapshotId,facts,attested:true},{signal})).data,

  stocks:(params:Record<string,unknown>,signal?:AbortSignal)=>get<CatalogPage>('/stocks',params,signal),
  stock:(code:string,signal?:AbortSignal)=>get<MarketStock>('/stocks/'+encodeURIComponent(code),undefined,signal),
  live:(code:string,signal?:AbortSignal)=>get<LivePriceResult>('/stocks/'+encodeURIComponent(code)+'/live',undefined,signal),
  refreshPrice:async(code:string,signal?:AbortSignal):Promise<LivePriceResult>=>(await apiClient.post<LivePriceResult>(BASE+'/stocks/'+encodeURIComponent(code)+'/refresh',undefined,{signal})).data,
  history:(code:string,start:string,end:string,adjust:Adjust,signal?:AbortSignal,refresh=false)=>get<HistoryPage>('/stocks/'+encodeURIComponent(code)+'/history',{start,end,adjust,refresh},signal),
  outlook:(code:string,minRewardRisk=2,signal?:AbortSignal,refresh=false)=>get<QuantOutlook>('/stocks/'+encodeURIComponent(code)+'/outlook',{min_reward_risk:minRewardRisk,refresh},signal),
  scenarios:(code:string,signal?:AbortSignal)=>get<PriceScenarioResult>('/stocks/'+encodeURIComponent(code)+'/scenarios',undefined,signal),
  integrated:(code:string,signal?:AbortSignal)=>get<IntegratedResearchResult>('/stocks/'+encodeURIComponent(code)+'/integrated-research',undefined,signal),
  prepareResearch:async(code:string,peerOffset=0,signal?:AbortSignal):Promise<ResearchAction>=>(await apiClient.post<ResearchAction>(BASE+'/stocks/'+encodeURIComponent(code)+'/research-data',undefined,{params:{peer_offset:peerOffset},signal})).data,
  generateIntegrated:async(code:string,force=false,signal?:AbortSignal):Promise<ResearchAction>=>(await apiClient.post<ResearchAction>(BASE+'/stocks/'+encodeURIComponent(code)+'/integrated-research',undefined,{params:{force},signal})).data,
  sectors:(params:Record<string,unknown>,signal?:AbortSignal)=>get<{items:Sector[];classification:string;period:number;demo:boolean}>('/sectors',params,signal),
  members:(id:string,params:Record<string,unknown>,signal?:AbortSignal)=>get<SectorMembersPage>('/sectors/'+encodeURIComponent(id)+'/members',params,signal),
  sectorHistory:(id:string,start:string,end:string,signal?:AbortSignal)=>get<HistoryPage>('/sectors/'+encodeURIComponent(id)+'/history',{start,end},signal),
  benchmarkHistory:(start:string,end:string,signal?:AbortSignal)=>get<HistoryPage>('/benchmark/history',{start,end},signal),
  jobs:()=>get<MarketJobs>('/jobs'),
  warmup:()=>apiClient.post(BASE+'/warmup'),pause:()=>apiClient.post(BASE+'/jobs/pause'),resume:()=>apiClient.post(BASE+'/jobs/resume'),
};
