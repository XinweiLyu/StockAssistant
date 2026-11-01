import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {expect,it,vi,beforeEach} from 'vitest';
import ValueInvestingPanel from '../ValueInvestingPanel';
import {useValueResearch} from '../useValueResearch';
import {aShareMarketApi} from '../../../api/aShareMarket';
import type {ValueResearchResult} from '../../../types/aShareValue';
import type {ValueSnapshot} from '../../../types/aShareValue';
import ValueAssumptionEditor from '../ValueAssumptionEditor';
import type {ValueAssumptions} from '../../../types/aShareValue';
vi.mock('../../../api/aShareMarket',()=>({aShareMarketApi:{getValue:vi.fn(),prepareValue:vi.fn(),generateValue:vi.fn(),saveValueAssumptions:vi.fn(),evaluateValue:vi.fn()}}));
beforeEach(()=>vi.clearAllMocks());

it('preserves value cards with free draft recalculation after saving monitoring without confirming valuation',async()=>{
 let calculated=false;
 vi.mocked(aShareMarketApi.getValue).mockImplementation(async code=>({code,status:'ready',snapshot:{snapshot_id:'s'},report:calculated?{valuation_state:'draft'}:null}) as ValueResearchResult);
 vi.mocked(aShareMarketApi.saveValueAssumptions).mockResolvedValue({revision:1} as ValueAssumptions);
 vi.mocked(aShareMarketApi.evaluateValue).mockImplementation(async()=>{calculated=true;return {} as Awaited<ReturnType<typeof aShareMarketApi.evaluateValue>>;});
 const a={code:'605499',snapshot_id:'s',cases:[{method:'ddm',scenario:'base'}],monitor_rules:[{id:'r',metric:'revenue',operator:'lt',threshold:80,unit:'CNY',sources:['F1']}]} as ValueAssumptions;
 function Harness(){const state=useValueResearch('605499');return <><button onClick={()=>void state.save(a,false)}>保存复核</button><p>{state.result?.report?'草案已重算':'待读取'}</p></>;}
 render(<Harness/>);await waitFor(()=>expect(aShareMarketApi.getValue).toHaveBeenCalled());
 fireEvent.click(screen.getByRole('button',{name:'保存复核'}));
 await screen.findByText('草案已重算');
 expect(aShareMarketApi.saveValueAssumptions).toHaveBeenCalledWith('605499','s',0,a,false,expect.any(AbortSignal));
 expect(aShareMarketApi.evaluateValue).toHaveBeenCalledWith('605499','s',1,expect.any(AbortSignal));
 expect(aShareMarketApi.generateValue).not.toHaveBeenCalled();
});

it('shows a numerical reference clearly separated from the incomplete AI valuation',()=>{
 const peers={candidates:[],confirmed:[],excluded:[],metrics:{}};
 const result={code:'605499',status:'ready',snapshot:{code:'605499',snapshot_id:'s',cutoff:'2026-11-01',economic_model:{model:'operating',checklist:[],allowed_methods:['ddm']},facts:[],events:[],evidence:[],missing:[],peers,financial_view:{latest:{},ttm:{},annual:[],quality:{risks:[]},conflicts:[]}},review:{status:'partial',missing:['AI尚缺完整资本核验']},reference:{state:'ready',label:'可编辑的股利参数试算，不是AI完整估值',limitations:['参数不是已验证预测'],parameters:[],report:{valuation_state:'reference',primary_method:'ddm',valuation_cases:['conservative','base','upside'].map(scenario=>({method:'ddm',scenario,state:'ready',value_per_share:12,missing:[]})),comparison:{conditional_price:null},peers,theses:[],missing:[],sensitivities:[],driver_effects:[],holding_cases:[]}}} as unknown as ValueResearchResult;
 const {rerender}=render(<ValueInvestingPanel code="605499" state={{result,loading:false,busy:false} as ReturnType<typeof useValueResearch>} onRequestResearch={()=>undefined}/>);
 expect(screen.getByText('可编辑的股利参数试算，不是AI完整估值')).toBeInTheDocument();
 expect(screen.getAllByText('¥12.00')).toHaveLength(3);
 expect(screen.getByText('参数不是已验证预测')).toBeInTheDocument();
 expect(screen.getByText('AI尚缺完整资本核验')).toBeInTheDocument();
 expect(screen.getByText('要求折价对应价格（试算）')).toBeInTheDocument();
 expect(screen.getByText('¥9.00')).toBeInTheDocument();
 expect(screen.queryByText('满足要求折价的条件参考上限')).not.toBeInTheDocument();
 result.report={...result.reference!.report!,valuation_state:'stale',parameter_origin:'reference_sensitivity_v1'};
 result.reference=null;
 result.history=[{snapshot_id:'old',assumptions_revision:1,generated_at:'2026-10-30',primary_method:'ddm',parameter_origin:'reference_sensitivity_v1',valuation_cases:[]}];
 rerender(<ValueInvestingPanel code="605499" state={{result,loading:false,busy:false} as ReturnType<typeof useValueResearch>} onRequestResearch={()=>undefined}/>);
 expect(screen.getByText('历史参数试算，资料已变化')).toBeInTheDocument();
 expect(screen.queryByText('保守价值',{exact:true})).not.toBeInTheDocument();
 expect(screen.getByText(/历史参数试算（非AI估值）/)).toBeInTheDocument();
});

it('allows review and editing of a proposed dividend share and cash bridge without calling AI',async()=>{
 const snapshot={code:'605499',snapshot_id:'s',economic_model:{allowed_methods:['ddm']},evidence:[{id:'F1',source:'原文'}],events:[],peers:{candidates:[]}} as unknown as ValueSnapshot;
 const assumptions={code:'605499',snapshot_id:'s',primary_method:'ddm',cases:[{method:'ddm',scenario:'conservative',shares:10,fixed_capital:false,dividends:[8,8,8,8,8],capital_bridge:{basis:'model_proposal',sources:['F1'],rationale:'资本情景',timing:'actions_before_dividend',initial_treasury_shares:1,years:[{repurchased_shares:1}]} }],risk_review:{},peer_confirmations:[],driver_changes:[],holding_cases:[],theses:[]} as unknown as ValueAssumptions;
 const save=vi.fn().mockResolvedValue({});
 render(<ValueAssumptionEditor snapshot={snapshot} assumptions={assumptions} busy={false} onSave={save}/>);
 expect(screen.getByLabelText('保守·初始库存股数')).toHaveValue(1);
 fireEvent.change(screen.getByLabelText('保守·第1年回购股数'),{target:{value:'2'}});
 fireEvent.click(screen.getByRole('button',{name:'保存草案（不调用AI）'}));
 await waitFor(()=>expect(save).toHaveBeenCalledOnce());
 expect(save.mock.calls[0][0].cases[0].capital_bridge.years[0].repurchased_shares).toBe(2);
 expect(save.mock.calls[0][0].cases[0].capital_bridge.sources).toEqual(['F1']);
 expect(save.mock.calls[0][1]).toBe(false);
 expect(aShareMarketApi.generateValue).not.toHaveBeenCalled();
});

it('shows concrete missing sources and returns to the unified research control',()=>{
 const action=vi.fn();
 render(<ValueInvestingPanel code="000807" state={{result:{code:'000807',status:'missing'} as ValueResearchResult,loading:false,busy:false} as ReturnType<typeof useValueResearch>} onRequestResearch={action}/>);
 expect(screen.getByRole('region',{name:'价值投资研究'})).toHaveTextContent('财报');
 fireEvent.click(screen.getByRole('button',{name:'在统一入口研究价值'}));expect(action).toHaveBeenCalledOnce();
 expect(aShareMarketApi.generateValue).not.toHaveBeenCalled();
});

it('discards a late response for the previous stock without calling a model',async()=>{
 let resolveA!:(r:ValueResearchResult)=>void;
 vi.mocked(aShareMarketApi.getValue).mockImplementation(code=>code==='000807'?new Promise(r=>{resolveA=r;}):Promise.resolve({code,status:'missing'} as ValueResearchResult));
 function Harness({code}:{code:string}){const state=useValueResearch(code);return <div>{state.result?.code||'loading'}</div>;}
 const {rerender}=render(<Harness code="000807"/>);rerender(<Harness code="601899"/>);
 await screen.findByText('601899');resolveA({code:'000807',status:'missing'} as ValueResearchResult);
 await waitFor(()=>expect(screen.queryByText('000807')).not.toBeInTheDocument());
 expect(aShareMarketApi.generateValue).not.toHaveBeenCalled();
});

it('saves explicit manual assumptions without inventing zero or calling AI',async()=>{
 const snapshot={code:'000807',snapshot_id:'s1',economic_model:{allowed_methods:['fcff'],model:'unresolved'},financial_view:{latest:{shares:{value:10}},ttm:{revenue:{value:100}}},evidence:[{id:'F1',source:'财报'}],events:[],peers:{candidates:[]}} as unknown as ValueSnapshot;
 const save=vi.fn().mockResolvedValue({});
 render(<ValueAssumptionEditor snapshot={snapshot} busy={false} onSave={save}/>);
 expect(screen.getByLabelText('保守·第1年投资/营收 %')).toHaveValue(null);
 fireEvent.change(screen.getByLabelText('人工核对经济模型'),{target:{value:'operating'}});
 fireEvent.change(screen.getByLabelText('主营判断依据'),{target:{value:'核对年报业务结构'}});
 fireEvent.change(screen.getByLabelText('假设的基础资料'),{target:{value:'F1'}});
 fireEvent.click(screen.getByRole('button',{name:'保存草案（不调用AI）'}));
 await waitFor(()=>expect(save).toHaveBeenCalledOnce());
 expect(save.mock.calls[0][0].cases[0].operating.years[0]).not.toHaveProperty('capex_ratio');
 expect(save.mock.calls[0][0].economic_model_override.model).toBe('operating');
 expect(aShareMarketApi.generateValue).not.toHaveBeenCalled();
});

it('keeps a failed manual action visible after the cache is read again',async()=>{
 vi.mocked(aShareMarketApi.getValue).mockImplementation(async code=>({code,status:'ready',snapshot:{snapshot_id:'s1'}} as ValueResearchResult));
 vi.mocked(aShareMarketApi.generateValue).mockRejectedValue(new Error('请先启用研究模型'));
 function Harness(){const state=useValueResearch('000807');return <><button onClick={()=>void state.generate().catch(()=>undefined)}>研究</button><p>{state.error}</p><i>{state.result?.status}</i></>;}
 render(<Harness/>);await screen.findByText('ready');fireEvent.click(screen.getByRole('button',{name:'研究'}));
 await screen.findByText('请先启用研究模型');
 await waitFor(()=>expect(aShareMarketApi.getValue).toHaveBeenCalledTimes(2));
 expect(screen.getByText('请先启用研究模型')).toBeInTheDocument();
});

it('labels historical AI views separately and identifies holding scenarios',()=>{
 const result={code:'000807',status:'ready',historical_review:{status:'partial',theses:[{text:'旧观点A'}],stale_reason:'假设已变化'},snapshot:{code:'000807',snapshot_id:'s',cutoff:'2026-10-30',economic_model:{model:'operating',checklist:[],allowed_methods:['ddm']},missing:[],facts:[],events:[],evidence:[],peers:{candidates:[],confirmed:[],excluded:[],metrics:{}},financial_view:{latest:{},ttm:{},annual:[],quality:{risks:[]},conflicts:[]}},report:{primary_method:'ddm',valuation_state:'draft',valuation_cases:[],comparison:{},theses:[{text:'当前观点B'}],missing:[],sensitivities:[],driver_effects:[],holding_cases:[{months:12,method:'ddm',scenario:'conservative',state:'ready',intrinsic_value:10,price:8,dividends:1,gross_return:.1}]}} as unknown as ValueResearchResult;
 render(<ValueInvestingPanel code="000807" state={{result,loading:false,busy:false} as ReturnType<typeof useValueResearch>} onRequestResearch={()=>undefined}/>);
 expect(screen.getByText('当前观点B')).toBeInTheDocument();
 expect(screen.getByText(/保守情景 · 现金股利/)).toBeInTheDocument();
 expect(screen.getByText('历史AI观点（资料或假设已变化）')).toBeInTheDocument();
});

it('one explicit generation click prepares missing data and submits one value model request',async()=>{
 let prepared=false,reads=0;
 vi.mocked(aShareMarketApi.getValue).mockImplementation(async code=>{
  reads++;
  return {code,status:prepared&&reads>2?'ready':'missing',snapshot:prepared&&reads>2?{snapshot_id:'s1'}:null} as ValueResearchResult;
 });
 vi.mocked(aShareMarketApi.prepareValue).mockImplementation(async()=>{prepared=true;return {accepted:true,status:'preparing'};});
 vi.mocked(aShareMarketApi.generateValue).mockResolvedValue({accepted:true,status:'running'});
 function Harness(){const state=useValueResearch('605499');return <><button onClick={()=>void state.research().catch(()=>undefined)}>生成价值研究</button><p>{state.result?.status}</p></>;}
 render(<Harness/>);await screen.findByText('missing');
 fireEvent.click(screen.getByRole('button',{name:'生成价值研究'}));
 await waitFor(()=>expect(aShareMarketApi.generateValue).toHaveBeenCalledOnce());
 expect(aShareMarketApi.prepareValue).toHaveBeenCalledOnce();
 expect(aShareMarketApi.generateValue).toHaveBeenCalledWith('605499','s1',false,expect.any(AbortSignal));
});

it('does not present prepared-only data as a completed but insufficient valuation',()=>{
 const result={code:'605499',status:'ready',snapshot:{code:'605499',snapshot_id:'s',cutoff:'2026-10-31',economic_model:{model:'operating',checklist:[],allowed_methods:['fcff']},missing:['当前总股本未核实'],facts:[],events:[],evidence:[],peers:{candidates:[],confirmed:[],excluded:[],metrics:{}},financial_view:{latest:{},ttm:{},annual:[],quality:{risks:[]},conflicts:[]}}} as unknown as ValueResearchResult;
 render(<ValueInvestingPanel code="605499" state={{result,loading:false,busy:false} as ReturnType<typeof useValueResearch>} onRequestResearch={()=>undefined}/>);
 expect(screen.getByText('资料已准备，尚未生成AI研究')).toBeInTheDocument();
 expect(screen.queryByText('研究资料/方法尚不足')).not.toBeInTheDocument();
 expect(screen.queryAllByText('依据不足')).toHaveLength(0);
 expect(screen.getAllByText('尚未生成')).toHaveLength(3);
 expect(screen.getByText('当前总股本未核实')).toBeInTheDocument();
});

it('cancels a not-yet-started model continuation when switching stocks',async()=>{
 let resolvePrepared!:(v:ValueResearchResult)=>void;
 let prepared=false;
 vi.mocked(aShareMarketApi.getValue).mockImplementation(async code=>{
  if(code==='600519')return {code,status:'missing'} as ValueResearchResult;
  if(prepared)return new Promise(resolve=>{resolvePrepared=resolve;});
  return {code,status:'missing'} as ValueResearchResult;
 });
 vi.mocked(aShareMarketApi.prepareValue).mockImplementation(async()=>{prepared=true;return {accepted:true,status:'preparing'};});
 function Harness({code}:{code:string}){const state=useValueResearch(code);return <><button onClick={()=>void state.research().catch(()=>undefined)}>生成</button><p>{state.result?.code}</p></>;}
 const {rerender}=render(<Harness code="605499"/>);await screen.findByText('605499');
 fireEvent.click(screen.getByRole('button',{name:'生成'}));
 await waitFor(()=>expect(resolvePrepared).toBeTypeOf('function'));
 rerender(<Harness code="600519"/>);await screen.findByText('600519');
 resolvePrepared({code:'605499',status:'ready',snapshot:{snapshot_id:'s1'}} as ValueResearchResult);
 await waitFor(()=>expect(screen.getByText('600519')).toBeInTheDocument());
 expect(aShareMarketApi.generateValue).not.toHaveBeenCalled();
});

it('does not pay for a model when data preparation fails',async()=>{
 let prepared=false;
 vi.mocked(aShareMarketApi.getValue).mockImplementation(async code=>({code,status:prepared?'failed':'missing',data_task:prepared?{state:'failed',error:'财报取数失败'}:null} as ValueResearchResult));
 vi.mocked(aShareMarketApi.prepareValue).mockImplementation(async()=>{prepared=true;return {accepted:true,status:'preparing'};});
 function Harness(){const state=useValueResearch('605499');return <><button onClick={()=>void state.research().catch(()=>undefined)}>生成</button><p>{state.error}</p></>;}
 render(<Harness/>);await waitFor(()=>expect(aShareMarketApi.getValue).toHaveBeenCalled());
 fireEvent.click(screen.getByRole('button',{name:'生成'}));
 await screen.findByText('财报取数失败');
 expect(aShareMarketApi.generateValue).not.toHaveBeenCalled();
});

it('refreshes an existing prepared snapshot with missing current capital before generating',async()=>{
 let repaired=false;
 vi.mocked(aShareMarketApi.getValue).mockImplementation(async code=>({code,status:'ready',snapshot:{snapshot_id:repaired?'s2':'s1',financial_view:{current_capital:repaired?{value:734199310}:null}}} as unknown as ValueResearchResult));
 vi.mocked(aShareMarketApi.prepareValue).mockImplementation(async()=>{repaired=true;return {accepted:true,status:'preparing'};});
 vi.mocked(aShareMarketApi.generateValue).mockResolvedValue({accepted:true,status:'running'});
 function Harness(){const state=useValueResearch('605499');return <><button onClick={()=>void state.research().catch(()=>undefined)}>生成</button><i>{state.result?.snapshot?.snapshot_id}</i></>;}
 render(<Harness/>);await screen.findByText('s1');fireEvent.click(screen.getByRole('button',{name:'生成'}));
 await waitFor(()=>expect(aShareMarketApi.generateValue).toHaveBeenCalled());
 expect(aShareMarketApi.prepareValue).toHaveBeenCalledOnce();
 expect(aShareMarketApi.generateValue).toHaveBeenCalledWith('605499','s2',false,expect.any(AbortSignal));
});

it('waits for data repair even when a previous failed model overrides the top-level status',async()=>{
 let prepared=false,reads=0;
 vi.mocked(aShareMarketApi.getValue).mockImplementation(async code=>{
  if(!prepared)return {code,status:'failed',stale_reasons:['财报/股本已变化'],snapshot:{snapshot_id:'old',financial_view:{current_capital:{value:10}}}} as unknown as ValueResearchResult;
  reads++;
  return {code,status:'failed',data_task:{state:reads<2?'running':'complete'},snapshot:{snapshot_id:reads<2?'old':'repaired',financial_view:{current_capital:{value:10}}}} as unknown as ValueResearchResult;
 });
 vi.mocked(aShareMarketApi.prepareValue).mockImplementation(async()=>{prepared=true;return {accepted:true,status:'preparing'};});
 vi.mocked(aShareMarketApi.generateValue).mockResolvedValue({accepted:true,status:'running'});
 function Harness(){const state=useValueResearch('605499');return <><button onClick={()=>void state.research().catch(()=>undefined)}>生成</button><i>{state.result?.snapshot?.snapshot_id}</i></>;}
 render(<Harness/>);await screen.findByText('old');fireEvent.click(screen.getByRole('button',{name:'生成'}));
 await waitFor(()=>expect(aShareMarketApi.generateValue).toHaveBeenCalled(),{timeout:5000});
 expect(aShareMarketApi.prepareValue).toHaveBeenCalledOnce();
 expect(aShareMarketApi.generateValue).toHaveBeenCalledWith('605499','repaired',false,expect.any(AbortSignal));
});
