import type {SectorFundFlow,SectorFlowRank,SectorFlowComparison} from '../types/aShareSectorFlow';
import {instrumentBase,pathBase,marketBase,type WorkspaceMarket} from './marketWorkspace';
import type {ValueResearchResult,ValueAction,ValueAssumptions,ValueReport,ValueSnapshot,ValueSupplement} from '../types/aShareValue';
import apiClient from './index';
import type { Adjust, CatalogPage, HistoryPage, MarketJobs, MarketStock, PriceScenarioResult, QuantOutlook, LivePriceResult, Sector, SectorMembersPage, IntegratedResearchResult, ResearchAction } from '../types/aShareMarket';
async function get<T>(path:string,params?:Record<string,unknown>,signal?:AbortSignal):Promise<T>{ const market=params?.market as WorkspaceMarket|undefined;const query=params?{...params}:undefined;if(query)delete query.market;return (await apiClient.get<T>((market?marketBase(market):pathBase(path))+path,{params:query,signal})).data; }
export const aShareMarketApi={
  fundFlowComparison:(kind:string,ids:string[],signal?:AbortSignal,refresh=false)=>get<SectorFlowComparison>('/sectors/fund-flow-comparison',{kind,ids:ids.join(','),refresh},signal),
  fundFlow:(id:string,period:number,signal?:AbortSignal)=>get<SectorFundFlow>('/sectors/'+encodeURIComponent(id)+'/fund-flow',{period},signal),
  refreshFundFlow:async(id:string,period:number,signal?:AbortSignal):Promise<SectorFundFlow>=>(await apiClient.post<SectorFundFlow>(marketBase('cn')+'/sectors/'+encodeURIComponent(id)+'/fund-flow/refresh',undefined,{params:{period},signal})).data,
  fundFlowRank:(kind:string,signal?:AbortSignal)=>get<SectorFlowRank>('/sectors/fund-flow-rankings',{kind},signal),
  getValue:(code:string,signal?:AbortSignal)=>get<ValueResearchResult>('/stocks/'+encodeURIComponent(code)+'/value-research',undefined,signal),
  prepareValue:async(code:string,peerOffset=0,refresh=false,signal?:AbortSignal):Promise<ValueAction>=>(await apiClient.post<ValueAction>(instrumentBase(code)+'/stocks/'+encodeURIComponent(code)+'/value-data',{peer_offset:peerOffset,refresh},{signal})).data,
  generateValue:async(code:string,snapshotId:string,force=false,signal?:AbortSignal):Promise<ValueAction>=>(await apiClient.post<ValueAction>(instrumentBase(code)+'/stocks/'+encodeURIComponent(code)+'/value-research',{snapshot_id:snapshotId,force},{signal})).data,
  saveValueAssumptions:async(code:string,snapshotId:string,revision:number,assumptions:ValueAssumptions,confirmed:boolean,signal?:AbortSignal):Promise<ValueAssumptions>=>(await apiClient.put<ValueAssumptions>(instrumentBase(code)+'/stocks/'+encodeURIComponent(code)+'/value-assumptions',{snapshot_id:snapshotId,expected_revision:revision,assumptions,confirmed},{signal})).data,
  evaluateValue:async(code:string,snapshotId:string,revision:number,signal?:AbortSignal):Promise<ValueReport>=>(await apiClient.post<ValueReport>(instrumentBase(code)+'/stocks/'+encodeURIComponent(code)+'/value-evaluate',{snapshot_id:snapshotId,assumptions_revision:revision},{signal})).data,
  supplementValue:async(code:string,snapshotId:string,facts:ValueSupplement[],signal?:AbortSignal):Promise<ValueSnapshot>=>(await apiClient.post<ValueSnapshot>(instrumentBase(code)+'/stocks/'+encodeURIComponent(code)+'/value-supplement',{snapshot_id:snapshotId,facts,attested:true},{signal})).data,

  stocks:(params:Record<string,unknown>,signal?:AbortSignal)=>get<CatalogPage>('/stocks',params,signal),
  stock:(code:string,signal?:AbortSignal)=>get<MarketStock>('/stocks/'+encodeURIComponent(code),undefined,signal),
  live:(code:string,signal?:AbortSignal)=>get<LivePriceResult>('/stocks/'+encodeURIComponent(code)+'/live',undefined,signal),
  refreshPrice:async(code:string,signal?:AbortSignal):Promise<LivePriceResult>=>(await apiClient.post<LivePriceResult>(instrumentBase(code)+'/stocks/'+encodeURIComponent(code)+'/refresh',undefined,{signal})).data,
  history:(code:string,start:string,end:string,adjust:Adjust,signal?:AbortSignal,refresh=false)=>get<HistoryPage>('/stocks/'+encodeURIComponent(code)+'/history',{start,end,adjust,refresh},signal),
  outlook:(code:string,minRewardRisk=2,signal?:AbortSignal,refresh=false)=>get<QuantOutlook>('/stocks/'+encodeURIComponent(code)+'/outlook',{min_reward_risk:minRewardRisk,refresh},signal),
  scenarios:(code:string,signal?:AbortSignal)=>get<PriceScenarioResult>('/stocks/'+encodeURIComponent(code)+'/scenarios',undefined,signal),
  integrated:(code:string,signal?:AbortSignal)=>get<IntegratedResearchResult>('/stocks/'+encodeURIComponent(code)+'/integrated-research',undefined,signal),
  prepareResearch:async(code:string,peerOffset=0,signal?:AbortSignal):Promise<ResearchAction>=>(await apiClient.post<ResearchAction>(instrumentBase(code)+'/stocks/'+encodeURIComponent(code)+'/research-data',undefined,{params:{peer_offset:peerOffset},signal})).data,
  generateIntegrated:async(code:string,force=false,signal?:AbortSignal):Promise<ResearchAction>=>(await apiClient.post<ResearchAction>(instrumentBase(code)+'/stocks/'+encodeURIComponent(code)+'/integrated-research',undefined,{params:{force},signal})).data,
  sectors:(params:Record<string,unknown>,signal?:AbortSignal)=>get<{items:Sector[];classification:string;period:number;demo:boolean}>('/sectors',params,signal),
  members:(id:string,params:Record<string,unknown>,signal?:AbortSignal)=>get<SectorMembersPage>('/sectors/'+encodeURIComponent(id)+'/members',params,signal),
  sectorHistory:(id:string,start:string,end:string,signal?:AbortSignal)=>get<HistoryPage>('/sectors/'+encodeURIComponent(id)+'/history',{start,end},signal),
  benchmarkHistory:(start:string,end:string,signal?:AbortSignal)=>get<HistoryPage>('/benchmark/history',{start,end},signal),
  jobs:(market?:WorkspaceMarket)=>get<MarketJobs>('/jobs',market?{market}:undefined),
  warmup:(market:WorkspaceMarket='cn')=>apiClient.post(marketBase(market)+'/warmup'),pause:(market:WorkspaceMarket='cn')=>apiClient.post(marketBase(market)+'/jobs/pause'),resume:(market:WorkspaceMarket='cn')=>apiClient.post(marketBase(market)+'/jobs/resume'),
};
