import {fireEvent,render,screen,within} from '@testing-library/react';
import {expect,it} from 'vitest';
import ValueInvestingPanel from '../ValueInvestingPanel';
import type {useValueResearch} from '../useValueResearch';
import type {ValueResearchResult} from '../../../types/aShareValue';

function result():ValueResearchResult {
 const peers={candidates:[],confirmed:[],excluded:[],metrics:{}};
 return {code:'605499',status:'ready',quote:{price:100,valid:false},snapshot:{code:'605499',snapshot_id:'s',cutoff:'2026-11-01',economic_model:{model:'operating',checklist:[],allowed_methods:['ddm']},facts:[],events:[],evidence:[],missing:[],peers,financial_view:{latest:{},ttm:{},annual:[],quality:{risks:[]},conflicts:[]}},review:{status:'partial'},reference:{state:'ready',report:{valuation_state:'reference',parameter_origin:'reference_sensitivity_v1',primary_method:'ddm',valuation_cases:['conservative','base','upside'].map(scenario=>({method:'ddm',scenario,state:'ready',value_per_share:80,missing:[]})),comparison:{margin:null,upside:null,conditional_price:null},peers,theses:[],missing:[],sensitivities:[],driver_effects:[],holding_cases:[]}}} as unknown as ValueResearchResult;
}
function panel(data:ValueResearchResult,code=data.code){
 return <ValueInvestingPanel code={code} state={{result:data,loading:false,busy:false} as ReturnType<typeof useValueResearch>} onRequestResearch={()=>undefined}/>;
}
const card=(name:string)=>within(screen.getByText(name,{exact:true}).closest('div')!);

it('shows signed reference arithmetic using a disclosed unverified cache price without publishing formal recommendations',()=>{
 const data=result();render(panel(data));
 expect(card('相对试算值的折价率').getByText('-25.0%')).toBeInTheDocument();
 expect(card('到试算值的价格差幅').getByText('-20.0%')).toBeInTheDocument();
 expect(card('要求折价对应价格（试算）').getByText('¥60.00')).toBeInTheDocument();
 expect(screen.getByText(/缓存价格日期未核实/)).toBeInTheDocument();
 expect(screen.getByLabelText('试算要求折价 %')).toHaveValue(25);
 expect(screen.queryByText('到保守价值的潜在涨幅')).not.toBeInTheDocument();
 expect(data.reference!.report!.comparison).toEqual({margin:null,upside:null,conditional_price:null});
});

it('updates each formula when inputs change, preserves a deliberate zero discount, and rejects missing or invalid inputs',()=>{
 const data=result();render(panel(data));
 fireEvent.change(screen.getByLabelText('试算基准价（元，不复权）'),{target:{value:'64'}});
 fireEvent.change(screen.getByLabelText('试算要求折价 %'),{target:{value:'0'}});
 expect(card('相对试算值的折价率').getByText('20.0%')).toBeInTheDocument();
 expect(card('到试算值的价格差幅').getByText('25.0%')).toBeInTheDocument();
 expect(card('要求折价对应价格（试算）').getByText('¥80.00')).toBeInTheDocument();
 expect(screen.getByText(/使用手动输入价格/)).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('试算基准价（元，不复权）'),{target:{value:'0'}});
 expect(card('相对试算值的折价率').getByText('请输入有效基准价')).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('试算基准价（元，不复权）'),{target:{value:''}});
 expect(card('到试算值的价格差幅').getByText('请输入有效基准价')).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('试算要求折价 %'),{target:{value:'90'}});
 expect(card('要求折价对应价格（试算）').getByText('请输入0–80%的折价比例')).toBeInTheDocument();
 expect(data.quote!.price).toBe(100);
});

it('calculates the discount price without a quote and does not substitute another method or missing valuation',()=>{
 const data=result();data.quote=undefined;
 const {rerender}=render(panel(data));
 expect(card('相对试算值的折价率').getByText('请输入有效基准价')).toBeInTheDocument();
 expect(card('要求折价对应价格（试算）').getByText('¥60.00')).toBeInTheDocument();
 data.reference!.report!.valuation_cases[0].method='fcff';
 rerender(panel(data));
 expect(card('要求折价对应价格（试算）').getByText('较保守试算值不可用')).toBeInTheDocument();
});

it('resets edited inputs when switching stocks and uses a saved zero margin without replacing it with the default',()=>{
 const data=result();const {rerender}=render(panel(data));
 fireEvent.change(screen.getByLabelText('试算基准价（元，不复权）'),{target:{value:'64'}});
 fireEvent.change(screen.getByLabelText('试算要求折价 %'),{target:{value:'40'}});
 const other=result();other.code='000807';other.snapshot!.code='000807';other.quote={price:200,valid:true,trade_date:'2026-10-30'};
 other.assumptions={code:other.code,snapshot_id:'s',revision:1,confirmed:false,primary_method:'ddm',cases:[],margin_required:0,peer_confirmations:[],driver_changes:[],holding_cases:[],theses:[],risk_review:{}};
 rerender(panel(other));
 expect(screen.getByLabelText('试算基准价（元，不复权）')).toHaveValue(200);
 expect(screen.getByLabelText('试算要求折价 %')).toHaveValue(0);
 expect(card('要求折价对应价格（试算）').getByText('¥80.00')).toBeInTheDocument();
});

it('does not activate stale or disputed reference values and preserves formal backend comparisons',()=>{
 const data=result();data.report={...data.reference!.report!,valuation_state:'stale'};data.reference=null;
 const {rerender}=render(panel(data));
 expect(screen.queryByLabelText('试算基准价（元，不复权）')).not.toBeInTheDocument();
 expect(screen.getByText('资料已变化，请先更新研究')).toBeInTheDocument();
 data.report.valuation_state='disputed';rerender(panel(data));
 expect(screen.getByText('试算情景存在争议，请先核对假设')).toBeInTheDocument();
 data.report.parameter_origin=null;data.report.valuation_state='conditional';
 data.report.comparison={margin:.2,upside:.25,conditional_price:60};rerender(panel(data));
 expect(card('对保守价值的安全边际').getByText('20.0%')).toBeInTheDocument();
 expect(card('到保守价值的潜在涨幅').getByText('25.0%')).toBeInTheDocument();
 expect(card('满足要求折价的条件参考上限').getByText('¥60.00')).toBeInTheDocument();
 expect(screen.queryByLabelText('试算基准价（元，不复权）')).not.toBeInTheDocument();
});

it('tracks refreshed quotes until a manual override and resets that override on a new snapshot or report revision',()=>{
 const data=result();const {rerender}=render(panel(data));
 data.quote={price:64,valid:true,trade_date:'2026-10-30'};rerender(panel(data));
 expect(card('相对试算值的折价率').getByText('20.0%')).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('试算基准价（元，不复权）'),{target:{value:'40'}});
 data.quote.price=100;rerender(panel(data));
 expect(screen.getByLabelText('试算基准价（元，不复权）')).toHaveValue(40);
 data.snapshot!.snapshot_id='new';rerender(panel(data));
 expect(screen.getByLabelText('试算基准价（元，不复权）')).toHaveValue(100);
 fireEvent.change(screen.getByLabelText('试算要求折价 %'),{target:{value:'40'}});
 data.reference!.report!.assumptions_revision=2;rerender(panel(data));
 expect(screen.getByLabelText('试算要求折价 %')).toHaveValue(25);
});

it('explains unavailable formal comparisons instead of showing unexplained dashes or recomputing from unverified quotes',()=>{
 const data=result();data.report={...data.reference!.report!,parameter_origin:null,valuation_state:'draft'};data.reference=null;
 data.report.comparison.reason='当前报价日期待核实';render(panel(data));
 expect(card('对保守价值的安全边际').getByText('暂不可计算')).toBeInTheDocument();
 expect(card('对保守价值的安全边际').getByText('当前报价日期待核实')).toBeInTheDocument();
 expect(card('到保守价值的潜在涨幅').getByText('当前报价日期待核实')).toBeInTheDocument();
 expect(card('满足要求折价的条件参考上限').getByText('暂停发布')).toBeInTheDocument();
 expect(screen.queryByLabelText('试算基准价（元，不复权）')).not.toBeInTheDocument();
});

it('allows arithmetic for a ready conservative reference even if another scenario is incomplete',()=>{
 const data=result();data.reference!.report!.valuation_state='research_only';
 data.reference!.report!.valuation_cases[1].state='missing';
 render(panel(data));
 expect(card('相对试算值的折价率').getByText('-25.0%')).toBeInTheDocument();
 expect(card('要求折价对应价格（试算）').getByText('¥60.00')).toBeInTheDocument();
});

it('rejects sub-cent prices and never formats overflowing arithmetic as infinity',()=>{
 const data=result();const {rerender}=render(panel(data));
 fireEvent.change(screen.getByLabelText('试算基准价（元，不复权）'),{target:{value:'1e-320'}});
 expect(card('到试算值的价格差幅').getByText('请输入有效基准价')).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('试算基准价（元，不复权）'),{target:{value:'0.01'}});
 data.reference!.report!.valuation_cases[0].value_per_share=1e308;rerender(panel(data));
 expect(card('到试算值的价格差幅').getByText('计算结果超出范围，请核对输入')).toBeInTheDocument();
 expect(screen.queryByText(/Infinity|NaN/)).not.toBeInTheDocument();
});
