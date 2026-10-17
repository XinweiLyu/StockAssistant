import type { LivePriceResult } from '../../../types/aShareMarket';
export function liveFixture(code='600000'):LivePriceResult {
  return {code,state:'ready',task_id:'live-1',requested_at:'2026-10-14T13:59:00+08:00',fetched_at:'2026-10-14T14:01:00+08:00',quote:{price:27.5,source:'tushare/daily',source_time:'2026-10-14T14:00:00+08:00',fetched_at:'2026-10-14T14:01:00+08:00',trade_date:'2026-10-14'},bars:{raw:{date:'2026-10-14',open:25,high:28,low:24,close:27.5,volume:200},qfq:{date:'2026-10-14',open:20,high:22.4,low:19.2,close:22,volume:200}},provisional:true,source:'tushare/daily',adjustment_basis:'tushare:2026-10-09',message:'最新行情已取得',completed_day:'2026-10-09',history_updated:true,history_binding:{raw:{source:'tushare/daily',adjustment_basis:'tushare:2026-10-09',fetched_at:'2026-10-14T14:00:00+08:00',anchor_date:'2026-10-09',anchor_close:25},qfq:{source:'tushare/daily+adj_factor',adjustment_basis:'tushare:2026-10-09',fetched_at:'2026-10-14T14:00:00+08:00',anchor_date:'2026-10-09',anchor_close:20}},demo:false};
}
export function unavailableLive(code='600000'):LivePriceResult {
  return {...liveFixture(code),state:'unavailable',quote:null,bars:{raw:null,qfq:null},provisional:false,message:'尚无最新行情缓存'};
}
