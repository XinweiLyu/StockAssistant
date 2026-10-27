import { render,screen,waitFor,fireEvent } from '@testing-library/react';
import { vi,it,expect,beforeEach,afterEach,describe } from 'vitest';
import StockDetail from '../StockDetail';
import { aShareMarketApi } from '../../../api/aShareMarket';
import { historyApi } from '../../../api/history';
import { strategyPrice } from '../savedAnalysis';
import { outlookFixture } from './outlookFixture';
import { unavailableLive } from './liveFixture';
import { integratedFixture,integratedHistory } from './integratedFixture';
import type { Candidate } from '../../../types/aShare';
vi.mock('../../../api/aShareMarket',()=>({aShareMarketApi:{stock:vi.fn(),history:vi.fn(),scenarios:vi.fn(),outlook:vi.fn(),live:vi.fn(),refreshPrice:vi.fn(),integrated:vi.fn(),prepareResearch:vi.fn(),generateIntegrated:vi.fn()}}));
vi.mock('../../../api/history',()=>({historyApi:{getList:vi.fn(),getDetail:vi.fn()}}));
const page=(code:string,close:number)=>({code,state:'ready',items:[{date:'2026-10-09',open:close,high:close+1,low:close-1,close}],source:'fixture',adjust:'qfq' as const,adjustment_basis:'b1',requested_start:'2026-01-01',requested_end:'2026-10-09',actual_end:'2026-10-09',limitations:[]});
beforeEach(()=>{vi.resetAllMocks();vi.mocked(aShareMarketApi.integrated).mockImplementation(async code=>({code,status:"missing",bundle:null,report:null,demo:false,progress:null,task:null,message:"尚无综合研究"}));vi.mocked(aShareMarketApi.live).mockImplementation(async code=>unavailableLive(code));vi.mocked(aShareMarketApi.outlook).mockResolvedValue({...outlookFixture(),status:'insufficient',forecasts:[]});vi.mocked(aShareMarketApi.stock).mockImplementation(async code=>({code,name:code,industries:[],concepts:[],source:'fixture',quote:null}));vi.mocked(aShareMarketApi.scenarios).mockResolvedValue({status:'insufficient',trade_levels:null,forecasts:[]});vi.mocked(historyApi.getList).mockResolvedValue({items:[],total:0,page:1,limit:1});});
it('shows the latest saved homepage decision and its four prices without generating new AI analysis',async()=>{
  vi.mocked(aShareMarketApi.history).mockImplementation(async(code,_start,_end,adjust)=>({...page(code,25),adjust}));
  vi.mocked(historyApi.getList).mockResolvedValue({items:[{id:7,queryId:'q7',stockCode:'000807.SZ',stockName:'云铝股份',createdAt:'2026-10-12T14:16:00+08:00'}],total:1,page:1,limit:1});
  vi.mocked(historyApi.getDetail).mockResolvedValue({
    meta:{id:7,queryId:'q7',stockCode:'000807.SZ',stockName:'云铝股份',reportType:'detailed',createdAt:'2026-10-12T14:16:00+08:00'},
    summary:{analysisSummary:'趋势偏弱，等待确认',operationAdvice:'减仓',trendPrediction:'看空',sentimentScore:30},
    strategy:{idealBuy:'25.80元（企稳后）',secondaryBuy:'26.30元（站稳均线后）',stopLoss:'25.60元',takeProfit:'26.60元'},
    details:{rawResult:{shortTermOutlook:'短期等待企稳',mediumTermOutlook:'中期观察均线恢复'}},
  } as never);
  render(<StockDetail code="000807" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  await screen.findByText('25.80元（企稳后）');
  expect(screen.getByText('二次买入')).toBeInTheDocument();
  expect(screen.getByText('26.30元（站稳均线后）')).toBeInTheDocument();
  expect(screen.getByText('25.60元')).toBeInTheDocument();
  expect(screen.getByText('26.60元')).toBeInTheDocument();
  expect(screen.getByText('短期等待企稳')).toBeInTheDocument();
  expect(screen.getByText('减仓')).toBeInTheDocument();
  expect(screen.getByLabelText('已保存的首页分析')).toHaveTextContent('2026-10-12 14:16');
  expect(screen.getByText(/历史报告，仅供对照/)).toBeInTheDocument();
  await waitFor(()=>expect(document.querySelector('[data-level-id="report-ideal"]')).toBeInTheDocument());
  expect(document.querySelector('[data-level-id="report-ideal"] line')).toHaveAttribute('stroke-dasharray','5 3');
  expect(document.querySelector('[data-level-id="report-secondary"]')).toBeInTheDocument();
  expect(document.querySelector('[data-level-id="report-stop"]')).toBeInTheDocument();
  expect(document.querySelector('[data-level-id="report-profit"]')).toBeInTheDocument();
});
it('integrates the new forecast and levels below the main chart without starting AI',async()=>{
  vi.mocked(aShareMarketApi.integrated).mockResolvedValue(integratedFixture());
  vi.mocked(aShareMarketApi.history).mockImplementation(async(_code,_start,_end,adjust)=>integratedHistory(adjust));
  const {container}=render(<StockDetail code="000807" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  const region=await screen.findByRole('region',{name:'综合预测与策略'});
  await waitFor(()=>expect(container.querySelector('[data-level-id="integrated-stop"]')).toBeInTheDocument());
  const candle=container.querySelector('svg');
  expect(candle!.compareDocumentPosition(region)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.getByText('¥19.00 – ¥20.00')).toBeInTheDocument();
  expect(aShareMarketApi.generateIntegrated).not.toHaveBeenCalled();
});
it('keeps manual research available after the former daily budget is exhausted',async()=>{
  vi.mocked(aShareMarketApi.history).mockImplementation(async(code,_start,_end,adjust)=>({...page(code,25),adjust}));
  render(<StockDetail code="600831" onResearch={()=>{}} onWatchlist={()=>{}} remainingCalls={0}/>);
  await waitFor(()=>expect(screen.getByRole('button',{name:'生成综合研究与价位'})).toBeEnabled());
  expect(screen.queryByRole('button',{name:'生成研究与价位'})).not.toBeInTheDocument();
  expect(screen.getByText(/手动生成不限每日次数/)).toBeInTheDocument();
  await screen.findByText(/该股没有已保存的首页分析报告/);
});
it('accepts one explicit strategy price and rejects ranges or percentages',()=>{
  expect(strategyPrice('25.80元（仅当企稳）')).toBe(25.8);
  expect(strategyPrice('25.80-26.30元')).toBeNull();
  expect(strategyPrice('上涨5%后买入')).toBeNull();
});
it('refreshes the saved report and chart lines when a newer homepage report appears',async()=>{
  vi.mocked(aShareMarketApi.history).mockImplementation(async(code,_start,_end,adjust)=>({...page(code,25),adjust}));
  let reportId=1;
  vi.mocked(historyApi.getList).mockImplementation(async()=>({items:[{id:reportId,queryId:`q${reportId}`,stockCode:'000807.SZ',createdAt:'2026-10-12T14:16:00+08:00'}],total:1,page:1,limit:1}));
  vi.mocked(historyApi.getDetail).mockImplementation(async id=>({
    meta:{id,queryId:`q${id}`,stockCode:'000807.SZ',stockName:'云铝股份',reportType:'detailed',createdAt:'2026-10-12T14:16:00+08:00'},
    summary:{analysisSummary:'等待确认',operationAdvice:'观察',trendPrediction:'震荡',sentimentScore:50},
    strategy:{idealBuy:id===1?'25.80元':'24.80元'},
  } as never));
  const {container}=render(<StockDetail code="000807" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  await screen.findByText('25.80元');
  reportId=2;
  fireEvent(window,new Event('focus'));
  await screen.findByText('24.80元');
  expect(container.querySelector('[data-level-id="report-ideal"] title')).toHaveTextContent('¥24.80');
});
it('explains why saved decision prices are unavailable for an unanalysed stock',async()=>{
  vi.mocked(aShareMarketApi.history).mockImplementation(async(code,_start,_end,adjust)=>({...page(code,25),adjust}));
  render(<StockDetail code="600831" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  expect(await screen.findByText(/该股没有已保存的首页分析报告/)).toBeInTheDocument();
  expect(screen.queryByText('理想买入')).not.toBeInTheDocument();
});
it('explains missing forecast inputs without blocking manual research',async()=>{
  vi.mocked(aShareMarketApi.history).mockImplementation(async(code,_start,_end,adjust)=>({...page(code,25),adjust}));
  render(<StockDetail code="600831" onResearch={()=>{}} onWatchlist={()=>{}} remainingCalls={1}/>);
  expect(await screen.findByText(/最近120个完整交易日/)).toBeInTheDocument();
  await waitFor(()=>expect(screen.getByRole('button',{name:'生成综合研究与价位'})).toBeEnabled());
  expect(screen.queryByRole('button',{name:'生成研究与价位'})).not.toBeInTheDocument();
});
it('late history cannot replace a newly selected stock and indicators never request research',async()=>{
  let resolve!:(value:ReturnType<typeof page>)=>void;
  vi.mocked(aShareMarketApi.history).mockImplementation(code=>code==='600000'?new Promise(r=>{resolve=r;}):Promise.resolve(page(code,20)));
  const research=vi.fn();const {rerender}=render(<StockDetail code="600000" onResearch={research} onWatchlist={()=>{}} />);
  rerender(<StockDetail code="600001" onResearch={research} onWatchlist={()=>{}} />);
  await screen.findByText(/2026-10-09 · 开 20/);
  resolve(page('600000',10));await waitFor(()=>expect(screen.queryByText(/开 10/)).not.toBeInTheDocument());
  fireEvent.click(screen.getByLabelText('BOLL'));
  expect(research).not.toHaveBeenCalled();
  expect(screen.getByRole('region',{name:'股票研究详情'})).toBeInTheDocument();
});
it('maps same-family Tushare raw and factor-adjusted history to current price layers',async()=>{
  vi.mocked(aShareMarketApi.history).mockImplementation(async(code,_start,_end,adjust)=>({...page(code,adjust==='raw'?20:16),adjust,source:adjust==='raw'?'tushare/daily':'tushare/daily+adj_factor',adjustment_basis:'tushare:2026-10-12'}));
  vi.mocked(aShareMarketApi.scenarios).mockResolvedValue({status:'ready',context:{code:'600000',anchor_date:'2026-10-09',reference_price:20,currency:'CNY',price_basis:'raw',data_hash:'h1',adjustment_basis:'tushare:2026-10-12'},trade_levels:{horizon_sessions:20,entry_low:20,entry_high:21,stop_reference:18,sell_low:24,sell_high:25,conditions:['趋势保持'],invalidation:['趋势破坏'],sources:['P1']},forecasts:[]});
  const {container}=render(<StockDetail code="600000" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  await waitFor(()=>expect(container.querySelector('[data-level-id="ai-entry"]')).toBeInTheDocument());
  fireEvent.click(screen.getByRole('button',{name:/AI 买入观察区间/}));
  expect(container.querySelector('[data-level-id="ai-entry"] line')).toHaveAttribute('stroke-width','2.5');
});

it('places the full chart before saved AI analysis and numerical research',async()=>{
  vi.mocked(aShareMarketApi.history).mockImplementation(async(code,_start,_end,adjust)=>({...page(code,25),adjust}));
  render(<StockDetail code="000807" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  const chart=await screen.findByRole('img',{name:'历史价格与指标'});
  const saved=screen.getByRole('region',{name:'已保存的首页分析'});
  const quant=screen.getByRole('region',{name:'多周期数值研究'});
  expect(chart.compareDocumentPosition(saved)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(chart.compareDocumentPosition(quant)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});


it('has one paid generation entry and preserves old research as read-only history',async()=>{
 vi.mocked(aShareMarketApi.integrated).mockResolvedValue(integratedFixture());
 vi.mocked(aShareMarketApi.generateIntegrated).mockResolvedValue({accepted:true,status:'running'});
 vi.mocked(aShareMarketApi.history).mockImplementation(async(_code,_start,_end,adjust)=>integratedHistory(adjust));
 const legacy=vi.fn();render(<StockDetail code="000807" onResearch={legacy} onWatchlist={()=>{}}/>);
 await screen.findByText(/已完成.*100%/);
 const button=screen.getByRole('button',{name:'生成综合研究与价位'});
 fireEvent.click(button);fireEvent.click(button);
 await waitFor(()=>expect(aShareMarketApi.generateIntegrated).toHaveBeenCalledTimes(1));
 expect(aShareMarketApi.generateIntegrated).toHaveBeenCalledWith('000807',false);
 expect(legacy).not.toHaveBeenCalled();
 expect(screen.getByText('历史AI价位与情景（旧版5/10/20日）')).toBeInTheDocument();
});


it('shows the failed manager beside the empty chart without inventing a forecast fan',async()=>{
 const s=integratedFixture();s.report!.status='partial';s.report!.forecasts=[];s.report!.plans=[];
 s.report!.roles=[{role:'research_manager',label:'综合经理',status:'failed',claims:[],message:'模型请求未完成：CalledProcessError'}];
 vi.mocked(aShareMarketApi.integrated).mockResolvedValue(s);
 vi.mocked(aShareMarketApi.history).mockImplementation(async(_code,_start,_end,adjust)=>integratedHistory(adjust));
 const {container}=render(<StockDetail code="000807" onResearch={()=>{}} onWatchlist={()=>{}}/>);
 await waitFor(()=>expect(screen.getByRole('region',{name:'K线与指标'})).toHaveTextContent('综合经理'));
 expect(screen.getByRole('region',{name:'K线与指标'})).toHaveTextContent('未生成');
 expect(container.querySelector('[data-integrated-code]')).not.toBeInTheDocument();
});

it('explains that earlier nodes remain when the selected terminal horizon is missing',async()=>{
  const state=integratedFixture();state.report!.plans=[];
  vi.mocked(aShareMarketApi.integrated).mockResolvedValue(state);
  vi.mocked(aShareMarketApi.history).mockImplementation(async(_code,_start,_end,adjust)=>integratedHistory(adjust));
  const {container}=render(<StockDetail code="000807" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  await waitFor(()=>expect(container.querySelector('[data-integrated-code]')).toBeInTheDocument());
  fireEvent.change(screen.getByLabelText('综合研究期限'),{target:{value:'60'}});
  await waitFor(()=>expect(container.querySelector('[data-integrated-code]')).toBeInTheDocument());
  expect(screen.getByRole('region',{name:'K线与指标'})).toHaveTextContent(/60.*较早期限.*保留/);
  expect(container.querySelector('[data-sessions="20"]')).toBeInTheDocument();
  expect(container.querySelector('[data-sessions="60"]')).not.toBeInTheDocument();
  expect(screen.queryByText(/当前无区间线可绘制/)).not.toBeInTheDocument();
});

describe('rule price history binding',()=>{
  const currentCandidate=()=>({code:'600000',name:'测试股票',sector:'test',strategy:'trend_v1',score:80,
    r20:.1,r60:.2,v20:.03,close:25,high:26,atr:1,sma20:24,sma60:23,as_of:'2026-10-09',
    valid_date:'2026-10-12',source:'fixture',check:{status:'observe',reasons:[]},
    plan:{entry:26,quantity:100,stop:24,reasons:[]}});
  beforeEach(()=>{
    vi.useFakeTimers({toFake:['Date']});
    vi.setSystemTime(new Date('2026-10-12T10:00:00+08:00'));
    vi.mocked(aShareMarketApi.history).mockImplementation(async(code,_start,_end,adjust)=>({...page(code,adjust==='raw'?25:20),adjust}));
  });
  afterEach(()=>vi.useRealTimers());

  it('keeps the current same-stock rule mapped to its own complete-day anchor',async()=>{
    const {container}=render(<StockDetail code="600000" candidate={currentCandidate()} onResearch={()=>{}} onWatchlist={()=>{}}/>);
    await screen.findByRole('img',{name:'历史价格与指标'});
    const level=container.querySelector('[data-level-id="rule-entry"]');
    expect(level).toBeInTheDocument();
    expect(level!.querySelector('title')).toHaveTextContent('¥20.80');
  });

  it.each([
    ['expired status',{check:{status:'expired',reasons:['条件已失效']}},/已失效/],
    ['blocked status',{check:{status:'blocked',reasons:['已核实重大风险']}},/风险阻止/],
    ['past validity date',{valid_date:'2026-10-09'},/已失效/],
    ['future validity date',{valid_date:'2026-10-13'},/尚未到有效日/],
    ['another stock',{code:'600001'},/证券不匹配/],
    ['missing research date',{as_of:undefined},/历史参考/],
  ] as const)('preserves %s plans as records without current rule lines',async(_label,changes,reason)=>{
    const candidate={...currentCandidate(),...changes};
    const {container}=render(<StockDetail code="600000" candidate={candidate as Candidate} onResearch={()=>{}} onWatchlist={()=>{}}/>);
    await screen.findByRole('img',{name:'历史价格与指标'});
    expect(container.querySelector('[data-level-id^="rule-"]')).not.toBeInTheDocument();
    const card=container.querySelector('.am-rule-plan');
    expect(card).toBeInTheDocument();
    expect(card).toHaveTextContent('26');
    expect(card).toHaveTextContent(reason);
  });

  it('does not move an old plan to a newer complete day or a manually selected historical end date',async()=>{
    vi.mocked(aShareMarketApi.history).mockImplementation(async(code,_start,end,adjust)=>({
      ...page(code,adjust==='raw'?25:20),adjust,actual_end:end==='2026-10-08'?'2026-10-08':'2026-10-12',
      items:[{...page(code,adjust==='raw'?25:20).items[0],date:end==='2026-10-08'?'2026-10-08':'2026-10-12'}],
    }));
    const {container}=render(<StockDetail code="600000" candidate={currentCandidate()} onResearch={()=>{}} onWatchlist={()=>{}}/>);
    await screen.findByText(/2026-10-12 · 开 20/);
    expect(container.querySelector('[data-level-id^="rule-"]')).not.toBeInTheDocument();
    expect(container.querySelector('.am-rule-plan')).toHaveTextContent(/历史参考/);
    fireEvent.change(screen.getByLabelText('截止日期'),{target:{value:'2026-10-08'}});
    await screen.findByText(/2026-10-08 · 开 20/);
    expect(container.querySelector('[data-level-id^="rule-"]')).not.toBeInTheDocument();
    expect(container.querySelector('.am-rule-plan')).toHaveTextContent('2026-10-09');
  });
});
