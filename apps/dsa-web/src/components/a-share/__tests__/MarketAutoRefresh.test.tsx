import { useState } from 'react';
import { act, cleanup, render, screen, fireEvent, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { aShareMarketApi } from '../../../api/aShareMarket';
import type { Sector } from '../../../types/aShareMarket';
import MarketStockBrowser from '../MarketStockBrowser';
import SectorBrowser from '../SectorBrowser';

vi.mock('../../../api/aShareMarket', () => ({
  aShareMarketApi: { stocks: vi.fn(), sectors: vi.fn(), members: vi.fn() },
}));

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-10-13T01:30:00Z'));
  vi.mocked(aShareMarketApi.stocks).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
  vi.mocked(aShareMarketApi.sectors).mockResolvedValue({ items: [], classification: 'eastmoney-industry', period: 0, demo: false });
  vi.mocked(aShareMarketApi.members).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 1, membership: { codes: [], version: 'v1', state: 'ready' } });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

it('rechecks the current filtered stock page after five minutes without resetting filters', async () => {
  const industry = { sector_id: 'em:industry:BK001', name: '测试行业' } as Sector;
  render(<MarketStockBrowser onSelectStock={() => {}} industry={industry} industries={[industry]} concepts={[]} sectorStatus="ready" onSelectIndustry={() => {}} onSelectConcept={() => {}} onClearSector={() => {}} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(250); });
  await act(async () => { await vi.advanceTimersByTimeAsync(250); });
  const initialCalls = vi.mocked(aShareMarketApi.stocks).mock.calls.length;
  expect(initialCalls).toBeGreaterThan(0);
  expect(screen.getByRole('combobox', { name: '行业筛选' })).toHaveValue(industry.sector_id);

  await act(async () => { await vi.advanceTimersByTimeAsync(5 * 60 * 1000); });
  await act(async () => { await vi.advanceTimersByTimeAsync(250); });
  expect(aShareMarketApi.stocks).toHaveBeenCalledTimes(initialCalls + 1);
  for (const call of vi.mocked(aShareMarketApi.stocks).mock.calls) {
    expect(call[0]).toMatchObject({ industry_id: industry.sector_id, page: 1 });
  }
  expect(screen.getByRole('combobox', { name: '行业筛选' })).toHaveValue(industry.sector_id);
});

it('rechecks the board heatmap after five minutes', async () => {
  render(<SectorBrowser onSelectSector={() => {}} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  expect(aShareMarketApi.sectors).toHaveBeenCalledTimes(1);

  await act(async () => { await vi.advanceTimersByTimeAsync(5 * 60 * 1000); });
  expect(aShareMarketApi.sectors).toHaveBeenCalledTimes(2);
  expect(vi.mocked(aShareMarketApi.sectors).mock.calls.map(call => call[0])).toEqual([
    { kind: 'industry', period: 0 },
    { kind: 'industry', period: 0 },
  ]);
});

it('loads selected industry and concept members, then replaces the empty stock list when both are ready', async () => {
  const industry = { sector_id: 'em:industry:BK001', name: '铝', kind: 'industry' } as Sector;
  const concept = { sector_id: 'em:concept:BK002', name: '新能源', kind: 'concept' } as Sector;
  let conceptReady = false;
  vi.mocked(aShareMarketApi.members).mockImplementation(async id => ({
    items: [], total: 0, page: 1, page_size: 1,
    membership: { codes: [], version: id === industry.sector_id || conceptReady ? 'v1' : null, state: id === industry.sector_id || conceptReady ? 'ready' : 'pending' },
  }));
  vi.mocked(aShareMarketApi.stocks).mockImplementation(async () => conceptReady
    ? { items: [{ code: '000807', name: '云铝股份', source: 'fixture', quote: null, industries: [], concepts: [] }], total: 1, page: 1, page_size: 50 }
    : { items: [], total: 0, page: 1, page_size: 50 });

  render(<MarketStockBrowser onSelectStock={() => {}} industry={industry} concept={concept} industries={[industry]} concepts={[concept]} sectorStatus="ready" onSelectIndustry={() => {}} onSelectConcept={() => {}} onClearSector={() => {}} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(250); });
  expect(screen.getByRole('status')).toHaveTextContent('正在获取板块成分股');
  expect(screen.queryByText(/所选范围暂无股票/)).not.toBeInTheDocument();

  conceptReady = true;
  await act(async () => { await vi.advanceTimersByTimeAsync(5500); });
  await act(async () => { await vi.advanceTimersByTimeAsync(250); });
  expect(screen.getByRole('button', { name: '云铝股份 000807' })).toBeInTheDocument();
  expect(screen.getByRole('combobox', { name: '行业筛选' })).toHaveValue(industry.sector_id);
  expect(screen.getByRole('combobox', { name: '概念筛选' })).toHaveValue(concept.sector_id);
});

it('rechecks only the current filtered cached list when a selected-stock refresh revision changes, preserving null change',async()=>{
  let refreshed=false;
  vi.mocked(aShareMarketApi.stocks).mockImplementation(async()=>({items:[{code:'000807',name:'云铝股份',source:'fixture',quote:{price:refreshed?26.27:25,change:refreshed?null:.02,source:'fixture',fetched_at:'2026-10-14T15:20:00+08:00'},industries:[],concepts:[]}],total:1,page:1,page_size:50}));
  const props={onSelectStock:()=>{},selectedCode:'000807',industries:[],concepts:[],sectorStatus:'ready' as const,onSelectIndustry:()=>{},onSelectConcept:()=>{},onClearSector:()=>{}};
  const {rerender}=render(<MarketStockBrowser {...props} reloadRevision={0}/>);
  fireEvent.change(screen.getByLabelText('搜索股票'),{target:{value:'000807'}});
  await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
  const calls=vi.mocked(aShareMarketApi.stocks).mock.calls.length;
  refreshed=true;rerender(<MarketStockBrowser {...props} reloadRevision={1}/>);
  await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
  expect(aShareMarketApi.stocks).toHaveBeenCalledTimes(calls+1);
  expect(aShareMarketApi.stocks).toHaveBeenLastCalledWith(expect.objectContaining({q:'000807',scope:'all',sort:'change',page:1}),expect.any(AbortSignal));
  const row=screen.getByRole('button',{name:'云铝股份 000807'});
  expect(within(row).getByText('26.27')).toBeInTheDocument();expect(within(row).getByText('资料不足')).toBeInTheDocument();
  expect(within(row).queryByText('+0.00%')).not.toBeInTheDocument();
  expect(screen.getByLabelText('搜索股票')).toHaveValue('000807');
});

it('returns to the last available watchlist page after removing its final row',async()=>{
  let removed=false;
  const stock={code:'000807',name:'云铝股份',source:'fixture',quote:null,industries:[],concepts:[]};
  vi.mocked(aShareMarketApi.stocks).mockImplementation(async params=>({
    items:removed&&params.page===2?[]:[stock],total:removed?50:51,page:Number(params.page),page_size:50,
  }));
  const props={onSelectStock:()=>{},industries:[],concepts:[],sectorStatus:'ready' as const,onSelectIndustry:()=>{},onSelectConcept:()=>{},onClearSector:()=>{}};
  const {rerender}=render(<MarketStockBrowser {...props} watchlistSignature="000001|000807"/>);
  fireEvent.click(screen.getByRole('button',{name:'自选股票'}));
  await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
  fireEvent.click(screen.getByRole('button',{name:'下页'}));
  await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
  expect(screen.getByText('2 / 2 · 51 只')).toBeInTheDocument();
  removed=true;rerender(<MarketStockBrowser {...props} watchlistSignature="000001"/>);
  await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
  await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
  expect(screen.getByText('1 / 1 · 50 只')).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'云铝股份 000807'})).toBeInTheDocument();
});

it('does not refetch an all-stocks list merely because the watchlist changes',async()=>{
  const props={onSelectStock:()=>{},industries:[],concepts:[],sectorStatus:'ready' as const,onSelectIndustry:()=>{},onSelectConcept:()=>{},onClearSector:()=>{}};
  const {rerender}=render(<MarketStockBrowser {...props} watchlistSignature="000807"/>);
  await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
  const calls=vi.mocked(aShareMarketApi.stocks).mock.calls.length;
  rerender(<MarketStockBrowser {...props} watchlistSignature=""/>);
  await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
  expect(aShareMarketApi.stocks).toHaveBeenCalledTimes(calls);
});

it('shows a source failure instead of spinning forever and retries the upstream fetch', async () => {
  const industry = {sector_id:'em:industry:BK1586',name:'软饮料',kind:'industry'} as Sector;
  let ready=false;
  vi.mocked(aShareMarketApi.members).mockImplementation(async (_id, params) => {
    if(params.refresh) ready=true;
    return {items:[],total:ready?1:0,page:1,page_size:1,membership:{codes:ready?['000848']:[],version:ready?'v2':null,state:ready?'ready':'failed',error:ready?undefined:'来源暂不可用'}};
  });
  vi.mocked(aShareMarketApi.stocks).mockImplementation(async()=>({items:ready?[{code:'000848',name:'承德露露',source:'fixture',quote:null,industries:[],concepts:[]}]:[],total:ready?1:0,page:1,page_size:50}));
  render(<MarketStockBrowser onSelectStock={()=>{}} industry={industry} industries={[industry]} concepts={[]} sectorStatus="ready" onSelectIndustry={()=>{}} onSelectConcept={()=>{}} onClearSector={()=>{}}/>);
  await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
  expect(screen.getByRole('alert')).toHaveTextContent('来源暂不可用');
  expect(screen.queryByText(/正在获取板块成分股/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'重试板块成员'}));
  await act(async()=>{await vi.advanceTimersByTimeAsync(0);});
  await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
  expect(screen.getByRole('button',{name:'承德露露 000848'})).toBeInTheDocument();
});

it('keeps checking ready memberships so changed constituents replace the cached list',async()=>{
  const industry={sector_id:'em:industry:BK1586',name:'软饮料',kind:'industry'} as Sector;
  let added=false;
  vi.mocked(aShareMarketApi.members).mockImplementation(async()=>({items:[],total:0,page:1,page_size:1,membership:{codes:[],version:added?'v2':'v1',state:'ready'}}));
  vi.mocked(aShareMarketApi.stocks).mockImplementation(async()=>({items:added?[{code:'000848',name:'承德露露',source:'fixture',quote:null,industries:[],concepts:[]}]:[],total:added?1:0,page:1,page_size:50}));
  render(<MarketStockBrowser onSelectStock={()=>{}} industry={industry} industries={[industry]} concepts={[]} sectorStatus="ready" onSelectIndustry={()=>{}} onSelectConcept={()=>{}} onClearSector={()=>{}}/>);
  await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
  added=true;
  await act(async()=>{await vi.advanceTimersByTimeAsync(5*60*1000);});
  await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
  expect(aShareMarketApi.members).toHaveBeenCalledTimes(2);
  expect(screen.getByRole('button',{name:'承德露露 000848'})).toBeInTheDocument();
});

it('distinguishes a genuine empty intersection from unavailable board members',async()=>{
  const industry={sector_id:'em:industry:BK1283',name:'银行',kind:'industry'} as Sector;
  const concept={sector_id:'em:concept:BK0477',name:'酿酒概念',kind:'concept'} as Sector;
  render(<MarketStockBrowser onSelectStock={()=>{}} industry={industry} concept={concept} industries={[industry]} concepts={[concept]} sectorStatus="ready" onSelectIndustry={()=>{}} onSelectConcept={()=>{}} onClearSector={()=>{}}/>);
  await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
  expect(screen.getByText(/所选范围暂无匹配股票；行业与概念取交集/)).toBeInTheDocument();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  expect(screen.queryByText(/正在获取板块成分股/)).not.toBeInTheDocument();
});


it('does not silently revive an old industry when leaving the unclassified filter',async()=>{
  const initial={sector_id:'em:industry:BK1283',name:'银行',kind:'industry'} as Sector;
  const concept={sector_id:'em:concept:BK0477',name:'酿酒概念',kind:'concept'} as Sector;
  function Browser(){
    const [industry,setIndustry]=useState<Sector|undefined>(initial);
    const [selected,setSelected]=useState<Sector>();
    return <MarketStockBrowser onSelectStock={()=>{}} industry={industry} concept={selected} industries={[initial]} concepts={[concept]} sectorStatus="ready" onSelectIndustry={setIndustry} onSelectConcept={setSelected} onClearSector={()=>{}}/>;
  }
  render(<Browser/>);
  await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
  fireEvent.click(screen.getByLabelText('未知行业'));
  fireEvent.change(screen.getByLabelText('概念筛选'),{target:{value:concept.sector_id}});
  await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
  expect(screen.getByLabelText('行业筛选')).toHaveValue('');
  expect(screen.getByLabelText('概念筛选')).toHaveValue(concept.sector_id);
});
