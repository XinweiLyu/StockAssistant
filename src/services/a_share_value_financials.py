"""Comparable financial periods with explicit provenance and coverage."""
from collections import defaultdict
from datetime import date,timedelta
from src.schemas.a_share_integrated import stamp
from src.schemas.a_share_value import ValueFact


def build_financial_view(facts, cutoff):
    cutoff = stamp(cutoff)
    groups = defaultdict(list)
    excluded, capital = [], []
    for item in facts:
        try:
            f = ValueFact.model_validate(item).model_dump()
        except ValueError:
            excluded.append(dict(fact_id=item.get('fact_id'),reason='事实字段/单位/股本时点合同不合格'))
            continue
        if f['metric'] == 'current_shares':
            if f['available_at'] <= cutoff and f['period_end'] <= cutoff[:10] and f['scope'] == 'consolidated' and not f['conflicts']:
                capital.append(f)
            continue
        current_observation=(f.get('market') in ('us','hk') and f['vintage_quality']=='latest_reconstructed'
            and stamp(f['observed_at'])<=cutoff and stamp(f['available_at'])==stamp(f['observed_at']))
        if stamp(f['available_at']) > cutoff or f['period_end'] > cutoff[:10] or f['scope'] != 'consolidated' or (not f['published_at'] and not current_observation):
            excluded.append(dict(fact_id=f['fact_id'], reason='未在截止时可用或报表口径/公告时间未核实'))
            continue
        groups[(f['metric'], f['report_period'])].append(f)
    selected, conflicts,segments = {}, [],[]
    def record(values):
        v=values[0]
        return dict(value=v['value'],unit=v['unit'],period=v['report_period'],period_basis=v['period_basis'],
            period_start=v.get('period_start'),currency=v['currency'],scope=v['scope'],attribution=v['attribution'],
            vendor=v['source'].split('/')[0],fact_ids=[f['fact_id'] for f in values],formula='reported',
            user_attested=any(f['vintage_quality']=='user_attested' for f in values))
    for key, values in groups.items():
        for basis in ('quarter','half_year'):
            subset=[v for v in values if v['period_basis']==basis]
            signatures={(v['value'],v['unit'],v['scope'],v['attribution'],v['currency'],v.get('period_start')) for v in subset}
            if subset and len(signatures)==1 and not any(v['conflicts'] for v in subset):segments.append((key[0],record(subset)))
        # Annual/YTD and a standalone last quarter may share an end date.
        # Prefer the widest documented period rather than adding overlapping flows.
        rank={'annual':4,'ytd':3,'half_year':2,'quarter':1,'instant':0}
        chosen=max(rank[v['period_basis']] for v in values)
        values=[v for v in values if rank[v['period_basis']]==chosen]
        signatures = {(v['value'], v['unit'], v['period_basis'], v['scope'], v['attribution'],v['currency'],v.get('period_start')) for v in values}
        if len(signatures) != 1 or any(v['conflicts'] for v in values):
            conflicts.append(dict(metric=key[0], period=key[1], fact_ids=[v['fact_id'] for v in values], reason='数值或期间/主体口径冲突'))
            continue
        selected[key]=record(values)
    # Later DEI/cover-page share observations are capital dates, not a new
    # income/cash-flow statement period. Preserve them in periods, not the anchor.
    latest_period = max((p for (_,p),v in selected.items() if v['unit'] not in ('shares','ratio','multiple')), default=None)
    latest = {metric: v for (metric, period), v in selected.items() if period == latest_period}
    years = sorted({period for (_,period),v in selected.items() if v['period_basis']=='annual'})[-10:]
    annual = [dict(period=period, metrics={metric: v for (metric, p), v in selected.items()
                if p == period and v['period_basis'] in ('annual', 'instant')}) for period in years]
    periods=[dict(period=period,metrics={metric:v for (metric,p),v in selected.items() if p==period})
        for period in sorted({p for _,p in selected})]
    ttm = financial_ttm(selected,segments,latest_period)
    risks = []
    if latest.get('net_profit', {}).get('value', 0) < 0:
        risks.append('归母利润为负，不适用正PE比较')
    if latest.get('parent_equity', {}).get('value', 1) <= 0:
        risks.append('普通股账面权益非正，PB/RIM需另行重估')
    if len(annual) < 5:
        risks.append('完整年度不足5年，无法声称覆盖完整经营周期')
    current = max(capital, key=lambda f: f['available_at']) if capital else None
    if current:
        same_period = [f for f in capital if f['period_end'] == current['period_end']]
        if len({(f['value'], f['unit']) for f in same_period}) != 1:
            conflicts.append(dict(metric='current_shares', period=current['period_end'],
                fact_ids=[f['fact_id'] for f in same_period], reason='当前股本来源冲突，不能静默覆盖'))
            current = None
    from src.services.a_share_value_context import normalized_history
    normalization = normalized_history(annual, ttm.get('revenue', {}).get('value'))
    currencies={f['currency'] for f in facts if f.get('unit') not in ('shares','ratio','multiple')}
    return dict(currency=next(iter(currencies)) if len(currencies)==1 else None,flow_segments=[dict(metric=m,**v) for m,v in segments],latest_period=latest_period, latest=latest, annual=annual, periods=periods,ttm=ttm, normalization=normalization,
        current_capital=dict(value=current['value'], period=current['period_end'], available_at=current['available_at'],
            fact_ids=[current['fact_id']], unit='shares') if current else None,
        conflicts=conflicts, excluded=excluded, quality=dict(risks=risks, cash_profit_ratio=None,
            cash_profit_reason='合并CFO与归母利润主体不同，不标为严格现金转化率',
            years=len(annual), vintage='当前修订数据；不可作为历史当时已知财报'))


def financial_ttm(selected,segments,period):
    """Normalize the same fiscal intervals for capture and later monitoring."""
    latest={m:v for (m,p),v in selected.items() if p==period}
    ttm = {}
    for metric, value in latest.items():
        if value['period_basis'] == 'annual':
            ttm[metric] = value
        elif value['period_basis'] == 'ytd':
            year=int(value['period'][:4])-1
            prev=selected.get((metric,str(year)+value['period'][4:]))
            if not prev and value.get('period_start'):
                # 52/53-week fiscal calendars shift the month/day. Match both
                # interval endpoints within one fortnight, never arbitrary YTD.
                candidates=[v for (m,_),v in selected.items() if m==metric and v['period_basis']=='ytd'
                    and v.get('period_start') and 350<=(date.fromisoformat(value['period'])-date.fromisoformat(v['period'])).days<=380
                    and 350<=(date.fromisoformat(value['period_start'])-date.fromisoformat(v['period_start'])).days<=380]
                if len(candidates)==1:prev=candidates[0]
            before=value.get('period_start') or value['period'][:4]+'-01-01'
            annuals=[v for (m,p),v in selected.items() if m==metric and p<before and v['period_basis']=='annual']
            annual_prev=max(annuals,key=lambda v:v['period'],default=None)
            if not prev or not annual_prev or prev['period_basis'] != 'ytd' or annual_prev['period_basis'] != 'annual':
                continue
            if any(any(v[k] != value[k] for k in ('vendor', 'scope', 'unit', 'attribution','currency')) for v in (prev, annual_prev)):
                continue
            if value.get('period_start') and (not prev.get('period_start') or not annual_prev.get('period_start')
                or abs((date.fromisoformat(annual_prev['period'])-date.fromisoformat(before)).days)>8
                or abs((date.fromisoformat(value['period'])-date.fromisoformat(value['period_start'])).days-
                    (date.fromisoformat(prev['period'])-date.fromisoformat(prev['period_start'])).days)>14):continue
            ttm[metric] = value | dict(value=value['value']+annual_prev['value']-prev['value'],
                fact_ids=value['fact_ids']+annual_prev['fact_ids']+prev['fact_ids'], formula='YTD+previous_annual-previous_YTD')
        elif value['period_basis'] in ('quarter','half_year'):
            count=4 if value['period_basis']=='quarter' else 2
            rows=sorted([v for m,v in segments if m==metric and v['period']<=value['period'] and
                v['period_basis']==value['period_basis'] and v.get('period_start')],key=lambda v:v['period'])[-count:]
            if len(rows)!=count or any(any(r[k]!=value[k] for k in ('vendor','scope','unit','attribution','currency')) for r in rows):continue
            if not all(date.fromisoformat(b['period_start'])==date.fromisoformat(a['period'])+timedelta(days=1) for a,b in zip(rows,rows[1:])):continue
            span=(date.fromisoformat(rows[-1]['period'])-date.fromisoformat(rows[0]['period_start'])).days+1
            if not 330<=span<=400:continue
            ttm[metric]=value|dict(value=sum(r['value'] for r in rows),fact_ids=[i for r in rows for i in r['fact_ids']],
                formula='sum_contiguous_'+str(count)+'_'+value['period_basis'],period_start=rows[0]['period_start'])
    return ttm
