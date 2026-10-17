import type { QuantOutlook, HistoryPage } from '../../../types/aShareMarket';
export function outlookFixture(code='600000'):QuantOutlook {
  return {
    code,status:'ready',version:'quant-v1',as_of:'2026-10-09',generated_at:'2026-10-10T08:00:00+08:00',history_sessions:800,
    reference_price:25,price_basis:'raw',source:'tushare/daily',adjustment_basis:'tushare:2026-10-09',raw_anchor:25,qfq_anchor:20,data_hash:'h1',demo:false,
    trends:[{period:120,ma:24,distance:.04,slope:.01,state:'up'},{period:250,ma:null,distance:null,slope:null,state:'insufficient'}],
    weekly:{as_of:'2026-10-02',ma10:24,ma30:23,state:'up'},
    environment:{market_state:'range',relative20:.02,relative60:null,sector_relative20:.01,sector_relative60:null},
    forecasts:[5,20,60].map(horizon=>({horizon_sessions:horizon,target_date:null,low:20,median:25+horizon/10,high:35,sample_size:300,method:'regularized baseline',nominal_coverage:.8,calibration_state:'historical',validation:{state:'measured',samples:20,coverage:.75,mean_absolute_error:2,baseline_mean_absolute_error:3,method:'rolling origin'},points:[{sessions:horizon,date:null,low:20,median:25+horizon/10,high:35}]})),
    plan:{status:'conditional',horizon_sessions:20,entry_low:24,entry_high:25,stop:23,target_low:29,target_high:32,reward_risk:2,min_reward_risk:2,valid_until:null,conditions:['趋势保持'],invalidation:['跌破止损'],reasons:[]},
    events:[{id:'e1',title:'公司公告',url:'https://example.com/notice',date:'2026-10-09',published_at:'2026-10-09T15:00:00+08:00',first_seen:'2026-10-09T16:00:00+08:00',kind:'announcement',verified:true,impact:{state:'insufficient',samples:0,horizon_sessions:20,median_excess:null,low:null,high:null,reason:'事件尚未成熟'}}],
    archive:{snapshots:3,matured:1,coverage:.5,mean_absolute_error:2},limitations:['样本有限'],
  };
}
export function outlookHistory(adjust:'raw'|'qfq'='qfq',code='600000'):HistoryPage {
  const close=adjust==='raw'?25:20;
  return {code,state:'ready',fetched_at:'2026-10-14T14:00:00+08:00',items:[{date:'2026-10-09',open:close,high:close+1,low:close-1,close}],source:adjust==='raw'?'tushare/daily':'tushare/daily+adj_factor',adjust,adjustment_basis:'tushare:2026-10-09',requested_start:'2026-01-01',requested_end:'2026-10-09',actual_end:'2026-10-09',limitations:[]};
}
