import type { IntegratedResearchResult, HistoryPage } from '../../../types/aShareMarket';
export const integratedHistory=(adjust:'raw'|'qfq'='raw'):HistoryPage=>({code:'000807',adjust,state:'ready',
  source:'fixture',adjustment_basis:'basis1',fetched_at:'generation1',actual_end:'2026-10-15',
  requested_start:'2026-01-01',requested_end:'2026-10-15',limitations:[],
  items:[{date:'2026-10-15',open:adjust==='raw'?20:16,close:adjust==='raw'?20:16,high:adjust==='raw'?21:17,low:adjust==='raw'?19:15}]});
export function integratedFixture():IntegratedResearchResult {
  const binding={anchor_date:'2026-10-15',source:'fixture',raw_anchor:20,qfq_anchor:16,adjustment_basis:'basis1',raw_fetched_at:'generation1',qfq_fetched_at:'generation1'};
  return {code:'000807',status:'ready',demo:false,task:null,progress:null,message:'已取得资料',
    bundle:{code:'000807',name:'云铝股份',data_hash:'bundle1',anchor_date:'2026-10-15',cutoff:'2026-10-16T10:00:00+08:00',reference_price:20,source:'fixture',history_binding:binding,
      facts:[{fact_id:'F1',category:'financial',source:'eastmoney',report_period:'2026-06-30',available_at:'2026-08-20T16:00:00+08:00',values:{net_profit:123000000}}],
      events:[],cases:{horizons:{'20':{sample_size:2,companies:1,numerical_eligible:false,median_return:.1,median_market_excess:.03,median_industry_excess:.01,reason:'样本不足'}},cases:[],reference_cases:[],excluded:{},missing_dimensions:[],limitations:[]},
      coverage:[{category:'financial',status:'ready',count:12},{category:'news',status:'missing',count:0}],missing:['历史行业未核实'],context:{},baseline:{forecasts:[]}},
    report:{code:'000807',data_hash:'bundle1',status:'complete',model:'configured',generated_at:'2026-10-16T10:05:00+08:00',anchor_date:'2026-10-15',reference_price:20,history_binding:binding,
      calibrated:false,calls:6,extraction_calls:0,expected_calls:6,cached:false,roles:[{role:'fundamentals_analyst',label:'业绩与估值',status:'ok',claims:[{text:'现金流仍需跟踪',sources:['F1']}]}],evidence:[],limitations:['研究估计，尚未校准'],
      forecasts:[{horizon_sessions:20,scenario:'base',low:21,high:23,conditions:['趋势与业绩保持'],sources:['P1','F1'],basis_ids:['B20'],derivation:'参考区间内的业绩情景'}],
      plans:[{horizon_sessions:20,strategy_kind:'trend_pullback',status:'conditional',entry_low:19,entry_high:20,stop_reference:18,
        second_entry:{low:19,high:19.5,conditions:['回踩确认'],invalidation:['跌破支撑']},targets:[25,26],conditions:['量价确认'],invalidation:['趋势破坏'],
        valid_until:'2026-10-20',sources:['P1','F1'],basis_ids:['B20'],derivation:'有依据的风险计划',reward_risk:2.5,min_reward_risk:2,rejection_reasons:[]} ]}};
}
