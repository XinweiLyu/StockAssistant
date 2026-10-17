import { render,screen,fireEvent,renderHook,waitFor,act } from '@testing-library/react';
import { vi,it,expect,beforeEach } from 'vitest';
import IntegratedResearchPanel from '../IntegratedResearchPanel';
import { useIntegratedResearch } from '../useIntegratedResearch';
import { integratedChartLayer } from '../priceChartData';
import PriceChart from '../PriceChart';
import { aShareMarketApi } from '../../../api/aShareMarket';
import { integratedFixture,integratedHistory } from './integratedFixture';
vi.mock('../../../api/aShareMarket',()=>({aShareMarketApi:{integrated:vi.fn(),prepareResearch:vi.fn(),generateIntegrated:vi.fn()}}));
beforeEach(()=>vi.resetAllMocks());

it('shows evidence coverage, real strategy levels and missing case statistics on the same panel',()=>{
  render(<IntegratedResearchPanel result={integratedFixture()} horizon={20} onHorizon={()=>{}} onPrepare={()=>{}} onGenerate={()=>{}}/>);
  expect(screen.getByRole('region',{name:'综合预测与策略'})).toBeInTheDocument();
  expect(screen.getByText('¥19.00 – ¥20.00')).toBeInTheDocument();
  expect(screen.getByText('¥19.00 – ¥19.50')).toBeInTheDocument();
  expect(screen.getByText(/25.00.*26.00/)).toBeInTheDocument();
  expect(screen.getByText(/2.*事件.*1.*公司/)).toBeInTheDocument();
  expect(screen.getByText(/样本不足，未发布历史事件数值预测/)).toBeInTheDocument();
  expect(screen.getByText(/历史行业未核实/)).toBeInTheDocument();
});

it('does not generate on open or horizon changes and separates prepare from paid research',()=>{
  const generate=vi.fn(),prepare=vi.fn(),change=vi.fn();
  render(<IntegratedResearchPanel result={integratedFixture()} horizon={20} onHorizon={change} onPrepare={prepare} onGenerate={generate}/>);
  fireEvent.change(screen.getByLabelText('综合研究期限'),{target:{value:'60'}});
  expect(change).toHaveBeenCalledWith(60);
  expect(generate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'更新研究资料'}));
  expect(prepare).toHaveBeenCalledOnce();expect(generate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'生成综合预测'}));
  expect(generate).toHaveBeenCalledWith(false);
});

it('marks stale research and keeps its historical result visible',()=>{
  const state=integratedFixture();state.status='stale';
  render(<IntegratedResearchPanel result={state} horizon={20} onHorizon={()=>{}} onPrepare={()=>{}} onGenerate={()=>{}}/>);
  expect(screen.getByText(/资料或价格已变化/)).toBeInTheDocument();
  expect(screen.getByText('¥19.00 – ¥20.00')).toBeInTheDocument();
});

it('shows the absence of matured validation and advances peer batches',()=>{
  const prepare=vi.fn(),state=integratedFixture();
  state.validation={status:'insufficient',snapshots:1,portfolio_return:null,costs_verified:false,horizons:{'20':{matured:0,non_overlapping_samples:0,status:'insufficient',mean_absolute_error:null,direction_accuracy:null,observed_scenario_coverage:null,mean_adverse:null}},limitations:[],comparison:{horizons:{'20':{samples:0,unchanged_price_mae:null,price_model_mae:null,integrated_mae:null}}}};
  render(<IntegratedResearchPanel result={state} horizon={20} onHorizon={()=>{}} onPrepare={prepare} onGenerate={()=>{}}/>);
  expect(screen.getByText(/尚无成熟的20日预测/)).toBeInTheDocument();
  expect(screen.getByText(/综合策略收益尚未验证/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'补充下一批同业资料'}));
  fireEvent.click(screen.getByRole('button',{name:'补充下一批同业资料'}));
  expect(prepare.mock.calls).toEqual([[20],[40]]);
});

it('maps only exact matching history bindings and preserves the old blue layer',()=>{
  const state=integratedFixture(),raw=integratedHistory(),qfq=integratedHistory('qfq');
  const layer=integratedChartLayer(state,raw,qfq,'qfq','000807',20);
  expect(layer?.forecast?.points[0].low).toBeCloseTo(16.8);
  expect(layer?.levels.find(l=>l.id==='integrated-second')?.low).toBeCloseTo(15.2);
  expect(integratedChartLayer(state,raw,{...qfq,fetched_at:'new-generation'},'qfq','000807',20)).toBeUndefined();
  expect(integratedChartLayer({...state,status:'stale'},raw,qfq,'qfq','000807',20)).toBeUndefined();
  expect(integratedChartLayer(state,raw,qfq,'qfq','600000',20)).toBeUndefined();
  expect(integratedChartLayer({...state,bundle:{...state.bundle!,data_hash:'new-data'}},raw,qfq,'qfq','000807',20)).toBeUndefined();
  render(<PriceChart items={qfq.items} chartType="candle" indicators={{}} levels={layer?.levels||[]} integrated={layer?.forecast}/>);
  expect(screen.getByLabelText('20交易日综合研究情景')).toBeInTheDocument();
  expect(screen.getByText(/情景.*研究估计，尚未校准/)).toBeInTheDocument();
  expect(document.querySelector('[data-level-id="integrated-stop"] line')).toHaveAttribute('stroke-dasharray','5 3');
});

it('uses one future time axis for blue20 and integrated60 session forecasts',()=>{
  const history=integratedHistory();
  const common={code:'000807',anchor_date:'2026-10-15',anchor_price:20,target_date:null,points:[{sessions:20,date:null,low:18,median:20,high:22}]};
  const {container}=render(<PriceChart items={history.items} chartType="candle" indicators={{}} levels={[]}
    forecast={{...common,horizon_sessions:20,nominal_coverage:.8}}
    integrated={{...common,horizon_sessions:60,points:[{sessions:60,date:null,low:17,median:21,high:24}]}}/>);
  const blue=container.querySelector('[data-outlook-code] path:last-of-type')!.getAttribute('d')!;
  const pink=container.querySelector('[data-integrated-code] path:last-of-type')!.getAttribute('d')!;
  const lastX=(path:string)=>Number([...path.matchAll(/L([\d.]+),/g)].at(-1)![1]);
  expect(lastX(blue)).toBeLessThan(lastX(pink));
  expect(lastX(blue)).toBeCloseTo(840+130/3);
});

it('distinguishes event runup and current-stage runup and shows realized case outcomes',()=>{
  const state=integratedFixture();
  state.bundle!.cases.cases=[{id:'e1',title:'原业绩事件',published_at:'2024-01-01',event_pre20:.1,pre20:.3,
    outcomes:{'20':{stock_return:.15,market_excess:.07,industry_excess:.04}}}];
  render(<IntegratedResearchPanel result={state} horizon={20} onHorizon={()=>{}} onPrepare={()=>{}} onGenerate={()=>{}}/>);
  expect(screen.getByRole('columnheader',{name:'当前阶段20日'})).toBeInTheDocument();
  expect(screen.getByRole('columnheader',{name:'期内收益'})).toBeInTheDocument();
  expect(screen.getByRole('cell',{name:'15.00%'})).toBeInTheDocument();
  expect(screen.getByRole('cell',{name:'10.00%'})).toBeInTheDocument();
});

it('late responses from a previous stock cannot replace current research',async()=>{
  let resolve!:(value:ReturnType<typeof integratedFixture>)=>void;
  vi.mocked(aShareMarketApi.integrated).mockImplementation(code=>code==='000807'?new Promise(r=>{resolve=r;}):Promise.resolve({...integratedFixture(),code:'600000'}));
  const {result,rerender}=renderHook(({code})=>useIntegratedResearch(code),{initialProps:{code:'000807'}});
  rerender({code:'600000'});
  await waitFor(()=>expect(result.current.result?.code).toBe('600000'));
  await act(async()=>resolve(integratedFixture()));
  expect(result.current.result?.code).toBe('600000');
  expect(aShareMarketApi.generateIntegrated).not.toHaveBeenCalled();
});

it('read failures remain local to integrated research and can be retried',async()=>{
  vi.mocked(aShareMarketApi.integrated).mockRejectedValueOnce(new Error('来源暂不可用')).mockResolvedValue(integratedFixture());
  const {result}=renderHook(()=>useIntegratedResearch('000807'));
  await waitFor(()=>expect(result.current.error).toContain('来源暂不可用'));
  act(()=>result.current.reload());
  await waitFor(()=>expect(result.current.result?.code).toBe('000807'));
});


it('distinguishes the historical report price anchor from refreshed source data',()=>{
  const state=integratedFixture();state.status='stale';
  state.bundle!.anchor_date='2026-10-16';state.bundle!.reference_price=21;
  state.report!.anchor_date='2026-10-14';state.report!.reference_price=18;
  render(<IntegratedResearchPanel result={state} horizon={20} onHorizon={()=>{}} onPrepare={()=>{}} onGenerate={()=>{}}/>);
  expect(screen.getByText(/当前资料截止/)).toHaveTextContent('2026-10-16 ¥21.00');
  expect(screen.getByText(/研究价格锚点/)).toHaveTextContent('2026-10-14 ¥18.00');
});


it('explains an omitted horizon strategy without inventing trade levels',()=>{
  const state=integratedFixture();state.report!.plans=[];
  render(<IntegratedResearchPanel result={state} horizon={20} onHorizon={()=>{}} onPrepare={()=>{}} onGenerate={()=>{}}/>);
  expect(screen.getByText(/20日尚无综合交易策略/)).toBeInTheDocument();
  expect(screen.queryByRole('button',{name:/止损参考/})).not.toBeInTheDocument();
});


it('locks generation against an older poll and synchronous repeated submissions',async()=>{
  let resolveRead!:(value:ReturnType<typeof integratedFixture>)=>void;
  let resolvePost!:(value:{accepted:boolean;status:string})=>void;
  vi.mocked(aShareMarketApi.integrated).mockResolvedValueOnce(integratedFixture()).mockImplementationOnce(()=>new Promise(r=>{resolveRead=r;})).mockResolvedValue({...integratedFixture(),status:'running'});
  vi.mocked(aShareMarketApi.generateIntegrated).mockImplementation(()=>new Promise(r=>{resolvePost=r;}));
  const {result}=renderHook(()=>useIntegratedResearch('000807'));
  await waitFor(()=>expect(result.current.result?.status).toBe('ready'));
  act(()=>fireEvent(window,new Event('focus')));
  let operation!:Promise<void>;
  act(()=>{operation=result.current.generate(true);void result.current.generate(true);});
  await act(async()=>resolveRead(integratedFixture()));
  expect(result.current.busy).toBe(true);
  expect(aShareMarketApi.generateIntegrated).toHaveBeenCalledTimes(1);
  await act(async()=>{resolvePost({accepted:true,status:'running'});await operation;});
  expect(result.current.busy).toBe(true);
});

it('keeps accepted background work locked through read failures until a terminal read',async()=>{
  vi.mocked(aShareMarketApi.integrated).mockResolvedValueOnce(integratedFixture()).mockRejectedValueOnce(new Error('temporary GET failure')).mockResolvedValue(integratedFixture());
  vi.mocked(aShareMarketApi.generateIntegrated).mockResolvedValue({accepted:true,status:'running'});
  const {result}=renderHook(()=>useIntegratedResearch('000807'));
  await waitFor(()=>expect(result.current.result?.status).toBe('ready'));
  await act(async()=>{await result.current.generate(true);});
  await waitFor(()=>expect(result.current.error).toBe('temporary GET failure'));
  expect(result.current.busy).toBe(true);
  await act(async()=>{await result.current.generate(true);});
  expect(aShareMarketApi.generateIntegrated).toHaveBeenCalledTimes(1);
  act(()=>result.current.reload());
  await waitFor(()=>expect(result.current.busy).toBe(false));
  expect(result.current.error).toBeUndefined();
});

it('does not carry pending actions to a different stock or overwrite it on acknowledgment',async()=>{
  let resolvePost!:(value:{accepted:boolean;status:string})=>void;
  vi.mocked(aShareMarketApi.integrated).mockImplementation(async code=>({...integratedFixture(),code}));
  vi.mocked(aShareMarketApi.generateIntegrated).mockImplementation(()=>new Promise(r=>{resolvePost=r;}));
  const {result,rerender}=renderHook(({code})=>useIntegratedResearch(code),{initialProps:{code:'000807'}});
  await waitFor(()=>expect(result.current.result?.status).toBe('ready'));
  let operation!:Promise<void>;act(()=>{operation=result.current.generate(true);});
  rerender({code:'600000'});
  await waitFor(()=>expect(result.current.result?.code).toBe('600000'));
  expect(result.current.busy).toBe(false);
  await act(async()=>{resolvePost({accepted:true,status:'running'});await operation;});
  expect(result.current.result?.code).toBe('600000');
  expect(result.current.busy).toBe(false);
});
