"""Company-specific evidence and economic checks, not an automatic buy signal."""
from statistics import median,quantiles
from src.services.a_share_value_economics import build_economic_analysis,amounts,FINANCIAL
from src.services.a_share_value_holding import add_months


def company_drivers(view,model):
    annual=sorted(view.get('annual',[]),key=lambda r:r['period'])[-6:]
    samples=[];history=[];sources=[]
    for index,row in enumerate(annual):
        p=row['period'];m=row['metrics'];out=dict(period=p)
        for k in ('revenue','net_profit','operating_profit','operating_cashflow','capex'):
            f=amounts(m,[k],p)
            if f:out[k]=f[0]['value'];sources+=f[0]['fact_ids']
        history.append(out)
        if index:
            before=annual[index-1];a=amounts(m,['revenue'],p);b=amounts(before['metrics'],['revenue'],before['period'])
            if (a and b and b[0]['value']>0 and int(p[:4])-int(before['period'][:4])==1
                and a[0]['vendor']==b[0]['vendor']):samples.append(a[0]['value']/b[0]['value']-1)
            else:samples=[]
    result=dict(origin='company_history',state='insufficient',history=history,sources=list(dict.fromkeys(sources)),
        projections=[],growth_range=None,reason='',limitation='历史锚点投影，非AI预测/概率区间；未来量价、竞争、资本效率和融资须另行论证')
    if model in FINANCIAL or model in ('cyclical','early_stage','unresolved'):
        return result|dict(reason='该经济模型需专属周期/资本或业务驱动，不外推通用经营现金路径')
    if len(samples)<3:return result|dict(reason='至少需要3个连续可比年度收入增速样本，历史断点不跨年插值')
    q1,q2,q3=quantiles(samples,n=4,method='inclusive')
    result['growth_range']=dict(low=q1,median=q2,high=q3,n=len(samples),formula='同口径连续年度收入同比的Q1/中位数/Q3；不是未来概率')
    ttm=view.get('ttm',{});p=view.get('latest_period');rows=amounts(ttm,['revenue','net_profit','operating_cashflow','capex'],p)
    if not rows or rows[0]['value']<=0 or rows[1]['value']<=0 or rows[2]['value']<=0:
        return result|dict(reason='当前收入/盈利/现金或投资口径不足，亏损/现金消耗不按稳定经营投影')
    result['sources']=list(dict.fromkeys(result['sources']+[i for f in rows for i in f['fact_ids']]))
    base={k:ttm[k]['value'] for k in ('revenue','net_profit','operating_cashflow','capex')}
    for scenario,g in [('conservative',q1),('base',q2),('upside',q3)]:
        if not -.99<g<=1:return result|dict(projections=[],reason='历史增速过于极端，须核实并购/规模/主营断点后建立预测')
        years=[dict(period=add_months(p,y*12),**{k:v*(1+g)**y for k,v in base.items()}) for y in range(1,6)]
        result['projections'].append(dict(scenario=scenario,revenue_growth=g,
            assumption='保持当前归母利润/经营现金/总投资相对收入比例，以历史收入增速锚点推演；不证明利润率可持续',years=years))
    return result|dict(state='historical_projection')


def build_value_strategy(snapshot,assumptions=None,report=None,portfolio=None):
    s=snapshot;view=s.get('financial_view',{});a=assumptions or {};r=report or {}
    model=s.get('economic_model',{}).get('model','unresolved')
    economics=build_economic_analysis(view,model)
    gaps=[]
    if not view.get('current_capital'):gaps.append(dict(kind='fact',item='当前普通股总股本及经济权益股数待核对',blocks='每股估值和正式条件价'))
    if model=='unresolved':gaps.append(dict(kind='fact',item='主营/分部及经济模型尚未核实',blocks='模型选择'))
    if not a.get('cases'):gaps.append(dict(kind='assumption',item='尚无公司专属、待核对的未来经营/分配假设',blocks='正式数值研究；不是公司未披露未来承诺'))
    allowed=s.get('economic_model',{}).get('allowed_methods',[])
    for method in ('fcff','fcfe','rim','ddm','nav'):
        if method not in allowed:gaps.append(dict(kind='method',item=method+'不在当前经济模型适用方法中',blocks='仅该方法，不是资料缺失'))
    for key in ('cash_conversion','normalized_ebit_proxy','roic_proxy'):
        m=economics['metrics'][key]
        if m['value'] is None and model not in FINANCIAL:
            gaps.append(dict(kind='fact',item=m['label']+'：'+m['reason'],blocks='该诊断/适用方法；不自动禁止其他方法的附条件草案'))
    checks=[]
    for c in r.get('valuation_cases',[]):
        share=c.get('terminal_share')
        if isinstance(share,(int,float)) and share>.75:
            checks.append(dict(method=c.get('method'),scenario=c.get('scenario'),code='terminal_dependence',
                message=f'终值贡献{share:.1%}，高度依赖长期假设；75%为复核提示而非错误/概率阈值'))
    for case in a.get('cases',[]):
        if case.get('method') not in ('fcff','fcfe'):continue
        try:
            from src.services.a_share_value_valuation import project_operating_case
            projected=project_operating_case(case,view);t=projected['terminal_row'];g=case['terminal_growth']
            investment=t['capex']-t['da']+t['nwc']*g/(1+g)
            if t['nopat']<=0:raise ValueError()
            rate=investment/t['nopat']
            required_roic=g/rate if rate>0 else None
            checks.append(dict(method=case['method'],scenario=case.get('scenario'),code='growth_capital',
                reinvestment_rate=rate,implied_roic=required_roic,
                message='稳定增长与再投资需匹配；'+('正增长但净再投资不为正，须提供轻资产/效率改善依据' if g>0 and rate<=0 else '隐含资本回报是诊断，不是已验证未来ROIC')))
        except (ValueError,KeyError,TypeError,OverflowError):
            checks.append(dict(method=case.get('method'),scenario=case.get('scenario'),code='growth_capital_missing',message='经营桥接不足，无法复核增长/再投资/资本回报'))
    guidance=[dict(method=m,state='candidate',reason=('核查股利与真实分配能力，不能仅因DCF缺字段选DDM' if m=='ddm' else
        '核查同口径经营/资本输入；允许有来源的预测假设，未知现状不填0')) for m in allowed]
    return dict(version='value-strategy-v1',economics=economics,company_drivers=company_drivers(view,model),
        gaps=gaps,economic_checks=checks,method_guidance=guidance,
        limitation='派生底稿不是独立原始证据；引用仍需核查底层事实。不将诊断/历史投影合成为买入评分或盈利概率')
