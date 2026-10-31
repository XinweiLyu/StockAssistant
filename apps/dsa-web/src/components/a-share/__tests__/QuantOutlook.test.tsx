import { act, fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import StockDetail from '../StockDetail';
import { aShareMarketApi } from '../../../api/aShareMarket';
import { historyApi } from '../../../api/history';
import { outlookFixture, outlookHistory } from './outlookFixture';
import { unavailableLive } from './liveFixture';
import type { QuantOutlook } from '../../../types/aShareMarket';
vi.mock('../../../api/aShareMarket',()=>({aShareMarketApi:{getValue:vi.fn(async(code:string)=>({code,status:"missing"})),stock:vi.fn(),history:vi.fn(),scenarios:vi.fn(),outlook:vi.fn(),live:vi.fn(),refreshPrice:vi.fn(),integrated:vi.fn(),prepareResearch:vi.fn(),generateIntegrated:vi.fn()}}));
vi.mock('../../../api/history',()=>({historyApi:{getList:vi.fn(),getDetail:vi.fn()}}));
beforeEach(()=>{
  vi.resetAllMocks();vi.mocked(aShareMarketApi.integrated).mockImplementation(async code=>({code,status:"missing",bundle:null,report:null,demo:false,progress:null,task:null,message:"尚无综合研究"}));vi.mocked(aShareMarketApi.live).mockImplementation(async code=>unavailableLive(code));
  vi.mocked(aShareMarketApi.stock).mockImplementation(async code=>({code,name:code,industries:[],concepts:[],source:'fixture',quote:null}));
  vi.mocked(aShareMarketApi.history).mockImplementation(async(code,_start,_end,adjust)=>outlookHistory(adjust,code));
  vi.mocked(aShareMarketApi.scenarios).mockResolvedValue({status:'insufficient',trade_levels:null,forecasts:[]});
  vi.mocked(aShareMarketApi.outlook).mockImplementation(async code=>outlookFixture(code));
  vi.mocked(historyApi.getList).mockResolvedValue({items:[],total:0,page:1,limit:1});
});
afterEach(()=>{cleanup();vi.useRealTimers();});
it('defaults to20 sessions, switches5/60 without model calls and refetches for the ratio',async()=>{
  const research=vi.fn();const {container}=render(<StockDetail code="600000" onResearch={research} onWatchlist={()=>{}}/>);
  expect(screen.getByLabelText('预测期限')).toHaveValue('20');
  await waitFor(()=>expect(container.querySelector('[data-outlook-horizon="20"]')).toBeInTheDocument());
  fireEvent.change(screen.getByLabelText('预测期限'),{target:{value:'5'}});
  expect(container.querySelector('[data-outlook-horizon="5"]')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('预测期限'),{target:{value:'60'}});
  expect(container.querySelector('[data-outlook-horizon="60"]')).toBeInTheDocument();
  expect(aShareMarketApi.outlook).toHaveBeenCalledTimes(1);
  fireEvent.change(screen.getByLabelText('最低盈亏比'),{target:{value:'3'}});
  await waitFor(()=>expect(aShareMarketApi.outlook).toHaveBeenLastCalledWith('600000',3,expect.any(AbortSignal),false));
  expect(research).not.toHaveBeenCalled();
  expect(screen.getByLabelText('MA120')).toBeInTheDocument();expect(screen.getByLabelText('MA250')).toBeInTheDocument();
  expect(screen.getByText(/最近完整周.*2026-10-02/)).toBeInTheDocument();
});
it('shows validation, source/time and safe event evidence, distinguishes unknown dates from trading days',async()=>{
  const data=outlookFixture();data.events.push({...data.events[0],id:'e2',title:'不安全地址',url:'javascript:alert(1)'});
  vi.mocked(aShareMarketApi.outlook).mockResolvedValue(data);
  render(<StockDetail code="600000" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  expect(await screen.findByText(/滚动验证.*20.*75.0%/)).toBeInTheDocument();
  expect(screen.getByText(/名义覆盖.*80.0%.*不等于/)).toBeInTheDocument();
  expect(screen.getByText(/连接线仅为显示插值/)).toBeInTheDocument();
  expect(screen.getAllByText(/未来日历未知/).length).toBeGreaterThan(0);
  expect(screen.getByRole('link',{name:/公司公告/})).toHaveAttribute('href','https://example.com/notice');
  expect(screen.queryByRole('link',{name:/不安全地址/})).not.toBeInTheDocument();
  expect(screen.getAllByText(/首次获取.*2026-10-09T16:00/)).toHaveLength(2);
  expect(screen.getByRole('heading',{name:'AI 价位与情景'})).toBeInTheDocument();
  expect(screen.getByLabelText('已保存的首页分析')).toBeInTheDocument();
});
it('discards old results immediately on code or ratio switches and ignores aborted replies',async()=>{
  let resolve!:(value:QuantOutlook)=>void;let oldSignal:AbortSignal|undefined;
  vi.mocked(aShareMarketApi.outlook).mockImplementation((code,_ratio,signal)=>{if(code==='600000'){oldSignal=signal;return new Promise(r=>{resolve=r;});}return Promise.resolve(outlookFixture(code));});
  const {rerender,container}=render(<StockDetail code="600000" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  expect(screen.getByText(/正在查询数值研究/)).toBeInTheDocument();
  rerender(<StockDetail code="600001" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  expect(oldSignal?.aborted).toBe(true);
  await waitFor(()=>expect(container.querySelector('[data-outlook-code="600001"]')).toBeInTheDocument());
  await act(async()=>resolve(outlookFixture('600000')));
  expect(container.querySelector('[data-outlook-code="600000"]')).not.toBeInTheDocument();
  vi.mocked(aShareMarketApi.outlook).mockImplementation(()=>new Promise(()=>{}));
  fireEvent.change(screen.getByLabelText('最低盈亏比'),{target:{value:'4'}});
  expect(container.querySelector('[data-outlook-code]')).not.toBeInTheDocument();
  expect(screen.getByText(/正在查询数值研究/)).toBeInTheDocument();
});
it('rechecks pending history and clears the forecast after a source failure',async()=>{
  vi.useFakeTimers();
  vi.mocked(aShareMarketApi.outlook).mockResolvedValueOnce({...outlookFixture(),status:'pending',forecasts:[]}).mockRejectedValueOnce(new Error('行情源获取失败'));
  const {container}=render(<StockDetail code="600000" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  await act(async()=>{await vi.advanceTimersByTimeAsync(0);});
  expect(screen.getByText(/历史补齐中/)).toBeInTheDocument();expect(container.querySelector('[data-outlook-code]')).not.toBeInTheDocument();
  await act(async()=>{await vi.advanceTimersByTimeAsync(4000);});
  expect(screen.getByRole('alert')).toHaveTextContent('行情源获取失败');
  expect(container.querySelector('[data-outlook-code]')).not.toBeInTheDocument();
});
it.each(['source','anchor','basis','code'] as const)('blocks the numerical chart fan for %s mismatches',async mismatch=>{
  const data=outlookFixture();
  if(mismatch==='source')data.source='other';if(mismatch==='anchor')data.qfq_anchor=21;if(mismatch==='basis')data.adjustment_basis='older';if(mismatch==='code')data.code='600001';
  vi.mocked(aShareMarketApi.outlook).mockResolvedValue(data);
  const {container}=render(<StockDetail code="600000" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  if(mismatch==='code')await screen.findByRole('alert');else await screen.findByText(/来源与时间证据/);
  expect(container.querySelector('[data-outlook-code]')).not.toBeInTheDocument();
});
it('removes numerical fan when the visible history moves before the latest anchor',async()=>{
  vi.mocked(aShareMarketApi.history).mockImplementation(async(code,_start,_end,adjust)=>{const h=outlookHistory(adjust,code);return {...h,items:[{...h.items[0],date:'2026-10-08'},...h.items]};});
  const {container}=render(<StockDetail code="600000" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  await waitFor(()=>expect(container.querySelector('[data-outlook-code]')).toBeInTheDocument());
  fireEvent.change(screen.getByLabelText('历史窗口位置'),{target:{value:'1'}});
  expect(container.querySelector('[data-outlook-code]')).not.toBeInTheDocument();
  expect(screen.getByText(/当前窗口不含数值研究锚点/)).toBeInTheDocument();
});

it('shows verified events and conditional plan prices on the matched chart without replacing AI layers',async()=>{
  vi.mocked(aShareMarketApi.scenarios).mockResolvedValue({status:'ready',context:{code:'600000',anchor_date:'2026-10-09',reference_price:25,currency:'CNY',price_basis:'raw',data_hash:'h1',adjustment_basis:'tushare:2026-10-09'},trade_levels:{horizon_sessions:20,entry_low:25,entry_high:26,stop_reference:23,sell_low:29,sell_high:31,conditions:['独立AI观点'],invalidation:['趋势失效'],sources:['P1']},forecasts:[]});
  const {container}=render(<StockDetail code="600000" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  await waitFor(()=>expect(container.querySelector('[data-level-id="quant-entry"]')).toBeInTheDocument());
  expect(container.querySelector('[data-level-id="quant-entry"] title')).toHaveTextContent('¥19.20');
  expect(container.querySelector('[data-level-id="quant-stop"] text')).not.toHaveTextContent('超出图轴');
  expect(container.querySelector('[data-quant-event="e1"] title')).toHaveTextContent('公司公告');
  expect(container.querySelector('[data-level-id="ai-entry"]')).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText('数值观察价位'));
  expect(container.querySelector('[data-level-id="quant-entry"]')).not.toBeInTheDocument();
  expect(container.querySelector('[data-level-id="ai-entry"]')).toBeInTheDocument();
  expect(container.querySelector('[data-outlook-code]')).toBeInTheDocument();
});
it('treats a below-threshold conditional response as observation without actionable price layers',async()=>{
  const data=outlookFixture();data.plan.reward_risk=1.5;
  vi.mocked(aShareMarketApi.outlook).mockResolvedValue(data);
  const {container}=render(<StockDetail code="600000" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  expect(await screen.findByRole('heading',{name:/仅观察 · 条件未齐备/})).toBeInTheDocument();
  expect(container.querySelector('[data-level-id="quant-entry"]')).not.toBeInTheDocument();
});

it('sends refresh only for the explicit retry, and never carries it to ratio or stock switches',async()=>{
  const {rerender}=render(<StockDetail code="600000" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  await screen.findByText(/来源与时间证据/);
  fireEvent.click(screen.getByRole('button',{name:'更新数值研究'}));
  await waitFor(()=>expect(aShareMarketApi.outlook).toHaveBeenLastCalledWith('600000',2,expect.any(AbortSignal),true));
  fireEvent.change(screen.getByLabelText('最低盈亏比'),{target:{value:'3'}});
  await waitFor(()=>expect(aShareMarketApi.outlook).toHaveBeenLastCalledWith('600000',3,expect.any(AbortSignal),false));
  rerender(<StockDetail code="600001" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  await waitFor(()=>expect(aShareMarketApi.outlook).toHaveBeenLastCalledWith('600001',3,expect.any(AbortSignal),false));
});
it('refreshes a ready outlook after five minutes and retains same-stock evidence with a transient error notice',async()=>{
  vi.useFakeTimers();
  vi.mocked(aShareMarketApi.outlook).mockResolvedValueOnce(outlookFixture()).mockRejectedValueOnce(new Error('临时连接中断')).mockResolvedValue(outlookFixture());
  const {container}=render(<StockDetail code="600000" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  await act(async()=>{await vi.advanceTimersByTimeAsync(0);});
  expect(container.querySelector('[data-outlook-code="600000"]')).toBeInTheDocument();
  await act(async()=>{await vi.advanceTimersByTimeAsync(5*60*1000);});
  expect(aShareMarketApi.outlook).toHaveBeenCalledTimes(2);
  expect(screen.getByRole('alert')).toHaveTextContent('临时连接中断');
  expect(container.querySelector('[data-outlook-code="600000"]')).toBeInTheDocument();
  await act(async()=>{fireEvent(window,new Event('focus'));});
  expect(aShareMarketApi.outlook).toHaveBeenCalledTimes(3);
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
it('reports incomplete API responses without crashing the existing stock detail',async()=>{
  vi.mocked(aShareMarketApi.outlook).mockResolvedValue({code:'600000',status:'ready'} as QuantOutlook);
  render(<StockDetail code="600000" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  expect(await screen.findByRole('alert')).toHaveTextContent('数值研究数据结构不完整');
  expect(screen.getByRole('heading',{name:'AI 价位与情景'})).toBeInTheDocument();
});

it('keeps independent AI price layers available when the numerical source fails',async()=>{
  vi.mocked(aShareMarketApi.outlook).mockRejectedValue(new Error('数值资料暂不可用'));
  vi.mocked(aShareMarketApi.scenarios).mockResolvedValue({status:'ready',context:{code:'600000',anchor_date:'2026-10-09',reference_price:25,currency:'CNY',price_basis:'raw',data_hash:'h1',adjustment_basis:'tushare:2026-10-09'},trade_levels:{horizon_sessions:20,entry_low:25,entry_high:26,stop_reference:23,sell_low:29,sell_high:31,conditions:['独立AI观点'],invalidation:['趋势失效'],sources:['P1']},forecasts:[]});
  const {container}=render(<StockDetail code="600000" onResearch={()=>{}} onWatchlist={()=>{}}/>);
  await waitFor(()=>expect(container.querySelector('[data-level-id="ai-entry"]')).toBeInTheDocument());
  expect(screen.getByRole('alert')).toHaveTextContent('数值资料暂不可用');
  expect(container.querySelector('[data-outlook-code]')).not.toBeInTheDocument();
  expect(screen.getByLabelText('已保存的首页分析')).toBeInTheDocument();
});
