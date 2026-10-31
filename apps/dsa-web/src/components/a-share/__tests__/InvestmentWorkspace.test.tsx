import { act,cleanup,fireEvent,render,screen,within } from '@testing-library/react';
import { vi,it,expect } from 'vitest';
import InvestmentWorkspace from '../InvestmentWorkspace';
import apiClient from '../../../api';
import { outlookFixture } from './outlookFixture';
import { unavailableLive,liveFixture } from './liveFixture';
import { outlookHistory } from './outlookFixture';
vi.mock('../../../api',()=>({default:{get:vi.fn(),post:vi.fn(),put:vi.fn()}}));
it('shows noncandidates with history in the same workspace without automatic research',async()=>{
  vi.mocked(apiClient.get).mockImplementation(async url=>({data:url?.endsWith('/live')?unavailableLive('600001'):url?.endsWith('/outlook')?{...outlookFixture('600001'),status:'insufficient',forecasts:[]}:url?.endsWith('/stocks')?{items:[{code:'600001',name:'非候选股票',source:'fixture',quote:{price:12,change:.02},industries:[],concepts:[]}],total:1,page:1,page_size:50}:url?.includes('/history')?{code:'600001',items:[{date:'2026-10-09',open:12,high:13,low:11,close:12}],adjust:'qfq',state:'ready',actual_end:'2026-10-09',limitations:[]}:url?.includes('/scenarios')?{status:'insufficient',trade_levels:null,forecasts:[]}:url?.includes('/sectors')?{items:[],classification:'eastmoney-industry'}:url?.includes('/jobs')?{counts:{},paused:false,coverage:{catalog_total:1,valid:0,excluded:0,failed:0,unverified:1,pending:0,state:'complete_with_gaps'}}:{code:'600001',name:'非候选股票',quote:null,industries:[],concepts:[]}}));
  const board={settings:{mode:'free',watchlist:[],research_enabled:false},report:null,research:[],events:[],holdings:[]};
  render(<InvestmentWorkspace board={board as never} selectedCode="600001" onSelectStock={()=>{}} onWatchlist={()=>{}} onResearch={()=>{}}/>);
  expect(await screen.findByRole('region',{name:'股票研究详情'})).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText('MA5'));
  expect(apiClient.post).not.toHaveBeenCalled();
  expect(screen.getByLabelText('行业筛选')).toBeInTheDocument();expect(screen.getByLabelText('概念筛选')).toBeInTheDocument();
});
it('retains the selected original strategy when a stock has two rule candidates',async()=>{
  vi.mocked(apiClient.get).mockImplementation(async url=>({data:url?.endsWith('/live')?unavailableLive('600001'):url?.endsWith('/outlook')?{...outlookFixture('600001'),status:'insufficient',forecasts:[]}:url?.includes('/history')?{code:'600001',items:[],adjust:'qfq',state:'partial',limitations:[]}:url?.includes('/scenarios')?{status:'insufficient',trade_levels:null,forecasts:[]}:url?.includes('/sectors')?{items:[]}:url?.includes('/jobs')?{counts:{},paused:false}:{code:'600001',name:'同股双规则',industries:[],concepts:[],quote:null,items:[],total:0}}));
  const shared={code:'600001',name:'同股双规则',r20:.1,r60:.2,atr:.5,high:20,source:'fixture',valid_date:'2026-10-12',plan:{entry:20,quantity:100,stop:19,reasons:[]}};
  const board={settings:{mode:'free',watchlist:[],research_enabled:false},report:{candidates:[{...shared,strategy:'trend_v1',score:90},{...shared,strategy:'sector_trend_v1',score:75}]},research:[],events:[],holdings:[]};
  render(<InvestmentWorkspace board={board as never} selectedCode="600001" selectedStrategy="sector_trend_v1" onSelectStock={()=>{}} onWatchlist={()=>{}} onResearch={()=>{}}/>);
  expect(await screen.findByText(/原规则计划 · sector_trend_v1/)).toBeInTheDocument();
  expect(screen.getByText(/得分 75/)).toBeInTheDocument();
});

it('refreshes the selected stock detail and local list together after a manual price refresh',async()=>{
  vi.useFakeTimers();vi.setSystemTime(new Date('2026-10-14T06:00:00Z'));vi.clearAllMocks();
  try{
    let refreshed=false;
    const stock=()=>({code:'600000',name:'列表联动股',source:'tushare/daily',quote:{price:refreshed?27.5:25,change:refreshed?null:.02,source:'tushare/daily',fetched_at:refreshed?'2026-10-14T14:01:00+08:00':'2026-10-09T15:00:00+08:00'},industries:[],concepts:[]});
    vi.mocked(apiClient.get).mockImplementation(async(url,config)=>({data:url?.endsWith('/live')?unavailableLive():url?.endsWith('/outlook')?outlookFixture():url?.endsWith('/stocks')?{items:[stock()],total:1,page:1,page_size:50}:url?.includes('/market/stocks/')&&url.endsWith('/history')?outlookHistory(config?.params?.adjust||'qfq'):url?.endsWith('/scenarios')?{status:'insufficient',trade_levels:null,forecasts:[]}:url?.includes('/sectors')?{items:[],classification:'fixture'}:url?.endsWith('/jobs')?{counts:{},paused:false,coverage:{catalog_total:1,valid:1,state:'complete'}}:url?.includes('/api/v1/history')?{items:[],total:0,page:1,limit:1}:stock()}));
    vi.mocked(apiClient.post).mockImplementation(async()=>{refreshed=true;return {data:{...liveFixture(),quote:{...liveFixture().quote!,change:null}}};});
    const board={settings:{mode:'free',watchlist:[],research_enabled:false},report:null,research:[],events:[],holdings:[]};
    const {container}=render(<InvestmentWorkspace board={board as never} selectedCode="600000" onSelectStock={()=>{}} onWatchlist={()=>{}} onResearch={()=>{}}/>);
    await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
    expect(within(screen.getByRole('button',{name:'列表联动股 600000'})).getByText('25.00')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:'刷新最新行情'}));
    await act(async()=>{await vi.advanceTimersByTimeAsync(0);});
    await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
    expect(container.querySelector('.am-quote')).toHaveTextContent('¥27.50');
    const row=screen.getByRole('button',{name:'列表联动股 600000'});
    expect(within(row).getByText('27.50')).toBeInTheDocument();expect(within(row).getByText('资料不足')).toBeInTheDocument();
    expect(apiClient.post).toHaveBeenCalledTimes(1);
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/a-share/market/stocks/600000/refresh',undefined,{signal:expect.any(AbortSignal)});
    expect(vi.mocked(apiClient.get).mock.calls.filter(call=>call[0]?.endsWith('/stocks'))).toHaveLength(2);
  }finally{cleanup();vi.useRealTimers();}
});

it('removes a deleted watchlist stock immediately after the saved watchlist changes, preserving its filters',async()=>{
  vi.useFakeTimers();vi.clearAllMocks();
  try{
    let watched=true;
    const stock={code:'600000',name:'测试自选股',source:'fixture',quote:null,industries:[],concepts:[]};
    vi.mocked(apiClient.get).mockImplementation(async(url,config)=>({data:
      url?.endsWith('/stocks')?{items:config?.params?.scope==='watchlist'&&!watched?[]:[stock],total:watched?1:0,page:1,page_size:50}:
      url?.endsWith('/live')?unavailableLive():url?.endsWith('/outlook')?outlookFixture():
      url?.endsWith('/integrated-research')?{code:'600000',status:'missing',bundle:null,report:null,task:null,progress:null,message:'尚无综合研究',demo:false}:
      url?.includes('/market/stocks/')&&url.endsWith('/history')?outlookHistory(config?.params?.adjust||'qfq'):
      url?.endsWith('/scenarios')?{status:'insufficient',trade_levels:null,forecasts:[]}:
      url?.endsWith('/sectors')?{items:[],classification:'fixture'}:url?.endsWith('/jobs')?{counts:{},paused:false}:
      url?.includes('/api/v1/history')?{items:[],total:0,page:1,limit:1}:stock}));
    const board={settings:{mode:'free',watchlist:['600000'],research_enabled:false},report:null,research:[],events:[],holdings:[]};
    const props={selectedCode:'600000',onSelectStock:()=>{},onWatchlist:()=>{watched=false;},onResearch:()=>{}};
    const {rerender}=render(<InvestmentWorkspace {...props} board={board as never}/>);
    fireEvent.click(screen.getByRole('button',{name:'自选股票'}));
    fireEvent.change(screen.getByLabelText('搜索股票'),{target:{value:'测试'}});
    fireEvent.change(screen.getByLabelText('股票市场'),{target:{value:'main'}});
    fireEvent.change(screen.getByLabelText('股票排序'),{target:{value:'name'}});
    await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
    expect(screen.getByRole('button',{name:'测试自选股 600000'})).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:'加入 / 移出自选'}));
    rerender(<InvestmentWorkspace {...props} board={{...board,settings:{...board.settings,watchlist:[]}} as never}/>);
    await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
    expect(screen.queryByRole('button',{name:'测试自选股 600000'})).not.toBeInTheDocument();
    expect(screen.getByLabelText('搜索股票')).toHaveValue('测试');
    expect(screen.getByLabelText('股票市场')).toHaveValue('main');
    expect(screen.getByLabelText('股票排序')).toHaveValue('name');
    expect(screen.getByRole('button',{name:'自选股票'})).toHaveAttribute('aria-pressed','true');
    expect(screen.getByRole('region',{name:'股票研究详情'})).toBeInTheDocument();
  }finally{cleanup();vi.useRealTimers();}
});

it('refreshes industry and concept options after first load and keeps the selected filter',async()=>{
  vi.useFakeTimers();vi.clearAllMocks();
  try{
    let expanded=false;
    const industry={sector_id:'em:industry:BK1586',name:'软饮料',kind:'industry'};
    const concept={sector_id:'em:concept:BK0800',name:'人工智能',kind:'concept'};
    vi.mocked(apiClient.get).mockImplementation(async(url,config)=>({data:
      url?.endsWith('/sectors')?{items:config?.params?.kind==='industry'?[industry,...(expanded?[{...industry,sector_id:'em:industry:BK1283',name:'银行'}]:[])]:[concept]}:
      url?.endsWith('/members')?{items:[],total:0,page:1,page_size:1,membership:{codes:['000848'],version:'v1',state:'ready'}}:
      url?.endsWith('/jobs')?{counts:{},paused:false}:{items:[],total:0,page:1,page_size:50}}));
    const board={settings:{mode:'free',watchlist:[],research_enabled:false},report:null,research:[],events:[],holdings:[]};
    render(<InvestmentWorkspace board={board as never} selectedCode="" onSelectStock={()=>{}} onWatchlist={()=>{}} onResearch={()=>{}}/>);
    await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
    fireEvent.change(screen.getByLabelText('行业筛选'),{target:{value:industry.sector_id}});
    expanded=true;
    await act(async()=>{await vi.advanceTimersByTimeAsync(5*60*1000);});
    expect(within(screen.getByLabelText('行业筛选')).getByRole('option',{name:'银行'})).toBeInTheDocument();
    expect(screen.getByLabelText('行业筛选')).toHaveValue(industry.sector_id);
    expect(apiClient.post).not.toHaveBeenCalled();
  }finally{cleanup();vi.useRealTimers();}
});
