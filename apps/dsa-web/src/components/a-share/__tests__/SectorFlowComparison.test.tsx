import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import SectorFlowComparisonPanel from '../SectorFlowComparisonPanel';
import {comparisonRows,comparisonSegments} from '../sectorFlowComparisonData';
import {aShareMarketApi} from '../../../api/aShareMarket';
import {MarketContext} from '../MarketContext';
import type {Sector} from '../../../types/aShareMarket';
import type {SectorFlowComparison,FlowPoint} from '../../../types/aShareSectorFlow';
vi.mock('../../../api/aShareMarket',()=>({aShareMarketApi:{sectors:vi.fn(),fundFlowComparison:vi.fn()}}));
const board=(code:string,name:string):Sector=>({sector_id:'em:industry:'+code,code,name,kind:'industry',classification:'eastmoney-industry',change:0,source:'fixture',fetched_at:'now'});
const boards=[board('BK0478','有色金属'),board('BK0438','食品饮料')];
const point=(at:string,n:number):FlowPoint=>({observed_at:at,values:{main:n,super:0,large:null,medium:null,small:null},ratios:{main:.02}});
const series=[{sector:boards[0],points:[point('2026-11-17T02:00:00Z',1e8),point('2026-11-17T02:05:00Z',2e8)],latest:point('2026-11-17T02:05:00Z',2e8)},{sector:boards[1],points:[point('2026-11-17T02:00:00Z',-1e8)],latest:point('2026-11-17T02:00:00Z',-1e8)}];
const response:SectorFlowComparison={kind:'industry',day:'2026-11-17',series,unit:'CNY',measure:'cumulative_snapshot',source:'eastmoney',source_date_verified:false,active:true,calendar_available:true,health:{},poll_pending:false,limitations:[]};
beforeEach(()=>{localStorage.clear();vi.mocked(aShareMarketApi.sectors).mockResolvedValue({items:boards,classification:'eastmoney-industry',period:0,demo:false});vi.mocked(aShareMarketApi.fundFlowComparison).mockResolvedValue(response);});
afterEach(()=>{vi.clearAllMocks();vi.useRealTimers();vi.restoreAllMocks();});
it('aligns all boards in5minute windows without carrying a missing board value or summing cumulative points',()=>{
 const rows=comparisonRows(series,'2026-11-17');const a=rows.find(r=>r.minute===605)!;
 expect(a.cells[boards[0].sector_id]?.values.main).toBe(2e8);expect(a.cells[boards[1].sector_id]).toBeUndefined();
 expect(comparisonSegments(rows,boards[0].sector_id,'main','amount')[0].map(p=>p.value)).toEqual([1e8,2e8]);
 expect(comparisonRows(series,'2026-11-18').every(r=>Object.keys(r.cells).length===0)).toBe(true);
});
it('breaks across missing buckets and lunch, and displays isolated points',()=>{
 const s=[{sector:boards[0],latest:null,points:[point('2026-11-17T03:25:00Z',1),point('2026-11-17T05:00:00Z',2),point('2026-11-17T05:10:00Z',3)]}];
 expect(comparisonSegments(comparisonRows(s,'2026-11-17'),boards[0].sector_id,'main','amount').map(s=>s.length)).toEqual([1,1,1]);
});
it('shows multiple board lines, linked cursor table and category controls without losing detail navigation',async()=>{
 const select=vi.fn();render(<SectorFlowComparisonPanel onSelectSector={select}/>);
 await screen.findByRole('img',{name:'多板块今日资金采样对比图'});
 expect(screen.getAllByRole('checkbox').filter(x=>(x as HTMLInputElement).checked)).toHaveLength(2);
 fireEvent.click(screen.getByRole('button',{name:'查看资金板块有色金属'}));expect(select).toHaveBeenCalledWith(boards[0]);
 expect(screen.getByText(/源交易日期未核实/)).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('对比资金类别'),{target:{value:'super'}});expect(screen.getByLabelText('对比资金类别')).toHaveValue('super');
 fireEvent.change(screen.getByLabelText('对比度量'),{target:{value:'ratio'}});expect(screen.getByLabelText('对比度量')).toHaveValue('ratio');
 fireEvent.click(screen.getByLabelText('对比食品饮料'));await waitFor(()=>expect(aShareMarketApi.fundFlowComparison).toHaveBeenLastCalledWith('industry',[boards[0].sector_id],expect.any(AbortSignal),false));
});
it('does not fetch CN flows for offshore market',()=>{
 render(<MarketContext.Provider value={{market:'hk',currency:'HKD',financialCurrency:'HKD'}}><SectorFlowComparisonPanel onSelectSector={()=>{}}/></MarketContext.Provider>);
 expect(screen.getByText(/仅支持A股/)).toBeInTheDocument();expect(aShareMarketApi.fundFlowComparison).not.toHaveBeenCalled();expect(aShareMarketApi.sectors).not.toHaveBeenCalled();
});
it('pauses polling while hidden and aborts on unmount',async()=>{
 vi.useFakeTimers();let visibility='visible';vi.spyOn(document,'visibilityState','get').mockImplementation(()=>visibility as DocumentVisibilityState);
 const {unmount}=render(<SectorFlowComparisonPanel onSelectSector={()=>{}}/>);
 await act(async()=>{await Promise.resolve();});await act(async()=>{await vi.advanceTimersByTimeAsync(500);});expect(aShareMarketApi.fundFlowComparison).toHaveBeenCalledTimes(1);const count=vi.mocked(aShareMarketApi.fundFlowComparison).mock.calls.length;
 visibility='hidden';await act(async()=>{await vi.advanceTimersByTimeAsync(300000);});expect(aShareMarketApi.fundFlowComparison).toHaveBeenCalledTimes(count);
 const last=vi.mocked(aShareMarketApi.fundFlowComparison).mock.lastCall;unmount();expect(last?.[2]?.aborted).toBe(true);
});
it('caps board selection at8 while keeping it independent from detail navigation',async()=>{
 const many=Array.from({length:10},(_,i)=>board('BK'+String(1000+i),'行业'+i));
 vi.mocked(aShareMarketApi.sectors).mockResolvedValue({items:many,classification:'eastmoney-industry',period:0,demo:false});
 vi.mocked(aShareMarketApi.fundFlowComparison).mockImplementation(async(_kind,ids)=>({...response,series:ids.map(id=>({sector:many.find(b=>b.sector_id===id)!,points:[],latest:null}))}));
 render(<SectorFlowComparisonPanel onSelectSector={()=>{}}/>);await screen.findByLabelText('对比行业9');
 fireEvent.click(screen.getByLabelText('对比行业6'));fireEvent.click(screen.getByLabelText('对比行业7'));
 expect(screen.getByLabelText('对比行业8')).toBeDisabled();expect(screen.getByLabelText('对比行业9')).toBeDisabled();
 expect(screen.getByText(/已选 8\/8/)).toBeInTheDocument();
});
it('ignores a cancelled earlier selection response',async()=>{
 let resolve!:(v:SectorFlowComparison)=>void;
 vi.mocked(aShareMarketApi.fundFlowComparison).mockImplementationOnce(()=>new Promise(r=>{resolve=r;})).mockResolvedValue({...response,series:[series[0]]});
 render(<SectorFlowComparisonPanel onSelectSector={()=>{}}/>);
 await waitFor(()=>expect(aShareMarketApi.fundFlowComparison).toHaveBeenCalledTimes(1));
 const firstSignal=vi.mocked(aShareMarketApi.fundFlowComparison).mock.calls[0][2];
 fireEvent.click(screen.getByLabelText('对比食品饮料'));
 await waitFor(()=>expect(aShareMarketApi.fundFlowComparison).toHaveBeenCalledTimes(2));
 await act(async()=>resolve(response));expect(firstSignal?.aborted).toBe(true);
 expect(screen.queryByRole('button',{name:'查看资金板块食品饮料'})).not.toBeInTheDocument();
});
it('treats missing selected-category values as unknown while zero remains a real point',async()=>{
 const p={...point('2026-11-17T02:00:00Z',0),values:{main:null,super:0,large:null,medium:null,small:null}};
 vi.mocked(aShareMarketApi.fundFlowComparison).mockResolvedValue({...response,series:boards.map(b=>({sector:b,points:[p],latest:p}))});
 render(<SectorFlowComparisonPanel onSelectSector={()=>{}}/>);
 await waitFor(()=>expect(aShareMarketApi.fundFlowComparison).toHaveBeenCalled());
 expect(screen.queryByRole('img',{name:'多板块今日资金采样对比图'})).not.toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('对比资金类别'),{target:{value:'super'}});
 expect(await screen.findByRole('img',{name:'多板块今日资金采样对比图'})).toBeInTheDocument();
});
it('breaks an actual gap over8minutes even when rounded buckets are adjacent',()=>{
 const s=[{sector:boards[0],latest:null,points:[point('2026-11-17T02:00:01Z',1),point('2026-11-17T02:09:59Z',2)]}];
 expect(comparisonSegments(comparisonRows(s,'2026-11-17'),boards[0].sector_id,'main','amount').map(s=>s.length)).toEqual([1,1]);
});
it('recovers a cold empty catalogue without remounting and initializes defaults only after real options arrive',async()=>{
 vi.useFakeTimers();vi.mocked(aShareMarketApi.sectors).mockResolvedValueOnce({items:[],classification:'eastmoney-industry',period:0,demo:false}).mockResolvedValue({items:boards,classification:'eastmoney-industry',period:0,demo:false});
 render(<SectorFlowComparisonPanel onSelectSector={()=>{}}/>);await act(async()=>{await Promise.resolve();});
 expect(screen.queryByLabelText('对比有色金属')).not.toBeInTheDocument();
 await act(async()=>{await vi.advanceTimersByTimeAsync(5000);});
 expect(screen.getByLabelText('对比有色金属')).toBeChecked();expect(screen.getByLabelText('对比食品饮料')).toBeChecked();
 expect(JSON.parse(localStorage.getItem('assistant-flow-comparison:industry')||'null')).toEqual(boards.map(b=>b.sector_id));
});
it('recovers a transient catalogue failure while preserving an intentional empty selection',async()=>{
 vi.useFakeTimers();localStorage.setItem('assistant-flow-comparison:industry','[]');vi.mocked(aShareMarketApi.sectors).mockRejectedValueOnce(new Error('temporary')).mockResolvedValue({items:boards,classification:'eastmoney-industry',period:0,demo:false});
 render(<SectorFlowComparisonPanel onSelectSector={()=>{}}/>);await act(async()=>{await Promise.resolve();});await act(async()=>{await vi.advanceTimersByTimeAsync(30000);});
 expect(screen.getByLabelText('对比有色金属')).not.toBeChecked();expect(aShareMarketApi.fundFlowComparison).not.toHaveBeenCalled();
});
