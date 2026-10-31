import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {expect,it,vi,beforeEach} from 'vitest';
import ValueInvestingPanel from '../ValueInvestingPanel';
import {useValueResearch} from '../useValueResearch';
import {aShareMarketApi} from '../../../api/aShareMarket';
import type {ValueResearchResult} from '../../../types/aShareValue';
import type {ValueSnapshot} from '../../../types/aShareValue';
import ValueAssumptionEditor from '../ValueAssumptionEditor';
vi.mock('../../../api/aShareMarket',()=>({aShareMarketApi:{getValue:vi.fn(),prepareValue:vi.fn(),generateValue:vi.fn()}}));
beforeEach(()=>vi.clearAllMocks());

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
