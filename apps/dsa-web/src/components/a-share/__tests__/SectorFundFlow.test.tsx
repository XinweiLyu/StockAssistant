import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import type {SectorFundFlow} from '../../../types/aShareSectorFlow';
import SectorFundFlowPanel from '../SectorFundFlowPanel';
import {MarketContext} from '../MarketContext';
import {aShareMarketApi} from '../../../api/aShareMarket';
import {chartRows,flowSegments} from '../sectorFundFlowData';
vi.mock('../../../api/aShareMarket',()=>({aShareMarketApi:{fundFlow:vi.fn(),refreshFundFlow:vi.fn()}}));
const sector={sector_id:'em:industry:BK0478',name:'有色金属',kind:'industry',code:'BK0478',classification:'eastmoney-industry',source:'fixture',fetched_at:'2026-11-17',change:null} as const;
const payload:SectorFundFlow={sector,period:0,unit:'CNY',source:'eastmoney/sector-flow',measure:'cumulative_snapshot',points:[],summary:{main_net:null,covered:0,required:null},complete:false,task_ids:[],health:{},member_flows:[],limitations:[],calendar_available:true,active:true};
beforeEach(()=>{vi.mocked(aShareMarketApi.fundFlow).mockResolvedValue(payload);vi.mocked(aShareMarketApi.refreshFundFlow).mockResolvedValue(payload);});
afterEach(()=>{vi.clearAllMocks();vi.useRealTimers();});
describe('sector flows',()=>{
 it('shows observation semantics and switches closed-day periods without AI',async()=>{
  render(<SectorFundFlowPanel sector={sector}/>);
  await screen.findByText(/尚无盘中采样/);
  fireEvent.change(screen.getByLabelText('资金流期间'),{target:{value:'20'}});
  await waitFor(()=>expect(aShareMarketApi.fundFlow).toHaveBeenLastCalledWith(sector.sector_id,20,expect.any(AbortSignal)));
  fireEvent.click(screen.getByText('刷新资金数据'));
  await waitFor(()=>expect(aShareMarketApi.refreshFundFlow).toHaveBeenCalledWith(sector.sector_id,20,expect.any(AbortSignal)));
  expect(screen.getByLabelText('超大单')).not.toBeChecked();
 });
 it('does not request CN data in offshore workspace',()=>{
  render(<MarketContext.Provider value={{market:'us',currency:'USD',financialCurrency:'USD'}}><SectorFundFlowPanel sector={sector}/></MarketContext.Provider>);
  expect(screen.getByText(/暂不支持港美股板块资金流/)).toBeInTheDocument();
  expect(aShareMarketApi.fundFlow).not.toHaveBeenCalled();
 });
 it('does not let an older sector response replace the selected board',async()=>{
  let resolve!:(v:SectorFundFlow)=>void;
  vi.mocked(aShareMarketApi.fundFlow).mockImplementationOnce(()=>new Promise(r=>{resolve=r;}));
  const {rerender}=render(<SectorFundFlowPanel sector={sector}/>);
  const next={...sector,sector_id:'em:industry:BK0438',name:'食品饮料'};
  rerender(<SectorFundFlowPanel sector={next}/>);
  await waitFor(()=>expect(aShareMarketApi.fundFlow).toHaveBeenCalledTimes(2));
  await act(async()=>resolve({...payload,observed_at:'OLD_RESPONSE'}));
  expect(screen.queryByText(/OLD_RESPONSE/)).not.toBeInTheDocument();
 });
 it('never adds cumulative snapshots; daily gaps stop cumulative sums',()=>{
  const points=[{source_date:'2026-11-10',values:{main:0}},{source_date:'2026-11-11',values:{main:null}},{source_date:'2026-11-12',values:{main:10}}];
  expect(chartRows(points as never,5).map(r=>r.cumulative)).toEqual([0,null,null]);
  const snapshots=[{observed_at:'2026-11-17T03:30:00Z',values:{main:10}},{observed_at:'2026-11-17T05:00:00Z',values:{main:20}}];
  expect(chartRows(snapshots as never,0).map(r=>r.cumulative)).toEqual([null,null]);
  expect(flowSegments(chartRows(snapshots as never,0),'main',0).length).toBe(2);
 });
});
it('polls visible pending work, pauses while hidden and cancels on unmount',async()=>{
 vi.useFakeTimers();let visibility='visible';vi.spyOn(document,'visibilityState','get').mockImplementation(()=>visibility as DocumentVisibilityState);
 vi.mocked(aShareMarketApi.fundFlow).mockResolvedValue({...payload,task_ids:['task']});
 const {unmount}=render(<SectorFundFlowPanel sector={sector}/>);
 await act(async()=>{await vi.advanceTimersByTimeAsync(0);});expect(aShareMarketApi.fundFlow).toHaveBeenCalledTimes(1);
 visibility='hidden';await act(async()=>{await vi.advanceTimersByTimeAsync(10000);});expect(aShareMarketApi.fundFlow).toHaveBeenCalledTimes(1);
 visibility='visible';await act(async()=>{document.dispatchEvent(new Event('visibilitychange'));});expect(aShareMarketApi.fundFlow).toHaveBeenCalledTimes(2);
 const signal=vi.mocked(aShareMarketApi.fundFlow).mock.calls[1][2];unmount();expect(signal?.aborted).toBe(true);vi.restoreAllMocks();
});
it('manual refresh applies once and a subsequent period change remains a cached read',async()=>{
 render(<SectorFundFlowPanel sector={sector}/>);await screen.findByText(/尚无盘中采样/);fireEvent.click(screen.getByText('刷新资金数据'));
 await waitFor(()=>expect(aShareMarketApi.refreshFundFlow).toHaveBeenCalledTimes(1));fireEvent.change(screen.getByLabelText('资金流期间'),{target:{value:'60'}});
 await waitFor(()=>expect(aShareMarketApi.fundFlow).toHaveBeenLastCalledWith(sector.sector_id,60,expect.any(AbortSignal)));expect(aShareMarketApi.refreshFundFlow).toHaveBeenCalledTimes(1);
});
