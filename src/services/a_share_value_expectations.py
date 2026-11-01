"""One-dimensional conditional inversion, never an inferred market consensus."""
from copy import deepcopy
from src.services.a_share_value_valuation import evaluate_method,number


def reverse_value(case,view,price,price_basis,context=None):
    bridge=case.get('capital_bridge')
    reference=case.get('parameter_origin') or ('reference_sensitivity_v1' if isinstance(bridge,dict) and bridge.get('basis')=='reference_sensitivity' else None)
    out=dict(state='unavailable',method=case.get('method'),scenario=case.get('scenario'),reference_origin=reference,
        price_basis='reference_input' if reference else 'verified_quote_input' if price_basis.get('valid') else 'unverified_input',
        held_assumptions='其他经营、资本、折现率、长期增长、债务及索取权固定；仅求一个参数',
        limitation='条件反推试算，不识别真实市场共识、概率或推荐价；无唯一/可行解时保留未知',reason='')
    try:target=number(price,'输入价格',1e-12)
    except ValueError:return out|dict(reason='缺少有效输入价格')
    out['input_price']=target
    method=case.get('method')
    context=context or {}
    baseline=evaluate_method(method,case,view,context)
    if baseline['state']!='ready':return out|dict(reason='当前基准情景不可计算：'+'；'.join(baseline.get('missing',[])))
    out['baseline_value']=baseline['value_per_share']
    if method in ('fcff','fcfe'):parameter,lo,hi='growth_shift',-.2,.3
    elif method=='ddm':parameter,lo,hi='dividend_scale',0.,3.
    elif method=='rim':parameter,lo,hi='roe_shift',-.15,.15
    elif method=='nav':parameter,lo,hi='asset_scale',0.,3.
    else:return out|dict(reason='没有可适用的估值方法')
    out.update(parameter=parameter,bracket=[lo,hi])
    def value(x):
        c=deepcopy(case)
        try:
            if method in ('fcff','fcfe'):
                for row in c['operating']['years']:row['growth']+=x
            elif method=='ddm':
                c['dividends']=[v*x for v in c['dividends']];c['terminal_dividend']*=x
            elif method=='rim':
                for row in c['years']:row['roe']+=x
            else:
                for row in c['assets']:row['value']*=x
            r=evaluate_method(method,c,view,context)
            return r['value_per_share'] if r['state']=='ready' else None
        except (KeyError,TypeError,ValueError,OverflowError):return None
    points=[(lo+(hi-lo)*i/32,value(lo+(hi-lo)*i/32)) for i in range(33)]
    valid=[(x,y) for x,y in points if y is not None]
    if len(valid)<2:return out|dict(reason='数学/资本约束不足，不能反推')
    differences=[b[1]-a[1] for a,b in zip(valid,valid[1:])]
    if max(differences,default=0)<=1e-10:return out|dict(reason='参数变化不能识别正向价格关系')
    if any(d<-1e-8 for d in differences):return out|dict(state='non_identifiable',reason='区间内非单调，不能报告唯一隐含参数')
    bracket=next(((a,b) for a,b in zip(valid,valid[1:]) if a[1]<=target<=b[1]),None)
    if not bracket:return out|dict(state='unreachable',reason='在当前固定假设及资金/股本约束内，输入价格没有可行解')
    left,right=bracket[0][0],bracket[1][0]
    for _ in range(45):
        mid=(left+right)/2;y=value(mid)
        if y is None:return out|dict(state='unreachable',reason='求解经过不可行资金/资本区间，不发布结果')
        if abs(y-target)<max(1e-7,target*1e-7):return out|dict(state='solved',solution=mid,reproduced_price=y)
        if y<target:left=mid
        else:right=mid
    return out|dict(state='unreachable',reason='求解未收敛')
