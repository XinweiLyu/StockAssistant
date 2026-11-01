"""Event evidence changes assumptions, never appends a historical price reaction."""
from copy import deepcopy
from src.schemas.a_share_integrated import stamp
from src.services.a_share_value_valuation import number

RATIOS = {'growth', 'ebit_margin', 'da_ratio', 'capex_ratio', 'nwc_ratio', 'tax'}
AMOUNTS = {'after_tax_interest', 'net_borrowing', 'minority_cashflow'}


def _targets(case,field,change,years):
    method=case.get('method');structural=change.get('temporal_type')=='structural'
    if method in ('fcff','fcfe') and case.get('operating') and field in RATIOS|AMOUNTS:
        if field in AMOUNTS and method!='fcfe':raise ValueError('该金额输入只适用于FCFE')
        pairs=[(case['operating']['years'][y-1],field,y) for y in years]
        if structural:pairs.append((case['operating']['terminal'],field,'terminal'))
        return pairs,'ratio' if field in RATIOS else 'CNY'
    if method=='ddm' and field=='dividend':
        pairs=[(case['dividends'],y-1,y) for y in years]
        if structural:pairs.append((case,'terminal_dividend','terminal'))
        return pairs,'CNY'
    if method=='ddm' and field.startswith('capital.') and case.get('capital_bridge'):
        key=field.split('.',1)[1]
        share_fields={'new_shares','repurchased_shares','cancelled_shares','treasury_reissued_shares'}
        cash_fields={'issuance_cash','repurchase_cash','treasury_reissue_cash','operating_cashflow','capex',
            'net_debt_financing','earnings','financing_cash_costs','minority_distributions'}
        if key not in share_fields|cash_fields:raise ValueError('未支持的资本桥接字段')
        b=case['capital_bridge'];pairs=[(b['years'][y-1],key,y) for y in years]
        if structural:
            terminal='terminal_'+key
            if terminal not in b:raise ValueError('稳定期不支持该资本行动；单次发行/回购须在指定年份桥接')
            pairs.append((b,terminal,'terminal'))
        return pairs,'shares' if key in share_fields else 'CNY'
    if method=='rim' and field in ('roe','dividend','oci'):
        if structural and 5 not in years:raise ValueError('结构性RIM变更须覆盖第5年及其后剩余收益锚')
        return [(case['years'][y-1],field,y) for y in years],'ratio' if field=='roe' else 'CNY'
    if method=='nav' and field in ('asset','liability'):
        if change.get('temporal_type')!='one_off':raise ValueError('NAV按一次性明确资产/索取权重估，不假设通用衰减')
        group=case.get('assets' if field=='asset' else 'liabilities',[])
        rows=[r for r in group if r.get('id')==change.get('item_id')]
        if len(rows)!=1:raise ValueError('NAV项目须为当前唯一资产/索取权ID')
        return [(rows[0],'value','current')],'CNY'
    return [],None


def apply_driver_changes(snapshot, assumptions):
    s=snapshot.model_dump() if hasattr(snapshot,'model_dump') else snapshot
    a=assumptions.model_dump() if hasattr(assumptions,'model_dump') else assumptions
    cases=deepcopy(a.get('cases',[]));events={e.get('event_id') or e.get('id'):e for e in s.get('events',[])}
    ids=set(events)|{f['fact_id'] for f in s.get('facts',[])}|{e['id'] for e in s.get('evidence',[]) if e.get('id')}
    effects,rejected,used=[],[],set()
    for change in a.get('driver_changes',[]):
        try:
            event=events.get(change.get('event_id'))
            if not event or not stamp(event.get('published_at')) or stamp(event['published_at'])>stamp(s['cutoff']):
                raise ValueError('事件来源不存在、时间未知或尚未发生')
            family=event.get('family_id') or change['event_id'];field=change.get('field','')
            if change.get('already_in_baseline') is not False:raise ValueError('同族同驱动重复，或未确认基准是否已纳入')
            if not change.get('sources') or not set(change['sources'])<=ids or not change.get('rationale'):
                raise ValueError('缺少实际送达的引用及经营传导依据')
            years=change.get('years',[])
            if not years or any(type(y) is not int or not 1<=y<=5 for y in years):raise ValueError('事件须指定1至5年的作用期间')
            temporal=change.get('temporal_type','temporary')
            if temporal not in ('temporary','one_off','structural'):raise ValueError('事件须区分一次性、暂时或结构影响')
            if temporal=='one_off' and len(set(years))!=1:raise ValueError('一次性变更只指定一个作用年份')
            if temporal=='structural' and change.get('include_terminal') is not True:raise ValueError('结构影响须明确传导到稳定期')
            old,new=number(change.get('old'),'事件原值'),number(change.get('new'),'事件新值')
            half=number(change.get('half_life_years'),'事件半衰期',.01,100) if temporal=='temporary' else None
            updates=[];keys=[]
            for index,case in enumerate(cases):
                if change.get('method') and change['method']!=case.get('method'):continue
                if change.get('scenario') and change['scenario']!=case.get('scenario'):continue
                targets,unit=_targets(case,field,change,sorted(set(years)))
                if targets and change.get('unit')!=unit:raise ValueError('事件单位与所选估值方法字段不符')
                for parent,key,year in targets:
                    token=(family,field,change.get('item_id'),index,year)
                    if token in used:raise ValueError('同族同驱动重复作用于同一方法、情景和年份')
                    before=number(parent[key] if isinstance(parent,list) else parent.get(key),field)
                    expected=number(change.get('terminal_old'),'稳定期原值') if year=='terminal' else old
                    if abs(before-expected)>1e-9:raise ValueError('事件原值与所选情景基准不一致，请分别提供变更')
                    after=old+(new-old)*2**(-(year-min(years))/half) if temporal=='temporary' and isinstance(year,int) else new
                    updates.append((parent,key,after));keys.append(token)
                    if year=='terminal' and field=='growth':updates.append((case,'terminal_growth',new))
            if not updates:raise ValueError('当前方法无该经营/资本/资产驱动桥接，保留定性研究')
            for parent,key,value in updates:parent[key]=value
            used.update(keys)
            effects.append(dict(**change,family_id=family,applied_years=sorted(set(years)),
                note='变更后重跑估值与资金约束；不是历史股价反应。growth是增速变化，收入水平的累积效应须单独核查。'))
        except (ValueError,TypeError,KeyError,IndexError) as exc:
            rejected.append(dict(event_id=change.get('event_id'),reason=str(exc) if isinstance(exc,ValueError) else '事件输入结构不完整'))
    return dict(cases=cases,counterfactual=deepcopy(a.get('cases',[])),effects=effects,rejected=rejected)
