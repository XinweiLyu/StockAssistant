"""Comparable financial periods with explicit provenance and coverage."""
from collections import defaultdict
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
        if f['available_at'] > cutoff or f['period_end'] > cutoff[:10] or f['scope'] != 'consolidated' or not f['published_at']:
            excluded.append(dict(fact_id=f['fact_id'], reason='未在截止时可用或报表口径/公告时间未核实'))
            continue
        groups[(f['metric'], f['report_period'])].append(f)
    selected, conflicts = {}, []
    for key, values in groups.items():
        signatures = {(v['value'], v['unit'], v['period_basis'], v['scope'], v['attribution']) for v in values}
        if len(signatures) != 1 or any(v['conflicts'] for v in values):
            conflicts.append(dict(metric=key[0], period=key[1], fact_ids=[v['fact_id'] for v in values], reason='数值或期间/主体口径冲突'))
            continue
        v = values[0]
        selected[key] = dict(value=v['value'], unit=v['unit'], period=v['report_period'],
            period_basis=v['period_basis'], scope=v['scope'], attribution=v['attribution'],
            vendor=v['source'].split('/')[0], fact_ids=[f['fact_id'] for f in values], formula='reported',
            user_attested=any(f['vintage_quality'] == 'user_attested' for f in values))
    latest_period = max((k[1] for k in groups), default=None)
    latest = {metric: v for (metric, period), v in selected.items() if period == latest_period}
    years = sorted({period for _, period in selected if period.endswith('12-31')})[-10:]
    annual = [dict(period=period, metrics={metric: v for (metric, p), v in selected.items()
                if p == period and v['period_basis'] in ('annual', 'instant')}) for period in years]
    ttm = {}
    for metric, value in latest.items():
        if value['period_basis'] == 'annual':
            ttm[metric] = value
        elif value['period_basis'] == 'ytd':
            year = int(value['period'][:4])-1
            prev = selected.get((metric, str(year)+value['period'][4:]))
            annual_prev = selected.get((metric, f'{year}-12-31'))
            if not prev or not annual_prev or prev['period_basis'] != 'ytd' or annual_prev['period_basis'] != 'annual':
                continue
            if any(any(v[k] != value[k] for k in ('vendor', 'scope', 'unit', 'attribution')) for v in (prev, annual_prev)):
                continue
            ttm[metric] = value | dict(value=value['value']+annual_prev['value']-prev['value'],
                fact_ids=value['fact_ids']+annual_prev['fact_ids']+prev['fact_ids'], formula='YTD+previous_annual-previous_YTD')
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
    return dict(latest_period=latest_period, latest=latest, annual=annual, ttm=ttm, normalization=normalization,
        current_capital=dict(value=current['value'], period=current['period_end'], available_at=current['available_at'],
            fact_ids=[current['fact_id']], unit='shares') if current else None,
        conflicts=conflicts, excluded=excluded, quality=dict(risks=risks, cash_profit_ratio=None,
            cash_profit_reason='合并CFO与归母利润主体不同，不标为严格现金转化率',
            years=len(annual), vintage='当前修订数据；不可作为历史当时已知财报'))
