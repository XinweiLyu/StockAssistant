"""Score immutable issued scenarios only after outcomes actually mature."""
from statistics import mean
from datetime import datetime
from src.schemas.a_share_integrated import stamp
from src.services.a_share_market_service import price_family
from src.services.a_share_event_cases import finite


def _observations(records, bars, calendar, cutoff, source):
    cutoff_stamp=stamp(cutoff)
    days=sorted(set(calendar))
    lookup={r['date']:r for r in bars if r['date']<=cutoff_stamp[:10]}
    observations={str(h):[] for h in (5,20,60)}
    seen=set()
    snapshots=[r.get('payload',r) for r in records]
    for saved in sorted(snapshots,key=lambda r:r.get('generated_at') or ''):
        try:
            issued=stamp(saved.get('generated_at'))
            anchor=saved['anchor_date']
            binding=saved['history_binding']
            if not issued or issued>cutoff_stamp or not source or price_family(binding.get('source'))!=price_family(source) or anchor not in days:
                continue
            first=lookup.get(anchor)
            reference=saved['reference_price']
            if not first or not finite(reference) or reference<=0 or not finite(first.get('close')) or abs(first['close']-reference)>max(1,reference)*1e-8:
                continue
            index=days.index(anchor)
            issue_day=issued[:10]
            hour=datetime.fromisoformat(issued).hour
            next_session=days[index+1] if index+1<len(days) else None
            if issue_day<anchor or (issue_day==anchor and hour<15) or not next_session:
                continue
            if issue_day>next_session or (issue_day==next_session and hour>=15):
                continue
            path_known_forward=issue_day==anchor or issue_day<next_session
            for h in (5,20,60):
                identity=(saved.get('code'),anchor,h)
                if identity in seen or index+h>=len(days):
                    continue
                target=days[index+h]
                if target>cutoff_stamp[:10] or target<=issued[:10]:
                    continue
                span=days[index:index+h+1]
                if any(d not in lookup or not finite(lookup[d].get('close')) or lookup[d]['close']<=0 for d in span):
                    continue
                group=[f for f in saved.get('forecasts',[]) if f.get('horizon_sessions')==h
                       and all(finite(f.get(k)) and f[k]>0 for k in ('low','high')) and f['low']<=f['high']]
                base=next((f for f in group if f.get('scenario')=='base'),None)
                if not base:
                    continue
                price=lookup[target]['close']
                center=(base['low']+base['high'])/2
                low=min(f['low'] for f in group)
                high=max(f['high'] for f in group)
                original=next((r for r in saved.get('numeric_references',[]) if r.get('id')=='B'+str(h)),None)
                original_median=original.get('median') if original else None
                window=[lookup[d] for d in span[1:]]
                adverse=min((b['low']/reference-1 for b in window if finite(b.get('low')) and b['low']>0),default=None) if path_known_forward else None
                observations[str(h)].append(dict(code=saved.get('code'),anchor=anchor,target=target,
                    actual=price,reference=reference,error=abs(price-center),
                    direction_correct=(center>reference)==(price>reference) if center!=reference and price!=reference else center==price,
                    covered=low<=price<=high,adverse=adverse,
                    original_error=abs(price-original_median) if finite(original_median) else None,
                    unchanged_error=abs(price-reference)))
                seen.add(identity)
        except (KeyError,TypeError,ValueError):
            # Malformed archived records are not reconstructed as successful forecasts.
            continue
    return observations


def evaluate_integrated_snapshots(records,bars,calendar,cutoff,source=None):
    observations=_observations(records,bars,calendar,cutoff,source)
    horizons={}
    for h,rows in observations.items():
        independent=[]
        for row in rows:
            if not any(p['code']==row['code'] and row['anchor']<=p['target'] and row['target']>=p['anchor'] for p in independent):
                independent.append(row)
        horizons[h]=dict(matured=len(rows),non_overlapping_samples=len(independent),
            mean_absolute_error=mean(r['error'] for r in rows) if rows else None,
            direction_accuracy=mean(r['direction_correct'] for r in rows) if rows else None,
            observed_scenario_coverage=mean(r['covered'] for r in rows) if rows else None,
            mean_adverse=mean(r['adverse'] for r in rows if r['adverse'] is not None) if any(r['adverse'] is not None for r in rows) else None,
            status='measured' if rows else 'insufficient')
    return dict(status='measured' if any(r['matured'] for r in horizons.values()) else 'insufficient',
        horizons=horizons,snapshots=len(records),portfolio_return=None,costs_verified=False,
        limitations=['仅评价实际生成且结果已成熟的预测；事后重建不计入前瞻表现',
                     '仅接受锚点收盘后至下一交易日收盘前的发行；盘中发行无法验证当日低点发生时刻，不统计路径不利变动',
                     '同期限样本可能重叠，独立窗口数量另列；情景覆盖不是置信度或盈利率',
                     '未完成综合策略可成交与成本回测，不显示组合收益'])


def compare_forecast_snapshots(records,bars,calendar,cutoff,source=None):
    observations=_observations(records,bars,calendar,cutoff,source)
    horizons={}
    for h,all_rows in observations.items():
        rows=[r for r in all_rows if r['original_error'] is not None]
        horizons[h]=dict(samples=len(rows),unchanged_price_mae=mean(r['unchanged_error'] for r in rows) if rows else None,
            price_model_mae=mean(r['original_error'] for r in rows) if rows else None,
            integrated_mae=mean(r['error'] for r in rows) if rows else None)
    unavailable=dict(status='unavailable',reason='没有实际生成的该变体实验快照，未补造消融结果')
    return dict(horizons=horizons,financial_only=unavailable,events_only=unavailable,
                method='paired issued stock/anchor/horizon/source observations')
