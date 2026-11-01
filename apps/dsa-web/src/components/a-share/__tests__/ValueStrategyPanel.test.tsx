import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {it,expect,vi} from 'vitest';
import ValueStrategyPanel from '../ValueStrategyPanel';
import ValueAssumptionEditor from '../ValueAssumptionEditor';
import type {ValueStrategy,ValueSnapshot} from '../../../types/aShareValue';

it('shows sourced company drivers, proxy limitations, reference inversion and pending forward checks on one page',()=>{
 const strategy={economics:{metrics:{roe:{label:'平均权益ROE',value:.12,unit:'ratio',period:'2026-09-30',formula:'归母利润/平均权益',fact_ids:['F1'],limitation:'期内发行需加权复核'}},flags:[],limitation:'不代表已审计结论'},company_drivers:{state:'historical_projection',origin:'company_history',history:[],growth_range:{median:.1,n:4},sources:['F1'],projections:[{scenario:'base',revenue_growth:.1,years:[{period:'2027-09-30',revenue:100,net_profit:10,operating_cashflow:15,capex:5}]}],limitation:'历史投影不是AI预测'},economic_checks:[{message:'增长和再投资需核查'}],gaps:[{kind:'assumption',item:'未来量价假设尚未建立'}],method_guidance:[{method:'fcff',reason:'核查经营口径'}],expectations:{state:'unreachable',method:'ddm',scenario:'base',input_price:100,bracket:[0,3],parameter:'dividend_scale',price_basis:'reference_input',reference_origin:'reference_sensitivity_v1',reason:'资金约束内无解',limitation:'不是真实市场共识'},monitoring:{rules:[],signals:[],forward_checks:[{metric:'revenue',period:'2027-09-30',state:'pending',forecast:100,actual:null,reason:'尚未到期'}],portfolio:{state:'unavailable',reason:'账户未配置'},next_review:'2027-02-01',limitation:'不自动交易'}} as unknown as ValueStrategy;
 render(<ValueStrategyPanel strategy={strategy}/>);
 expect(screen.getByRole('region',{name:'经营底稿与持有复核'})).toBeInTheDocument();
 expect(screen.getByText('12.0%')).toBeInTheDocument();
 expect(screen.getByText('历史投影不是AI预测')).toBeInTheDocument();
 expect(screen.getByText('期内发行需加权复核')).toBeInTheDocument();
 expect(screen.getByText('资金约束内无解')).toBeInTheDocument();
 expect(screen.getByText(/输入不复权价格：100元/)).toBeInTheDocument();
 expect(screen.getByText(/搜索范围：0.000—3.000倍/)).toBeInTheDocument();
 expect(screen.getByText('规则参数参考输入')).toBeInTheDocument();
 expect(screen.getByText('尚未到期')).toBeInTheDocument();
 expect(screen.getByText(/未来量价假设尚未建立/)).toBeInTheDocument();
});

it('saves an explicit monitoring threshold with sources and future period without inventing a zero',async()=>{
 const snapshot={code:'605499',snapshot_id:'s',economic_model:{allowed_methods:['ddm']},financial_view:{ttm:{},latest:{},annual:[]},evidence:[{id:'F1',source:'公司原文'}],events:[],peers:{candidates:[]}} as unknown as ValueSnapshot;
 const save=vi.fn().mockResolvedValue({});
 render(<ValueAssumptionEditor snapshot={snapshot} busy={false} onSave={save}/>);
 fireEvent.change(screen.getByLabelText('假设的基础资料'),{target:{value:'F1'}});
 fireEvent.click(screen.getByRole('button',{name:'添加经营复核条件'}));
 expect(screen.getByLabelText('复核阈值 1')).toHaveValue(null);
 fireEvent.change(screen.getByLabelText('复核阈值 1'),{target:{value:'80'}});
 fireEvent.change(screen.getByLabelText('复核目标期间 1'),{target:{value:'2027-09-30'}});
 fireEvent.change(screen.getByLabelText('复核说明 1'),{target:{value:'营收低于假设时重新研究'}});
 fireEvent.click(screen.getByRole('button',{name:'保存草案（不调用AI）'}));
 await waitFor(()=>expect(save).toHaveBeenCalledOnce());
 const r=save.mock.calls[0][0].monitor_rules[0];
 expect(r.threshold).toBe(80);expect(r.target_period).toBe('2027-09-30');expect(r.sources).toEqual(['F1']);
 expect(save.mock.calls[0][1]).toBe(false);
});
