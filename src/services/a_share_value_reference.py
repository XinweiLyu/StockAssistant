"""Editable sensitivity parameters, never an AI conclusion or safe price."""
import re
from datetime import date
from src.services.a_share_value_valuation import number, evaluate_value
from src.schemas.a_share_value import ValueAssumptions


def build_value_reference(s):
    try:
        if s.get('economic_model',{}).get('model')!='operating' or not s.get('binding',{}).get('eligibility',{}).get('eligible'):
            raise ValueError('参考试算仅适用于证券资格合格、可辨认的稳定经营企业')
        view=s['financial_view'];ids={f['fact_id'] for f in s.get('facts',[])}|{e['id'] for e in s.get('evidence',[])}
        period=date.fromisoformat(view.get('latest_period',''))
        age=(date.fromisoformat(s['cutoff'][:10])-period).days
        if not 0<=age<=400: raise ValueError('最新财务期间过旧或在未来，不生成当前参考试算')
        sources=[]
        def fact(group,metric,positive=False):
            f=group.get(metric) or {}
            if f.get('unit')!='CNY' or f.get('period')!=period.isoformat() or not f.get('fact_ids') or not set(f['fact_ids'])<=ids:
                raise ValueError(metric+'缺少当前可核对的金额及来源，未填0')
            sources.extend(f['fact_ids'])
            return number(f.get('value'),metric,1e-12 if positive else 0)
        profit=fact(view.get('ttm',{}),'net_profit',True)
        cfo=fact(view.get('ttm',{}),'operating_cashflow',True)
        capex=fact(view.get('ttm',{}),'capex')
        interest=fact(view.get('ttm',{}),'interest_expense')
        minority=fact(view.get('latest',{}),'minority_equity')
        treasury_cost=fact(view.get('latest',{}),'treasury_share_cost')
        cap=view.get('current_capital') or {}
        if not cap.get('fact_ids') or not set(cap['fact_ids'])<=ids:
            raise ValueError('当前总股本缺少来源')
        shares=number(cap.get('value'),'总股数',1e-12);sources.extend(cap['fact_ids'])
        if not any(d.get('status')=='implemented' and isinstance(d.get('cash_per_share'),(int,float))
                   and d['cash_per_share']>0 for d in s.get('distributions',[])):
            raise ValueError('没有已实施现金分红记录，不自动套用股利参考')
        treasury=0
        if treasury_cost==0 and any(e.get('code')==s['code'] and e.get('source')=='cninfo' and e.get('kind')=='buyback'
            and period.isoformat()<(e.get('published_at') or '')<=s['cutoff'] for e in s.get('events',[])):
            raise ValueError('零库存股报表之后存在回购披露，须重新核实股数，不能自动沿用0')
        if treasury_cost>0:
            found=False
            for e in sorted(s.get('events',[]),key=lambda e:e.get('published_at',''),reverse=True):
                if (e.get('code')!=s['code'] or e.get('source')!='cninfo' or e.get('id') not in ids
                    or e.get('kind')!='buyback' or e.get('text_status')!='ready'
                    or not e.get('published_at') or e['published_at']>s['cutoff']): continue
                text=re.sub(r'\s+','',e.get('text',''))
                q=re.search(r'累计已回购[Aa]?股股数([\d,]+(?:\.\d+)?)(万)?股',text)
                cost=re.search(r'累计已回购[Aa]?股金额([\d,]+(?:\.\d+)?)(万)?元',text)
                if not q or not cost: continue
                qty=float(q[1].replace(',',''))*(10000 if q[2] else 1)
                paid=float(cost[1].replace(',',''))*(10000 if cost[2] else 1)
                if not 0<qty<shares or abs(paid-treasury_cost)>treasury_cost*.01: continue
                treasury=qty;sources.append(e['id']);found=True;break
            if not found: raise ValueError('库存股账面成本为正，但未取得可与其核对的公开回购数量与金额')
        policies=[('conservative',.12,0,0,.75,.50),('base',.10,.025,.03,.90,.65),('upside',.08,.04,.06,1.,.80)]
        cases=[];parameters=[];sources=list(dict.fromkeys(sources))
        for scenario,discount,g,growth,haircut,payout in policies:
            rows=[];dividends=[];minimum=round(cfo*haircut*.1,2)
            for y in range(1,7):
                scale=(1+growth)**min(y,5)*((1+g) if y==6 else 1)
                earnings=round(profit*scale,2);operating=round(cfo*haircut*scale,2);investment=round(capex*scale,2)
                finance=round(interest*1.2*scale,2);reserve=round(minority*scale,2)
                free=round(operating-investment-finance-reserve,2)
                # Leave an explicit operating reserve; never bridge a funding
                # deficit by inventing net borrowing or current usable cash.
                dividend=round(min(earnings*payout,free-(minimum if y==1 else 0)),2)
                if dividend<=0: raise ValueError('压力后的经营现金不足分红和经营储备，不生成参考价')
                if y<=5:
                    rows.append(dict(new_shares=0,issuance_cash=0,repurchased_shares=0,repurchase_cash=0,
                        cancelled_shares=0,treasury_reissued_shares=0,treasury_reissue_cash=0,
                        operating_cashflow=operating,capex=investment,net_debt_financing=0,earnings=earnings,
                        financing_cash_costs=finance,minority_distributions=reserve))
                    dividends.append(dividend)
            bridge=dict(basis='reference_sensitivity',sources=sources,rationale='软件参考参数；不是公司承诺、AI预测或已核实未来',
                timing='actions_before_dividend',initial_treasury_shares=treasury,opening_available_cash=0,
                minimum_cash=minimum,terminal_capital_stable=True,terminal_earnings=earnings,
                terminal_operating_cashflow=operating,terminal_capex=investment,terminal_financing_cash_costs=finance,
                terminal_minority_distributions=reserve,years=rows)
            cases.append(dict(method='ddm',scenario=scenario,discount=discount,terminal_growth=g,shares=shares,
                fixed_capital=False,capital_feasible=True,dividends=dividends,terminal_dividend=dividend,
                capital_bridge=bridge,evidence_ids=sources,parameter_origin='reference_sensitivity_v1',
                start_date=s['cutoff'][:10],rationale=f'软件参数敏感性：折现率{discount:.1%}、经营增长{growth:.1%}、现金流系数{haircut:.0%}、目标分红率{payout:.0%}；未核实续贷和未来资本计划'))
            parameters.append(dict(scenario=scenario,discount=discount,growth=growth,terminal_growth=g,cash_factor=haircut,payout=payout))
        assumptions=ValueAssumptions(code=s['code'],snapshot_id=s['snapshot_id'],confirmed=False,primary_method='ddm',cases=cases).model_dump()
        report=evaluate_value(assumptions,s)
        if any(c['state']!='ready' for c in report['valuation_cases']):
            raise ValueError('参考参数未通过股本或现金一致性校验')
        return dict(state='ready',label='可编辑的股利参数试算，不是AI完整估值',assumptions=assumptions,
            report=report,parameters=parameters,limitations=[
                '增长、折现率、现金流折扣和分红率是软件敏感性参数，不是公司指引或已验证预测。',
                '仅采用未来经营回款，不依赖期初存量现金；融资费用按TTM利息费用的1.2倍、少数权益全额作年度现金风险准备，均是压力假设。',
                '假设未来债务净融资为0且无新增资本行动，不证明续贷、最低经营现金、回购或激励安排已核实。',
                '库存股按与账面成本接近的最近公开累计回购数量作参考，未确认注销、激励分配及其后变动；不发布安全价或潜在收益。'])
    except (ValueError,KeyError,TypeError,OverflowError) as exc:
        return dict(state='unavailable',missing=[str(exc) if isinstance(exc,ValueError) else '财务资料结构不足，未生成参考试算'])
