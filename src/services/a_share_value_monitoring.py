"""Frozen forward research and ongoing review. Never submits trading actions."""
from operator import lt,le,gt,ge
from math import isfinite
from src.services.a_share_value_economics import build_economic_analysis,amounts
from src.services.a_share_value_holding import add_months

OPERATORS={'lt':lt,'lte':le,'gt':gt,'gte':ge}


def _actual(snapshot,metric,period):
    view=snapshot.get('financial_view',{});current=view.get('latest_period')
    if current==period:ttm=view.get('ttm',{});latest=view.get('latest',{})
    else:
        periods={r['period']:r['metrics'] for r in view.get('periods',view.get('annual',[]))}
        latest=periods.get(period,{});ttm={};year=int(period[:4])-1
        for key,f in latest.items():
            if f.get('period_basis')=='annual':ttm[key]=f
            elif f.get('period_basis')=='ytd':
                prior=periods.get(str(year)+period[4:],{}).get(key);annual=periods.get(f'{year}-12-31',{}).get(key)
                if prior and annual and prior.get('period_basis')=='ytd' and annual.get('period_basis')=='annual' and all(all(v.get(k)==f.get(k) for k in ('unit','scope','vendor','attribution')) for v in (prior,annual)):
                    ttm[key]=f|dict(value=f['value']+annual['value']-prior['value'],fact_ids=f['fact_ids']+annual['fact_ids']+prior['fact_ids'],formula='YTD+previous_annual-previous_YTD')
    if metric in ('revenue','net_profit','operating_cashflow','capex'):
        f=ttm.get(metric,{})
        basis_ok=(f.get('period_basis')=='annual' if period.endswith('12-31') else
            f.get('period_basis')=='ytd' and f.get('formula')=='YTD+previous_annual-previous_YTD')
        if not basis_ok or not amounts(ttm,[metric],period):return None,None,[]
        return f.get('value'),f.get('unit'),f.get('fact_ids',[])
    e=build_economic_analysis(view|dict(latest_period=period,latest=latest,ttm=ttm),snapshot.get('economic_model',{}).get('model','unresolved'))
    f=e['metrics'].get(metric,{})
    return f.get('value'),f.get('unit'),f.get('fact_ids',[])


def build_monitoring(snapshot,assumptions,report,portfolio=None,history=None,as_of=None):
    s=snapshot;a=assumptions or {};r=report or {};history=history or [];today=(as_of or s['cutoff'])[:10]
    latest=s.get('financial_view',{}).get('latest_period');rules=[];forward=[];signals=[]
    for rule in a.get('monitor_rules',[]) if a.get('code')==s.get('code') else []:
        p=rule.get('target_period') or latest
        row=dict(rule,state='insufficient',actual=None,review_due=bool(rule.get('review_on') and rule['review_on']<=today),reason='指标口径或资料不足')
        if p and (not latest or p>latest):row.update(state='pending',reason='目标财务期间尚未可用')
        elif p:
            value,unit,ids=_actual(s,rule['metric'],p)
            if isinstance(value,(int,float)) and isfinite(value) and unit==rule.get('unit') and ids and rule.get('operator') in OPERATORS:
                triggered=OPERATORS[rule['operator']](value,rule['threshold'])
                row.update(state='breached' if triggered else 'observed',actual=value,actual_period=p,actual_sources=ids,
                    reason='触及研究复核条件，需检查反证；不是自动卖出指令' if triggered else '本次未触及该条件，不代表整体假说已证实')
                if triggered:signals.append(dict(kind='thesis_review',message=rule.get('rationale') or '经营条件触发复核',rule_id=rule.get('id')))
        rules.append(row)
    seen=set()
    for record in sorted(history,key=lambda r:r.get('created_at','')):
        old=record.get('payload',{});frozen=record.get('snapshot') or {}
        if old.get('code')!=s.get('code') or frozen.get('code')!=s.get('code'):continue
        known={f['fact_id'] for f in frozen.get('facts',[])}|{e['id'] for e in frozen.get('evidence',[])}
        for obs in old.get('forecast_observations',[]):
            p=obs['period'];key=(obs['metric'],p,obs.get('basis','ttm'))
            if key in seen:continue
            # These comparisons are deliberately conservative. Post-period
            # edits cannot replace the first actual forward research record.
            if (record.get('created_at','')[:10]>=p or frozen.get('cutoff','')[:10]>=p
                or frozen.get('financial_view',{}).get('latest_period','')>=p):continue
            seen.add(key)
            row=dict(metric=obs['metric'],period=p,forecast=obs['value'],unit=obs['unit'],origin=obs.get('origin'),
                revision=old.get('revision'),recorded_at=record.get('created_at'),snapshot_id=old.get('snapshot_id'),
                state='insufficient',actual=None,error=None,reason='原始来源或实际值口径不足',vintage='当前修订实际值，非历史当时可知回测')
            if not obs.get('sources') or not set(obs['sources'])<=known:forward.append(row);continue
            if not latest or p>latest:row.update(state='pending',reason='尚未到期或实际财报尚未取得')
            else:
                value,unit,ids=_actual(s,obs['metric'],p)
                if isinstance(value,(int,float)) and isfinite(value) and unit==obs['unit'] and ids:
                    row.update(state='matured',actual=value,error=value-obs['value'],actual_sources=ids,
                        relative_error=(value-obs['value'])/abs(obs['value']) if obs['value'] else None,
                        reason='原始假设与当前修订实际值对照，不是历史预测收益回测')
            forward.append(row)
    portfolio=portfolio or {};context=dict(state='unavailable',reason='账户、报价或持仓资料尚不完整')
    nav=portfolio.get('nav')
    if portfolio.get('complete') and isinstance(nav,(int,float)) and nav>0:
        positions=portfolio.get('positions',[]);mine=[p for p in positions if p.get('code')==s.get('code')]
        weight=sum(p.get('market_value',0) for p in mine)/nav;limits=portfolio.get('risk',{})
        context=dict(state='available',stock_weight=weight,limits=limits)
        sectors={p.get('sector') for p in mine if p.get('sector')}
        sector_weight=sum(p.get('market_value',0) for p in positions if p.get('sector') in sectors)/nav
        total_weight=sum(p.get('market_value',0) for p in positions)/nav
        context.update(sector_weight=sector_weight,total_weight=total_weight)
        if any(isinstance(limits.get(k),(int,float)) and v>limits[k] for k,v in
            [('stock_cap',weight),('sector_cap',sector_weight),('total_cap',total_weight)]):
            signals.append(dict(kind='portfolio_review',message='账户集中度超过已配置约束，需独立复核组合风险'))
        q=s.get('binding',{}).get('quote',{})
        if q.get('valid') and any(isinstance(p.get('stop'),(int,float)) and q.get('price',float('inf'))<=p['stop'] for p in mine):
            signals.append(dict(kind='trading_context',message='价格触及交易止损参考，不自动判定长期假说失效；结合账户与经营反证复核'))
    if r.get('valuation_state')=='conditional' and not r.get('parameter_origin') and (r.get('comparison',{}).get('margin') or 0)<0:
        signals.append(dict(kind='valuation_review',message='价格高于所选保守估值，复核估值更新及机会成本，不自动发出卖出指令'))
    baseline=next((h.get('snapshot') or {} for h in history if h.get('payload',{}).get('snapshot_id')==a.get('snapshot_id')
        and h.get('payload',{}).get('revision')==a.get('revision')),s)
    next_review=add_months(baseline.get('cutoff',s['cutoff']),3)
    if next_review<=today:signals.append(dict(kind='scheduled_review',message='原研究已到季度复核节点；更新经营资料并复核假说，不因每天查看而顺延'))
    return dict(rules=rules,forward_checks=forward[:60],signals=signals,portfolio=context,next_review=next_review,
        theses=a.get('theses',[]),limitation='季度复核、假说失效、估值与机会成本及组合风险分别判断；未触发条件不等于无风险，不自动交易')
