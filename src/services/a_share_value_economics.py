"""Sourced financial diagnostics; proxies are never reported accounting facts."""
from math import isfinite

FINANCIAL={'bank','life_insurance','nonlife_insurance','securities','asset_management','leasing'}
DEBT=('short_debt','long_debt','bonds','lease_liabilities','noncurrent_due_within_year')


def amounts(group, names, period=None):
    rows=[group.get(k) or {} for k in names]
    if not rows or any(not isinstance(f.get('value'),(int,float)) or isinstance(f.get('value'),bool)
        or not isfinite(f['value']) or f.get('unit')!='CNY' or not f.get('fact_ids') for f in rows):return None
    if any(any(f.get(k)!=rows[0].get(k) for k in ('period','vendor','scope')) for f in rows):return None
    if period and rows[0].get('period')!=period:return None
    if rows[0].get('scope')!='consolidated':return None
    for name,f in zip(names,rows):
        expected='parent_common' if name in ('net_profit','parent_equity') else 'minority' if name=='minority_equity' else 'all_claims'
        if f.get('attribution')!=expected:return None
    return rows


def build_economic_analysis(view, model):
    metrics={};flags=[];period=view.get('latest_period');ttm=view.get('ttm',{});latest=view.get('latest',{})
    prior_period=str(int(period[:4])-1)+period[4:] if period else ''
    prior=next((r['metrics'] for r in view.get('periods',view.get('annual',[])) if r['period']==prior_period),{})
    def store(key,label,rows,formula,calculate,unit='ratio',limitation='',industrial=False):
        reason='';value=None
        if industrial and model in FINANCIAL:reason='金融企业的现金流与资本定义不同，不套普通经营企业指标'
        elif not rows:reason='缺少同期间、同来源主体及单位的必要字段'
        else:
            try:
                value=calculate([f['value'] for f in rows])
                if not isfinite(value):raise ValueError()
            except (ValueError,ZeroDivisionError,TypeError):value=None;reason='分母非正或输入不适合该指标'
        metrics[key]=dict(label=label,value=value,unit=unit,period=period,formula=formula,
            vendor=rows[0].get('vendor') if rows else None,
            fact_ids=list(dict.fromkeys(i for f in rows or [] for i in f['fact_ids'])),reason=reason,limitation=limitation)
        return value
    def ratio(a,b):
        if b<=0:raise ValueError()
        return a/b
    store('cash_conversion','合并现金转化率',amounts(ttm,['operating_cashflow','total_net_profit'],period),
        '合并CFO / 合并净利润',lambda x:ratio(*x),industrial=True,
        limitation='需与债权、利息和营运资本变动共同分析；不代表可分配现金')
    store('cash_surplus_proxy','经营现金减总资本开支代理',amounts(ttm,['operating_cashflow','capex'],period),
        '合并CFO-capex',lambda x:x[0]-x[1],unit='CNY',industrial=True,
        limitation='不是严格FCFE；未桥接融资现金费用、少数股东、净融资和非经营资产')
    store('operating_margin','报表营业利润率',amounts(ttm,['operating_profit','revenue'],period),
        '营业利润 / 营业总收入',lambda x:ratio(*x),industrial=True,limitation='营业利润不是EBIT，不能直接送入DCF的EBIT率')
    store('gross_margin','毛利率代理',amounts(ttm,['revenue','operating_cost'],period),
        '(营业总收入-营业成本) / 营业总收入',lambda x:ratio(x[0]-x[1],x[0]),industrial=True,
        limitation='总收入含其他业务时须核对分部与成本口径')
    eq=amounts(latest,['parent_equity'],period);old=amounts(prior,['parent_equity'],prior_period)
    ni=amounts(ttm,['net_profit'],period)
    valid_eq=eq and old and ni and eq[0].get('vendor')==old[0].get('vendor')==ni[0].get('vendor')
    store('roe','平均普通股权益ROE',ni+eq+old if valid_eq else None,
        'TTM归母利润 / ((同期初归母权益+期末归母权益)/2)',lambda x:ratio(x[0],(x[1]+x[2])/2),
        limitation='期初期末均值近似；期内大额发行/回购仍须加权复核')
    ebit_rows=amounts(ttm,['operating_profit','finance_expense','investment_income','fair_value_income','asset_disposal_income','other_income'],period)
    ebit=store('normalized_ebit_proxy','剔除部分非经营项EBIT代理',ebit_rows,
        '营业利润+财务费用-投资收益-公允价值变动-资产处置-其他收益',
        lambda x:x[0]+x[1]-sum(x[2:]),unit='CNY',industrial=True,
        limitation='经营EBIT代理；仍需核查信用减值、一次项、研发资本化和非经营项目，不是审计确认正常化EBIT')
    tax_rows=amounts(ttm,['income_tax','total_profit'],period)
    tax=store('effective_tax','报表有效税率',tax_rows,'所得税费用 / 利润总额',lambda x:ratio(*x),industrial=True,
        limitation='会计费用率，不等于未来现金税率')
    caps=[]
    for group,p in [(prior,prior_period),(latest,period)]:
        rows=amounts(group,['parent_equity','minority_equity',*DEBT,'cash'],p)
        caps.append(rows)
    capital_ok=all(caps) and caps[0][0].get('vendor')==caps[1][0].get('vendor')
    cap_rows=caps[0]+caps[1] if capital_ok else None
    def average_capital(x):
        middle=len(x)//2
        return (sum(x[:middle-1])-x[middle-1]+sum(x[middle:-1])-x[-1])/2
    capital=store('invested_capital_proxy','平均投入资本代理',cap_rows,
        '期初期末平均(归母权益+少数权益+列示有息债务-货币资金)',average_capital,unit='CNY',industrial=True,
        limitation='全额减货币资金；最低经营现金、受限资金、超额现金和遗漏索取权须另行核实')
    same_vendor=ebit_rows and tax_rows and cap_rows and ebit_rows[0].get('vendor')==tax_rows[0].get('vendor')==cap_rows[0].get('vendor')
    roic_rows=(ebit_rows or [])+(tax_rows or [])+(cap_rows or []) if same_vendor and ebit is not None and tax is not None and capital is not None else None
    def roic(_):
        if not 0<=tax<=1:raise ValueError()
        return ratio(ebit*(1-tax),capital)
    store('roic_proxy','税后经营资本回报代理',roic_rows,'EBIT代理*(1-有效税率) / 平均投入资本代理',roic,
        industrial=True,limitation='代理指标，不是已正常化ROIC；不能单独作为增值或安全买入依据')
    store('receivable_days_proxy','应收账款周转天数代理',amounts(latest,['receivables'],period)+amounts(ttm,['revenue'],period)
        if amounts(latest,['receivables'],period) and amounts(ttm,['revenue'],period) and latest['receivables'].get('vendor')==ttm['revenue'].get('vendor') else None,
        '期末应收账款 / TTM收入 *365',lambda x:ratio(x[0],x[1])*365,unit='days',industrial=True,
        limitation='使用期末而非平均余额，未包括票据和其他应收，需结合账龄')
    cfo=ttm.get('operating_cashflow',{}).get('value');profit=ttm.get('total_net_profit',{}).get('value')
    if metrics['cash_conversion']['value'] is not None and profit>0 and cfo<0:
        flags.append(dict(code='cash_profit_divergence',message='合并盈利为正而经营现金流为负，需核查回款与营运资本',sources=metrics['cash_conversion']['fact_ids']))
    for key in ('receivables','inventory'):
        cur=amounts(latest,[key],period);prev=amounts(prior,[key],prior_period)
        rev=amounts(latest,['revenue'],period)
        if model not in FINANCIAL and cur and prev and prev[0]['value']>0 and rev:
            old=amounts(prior,['revenue'],prior_period);old_revenue=old[0] if old else None
            if (old_revenue and old_revenue['value']>0 and old_revenue.get('period_basis')==rev[0].get('period_basis')
                and old_revenue.get('vendor')==rev[0].get('vendor')==cur[0].get('vendor')==prev[0].get('vendor')):
                asset_growth=cur[0]['value']/prev[0]['value']-1;revenue_growth=rev[0]['value']/old_revenue['value']-1
                if asset_growth-revenue_growth>.1:flags.append(dict(code=key+'_growth',message=('应收' if key=='receivables' else '存货')+'增幅超过同期收入10个百分点，需复核质量而非直接判定造假',sources=cur[0]['fact_ids']+prev[0]['fact_ids']+rev[0]['fact_ids']+old_revenue['fact_ids']))
    return dict(metrics=metrics,flags=flags,model=model,
        limitation='描述性诊断与待核对代理值，不合成为盈利概率；空风险列表不表示已完成全面审计')
