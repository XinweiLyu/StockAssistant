import { useState } from 'react';
import { render,screen,fireEvent,waitFor,within } from '@testing-library/react';
import { beforeEach,expect,it,vi } from 'vitest';
import InvestmentWorkspace from '../InvestmentWorkspace';
import apiClient from '../../../api';
import { outlookFixture,outlookHistory } from './outlookFixture';
import { unavailableLive } from './liveFixture';
import type { AssistantBoard } from '../../../types/aShare';

vi.mock('../../../api',()=>({default:{get:vi.fn(),post:vi.fn(),put:vi.fn()}}));
const industry={sector_id:'em:industry:BK001',code:'BK001',name:'铝行业',kind:'industry',classification:'eastmoney-industry',source:'fixture',change:.02,fetched_at:'2026-10-16'};
const concept={...industry,sector_id:'em:concept:BK002',code:'BK002',name:'新能源概念',kind:'concept',classification:'eastmoney-concept'};
const stock=(code='600000')=>({code,name:code==='000807'?'云铝股份':'测试股票',source:'fixture',quote:null,industries:[],concepts:[]});
const board={settings:{mode:'free',watchlist:[],research_enabled:false},report:null,research:[],events:[],holdings:[]} as unknown as AssistantBoard;
function Workspace(){
  const [code,setCode]=useState('600000');
  return <InvestmentWorkspace board={board} selectedCode={code} onSelectStock={setCode} onWatchlist={()=>{}} onResearch={()=>{}}/>;
}
beforeEach(()=>{
  vi.clearAllMocks();
  vi.mocked(apiClient.get).mockImplementation(async(url,config)=>{
    if(url?.endsWith('/sectors'))return {data:{items:[config?.params?.kind==='concept'?concept:industry],classification:'fixture'}};
    if(url?.endsWith('/members'))return {data:{items:[stock('000807')],total:1,page:1,page_size:20,membership:{codes:['000807'],version:'v1',state:'ready'}}};
    if(url?.endsWith('/jobs'))return {data:{counts:{},paused:false,coverage:{catalog_total:1,state:'complete'}}};
    if(url?.endsWith('/stocks'))return {data:{items:[stock()],total:1,page:1,page_size:50}};
    const code=url?.includes('/stocks/000807')?'000807':'600000';
    if(url?.endsWith('/live'))return {data:unavailableLive(code)};
    if(url?.endsWith('/outlook'))return {data:outlookFixture(code)};
    if(url?.endsWith('/history')&&url.includes('/market/stocks/'))return {data:outlookHistory(config?.params?.adjust||'qfq',code)};
    if(url?.endsWith('/scenarios'))return {data:{status:'insufficient',trade_levels:null,forecasts:[]}};
    if(url?.includes('/api/v1/history'))return {data:{items:[],total:0,page:1,limit:1}};
    return {data:stock(code)};
  });
});

it('keeps board browsing separate and opens a clicked member in the stock workspace',async()=>{
  render(<Workspace/>);
  expect(await screen.findByRole('heading',{name:'测试股票'})).toBeInTheDocument();
  expect(screen.queryByRole('heading',{name:'行业与概念板块'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('tab',{name:'行业与概念'}));
  expect(screen.queryByRole('region',{name:'股票研究详情'})).not.toBeInTheDocument();
  fireEvent.click(await screen.findByRole('button',{name:'铝行业 2.00%'}));
  const members=await screen.findByRole('table',{name:'板块成分股'});
  fireEvent.click(within(members).getByRole('button',{name:'查看云铝股份 000807'}));
  expect(screen.getByRole('tab',{name:'个股行情'})).toHaveAttribute('aria-selected','true');
  expect(await screen.findByRole('heading',{name:'云铝股份'})).toBeInTheDocument();
  expect(screen.getByLabelText('行业筛选')).toHaveValue(industry.sector_id);
  expect(screen.queryByRole('region',{name:'板块详情'})).not.toBeInTheDocument();
  expect(apiClient.post).not.toHaveBeenCalled();
});

it('preserves chart settings when visiting boards and returning to the same stock',async()=>{
  render(<Workspace/>);
  await screen.findByRole('heading',{name:'测试股票'});
  fireEvent.change(screen.getByLabelText('价格口径'),{target:{value:'raw'}});
  fireEvent.change(screen.getByLabelText('起始日期'),{target:{value:'2026-01-05'}});
  fireEvent.click(screen.getByRole('tab',{name:'行业与概念'}));
  fireEvent.click(screen.getByRole('tab',{name:'个股行情'}));
  expect(screen.getByLabelText('价格口径')).toHaveValue('raw');
  expect(screen.getByLabelText('起始日期')).toHaveValue('2026-01-05');
});

it('replaces a previously chosen concept when opening an industry member',async()=>{
  render(<Workspace/>);
  await screen.findByRole('option',{name:concept.name});
  fireEvent.change(screen.getByLabelText('概念筛选'),{target:{value:concept.sector_id}});
  fireEvent.click(screen.getByRole('tab',{name:'行业与概念'}));
  fireEvent.click(await screen.findByRole('button',{name:'铝行业 2.00%'}));
  fireEvent.click(await screen.findByRole('button',{name:'查看云铝股份 000807'}));
  expect(screen.getByLabelText('概念筛选')).toHaveValue('');
  expect(screen.getByLabelText('行业筛选')).toHaveValue(industry.sector_id);
  await waitFor(()=>expect(vi.mocked(apiClient.get).mock.calls.filter(call=>call[0]?.endsWith('/stocks')).at(-1)?.[1]?.params).toMatchObject({industry_id:industry.sector_id,concept_id:undefined}));
});

it.each(['stock','strategy'])('returns to visible stock research for an external %s selection',async change=>{
  const props={board,selectedCode:'600000',onSelectStock:()=>{},onWatchlist:()=>{},onResearch:()=>{}};
  const {rerender}=render(<InvestmentWorkspace {...props}/>);
  await screen.findByRole('heading',{name:'测试股票'});
  fireEvent.click(screen.getByRole('tab',{name:'行业与概念'}));
  rerender(<InvestmentWorkspace {...props} selectedCode={change==='stock'?'000807':'600000'} selectedStrategy={change==='strategy'?'trend_v1':undefined}/>);
  expect(screen.getByRole('tab',{name:'个股行情'})).toHaveAttribute('aria-selected','true');
  expect(screen.getByRole('region',{name:'股票研究详情'})).toBeInTheDocument();
});

it('does not revive a previous board view when an external selection returns to that stock',async()=>{
  const props={board,selectedCode:'600000',onSelectStock:()=>{},onWatchlist:()=>{},onResearch:()=>{}};
  const {rerender}=render(<InvestmentWorkspace {...props}/>);
  await screen.findByRole('heading',{name:'测试股票'});
  fireEvent.click(screen.getByRole('tab',{name:'行业与概念'}));
  rerender(<InvestmentWorkspace {...props} selectedCode="000807"/>);
  expect(screen.getByRole('tab',{name:'个股行情'})).toHaveAttribute('aria-selected','true');
  rerender(<InvestmentWorkspace {...props}/>);
  expect(screen.getByRole('tab',{name:'个股行情'})).toHaveAttribute('aria-selected','true');
});

it('the actual unified value button prepares then starts one model request with one click',async()=>{
 let prepared=false;
 const original=vi.mocked(apiClient.get).getMockImplementation()!;
 const snapshot={code:'600000',snapshot_id:'value-s1',cutoff:'2026-10-31',economic_model:{model:'operating',checklist:[],allowed_methods:['fcff']},missing:[],facts:[],events:[],evidence:[],peers:{candidates:[],confirmed:[],excluded:[],metrics:{}},financial_view:{latest:{},ttm:{},annual:[],quality:{risks:[]},conflicts:[]}};
 vi.mocked(apiClient.get).mockImplementation(async(url,config)=>url?.endsWith('/value-research')?{data:{code:'600000',status:prepared?'ready':'missing',snapshot:prepared?snapshot:null}}:original(url,config));
 vi.mocked(apiClient.post).mockImplementation(async url=>{
  if(url.endsWith('/value-data')){prepared=true;return {data:{accepted:true,status:'preparing'}};}
  return {data:{accepted:true,status:'running'}};
 });
 render(<Workspace/>);
 await screen.findByRole('region',{name:'股票研究详情'});
 fireEvent.change(screen.getByLabelText('研究内容'),{target:{value:'value'}});
 fireEvent.click(screen.getByRole('button',{name:'生成价值研究'}));
 await waitFor(()=>expect(vi.mocked(apiClient.post).mock.calls.filter(([url])=>url.endsWith('/value-research'))).toHaveLength(1));
 expect(vi.mocked(apiClient.post).mock.calls.filter(([url])=>url.endsWith('/value-data'))).toHaveLength(1);
 expect(vi.mocked(apiClient.post).mock.calls.filter(([url])=>url.endsWith('/integrated-research'))).toHaveLength(0);
});
