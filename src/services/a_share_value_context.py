"""Descriptive normalization and own valuation history, never a price forecast."""
from datetime import date
from math import isfinite
from statistics import mean


def normalized_history(annual, current_revenue):
    output = {}
    for metric in ('operating_profit', 'net_profit', 'operating_cashflow'):
        rows = []
        for year in annual:
            rev, amount = year['metrics'].get('revenue'), year['metrics'].get(metric)
            if (not rev or not amount or rev['value'] <= 0 or rev['unit'] != 'CNY' or amount['unit'] != 'CNY'
                or any(rev.get(k) != amount.get(k) for k in ('vendor','scope'))):
                continue
            rows.append(dict(period=year['period'], margin=amount['value']/rev['value'],
                fact_ids=rev['fact_ids']+amount['fact_ids']))
        consecutive = bool(rows) and [int(r['period'][:4]) for r in rows] == list(range(int(rows[0]['period'][:4]),int(rows[-1]['period'][:4])+1))
        average = mean(r['margin'] for r in rows) if rows else None
        output[metric] = dict(years=len(rows), periods=[r['period'] for r in rows], rows=rows, mean_margin=average,
            scaled_amount=average*current_revenue if average is not None and current_revenue is not None else None,
            consecutive=consecutive, coverage_sufficient=len(rows)>=5 and consecutive,
            formula='mean(annual amount/revenue) × current TTM revenue',
            limitation='按营收规模调整的历史均值；不是EBIT或可持续自由现金流。完整周期、并购/产能/主营结构变化须另行核实')
    return output


def cycle_review_status(snapshot, assumptions):
    if snapshot.get('economic_model', {}).get('model') != 'cyclical':
        return dict(ready=True, reasons=[])
    review = assumptions.get('cycle_review', {})
    annual = snapshot.get('financial_view', {}).get('annual', [])
    valid = {r['period'] for r in annual if 'revenue' in r['metrics'] and any(k in r['metrics'] for k in ('operating_profit','net_profit'))}
    periods = review.get('periods', [])
    years = sorted(int(p[:4]) for p in periods if isinstance(p,str) and p in valid)
    ids = {f['fact_id'] for f in snapshot.get('facts', [])} | {e['id'] for e in snapshot.get('evidence', [])}
    reasons = []
    if len(years) < 5 or len(years) != len(set(years)) or years != list(range(min(years or [0]),max(years or [0])+1)):
        reasons.append('周期覆盖不足：需至少5个连续完整年度的同口径营收与盈利，不能以短均值代表完整周期')
    if (review.get('status') != 'reviewed' or review.get('method') not in ('revenue_scaled_margins','capacity_adjusted')
        or review.get('structural_change') not in ('none_identified','adjusted') or not review.get('rationale')
        or not review.get('sources') or not set(review['sources']) <= ids):
        reasons.append('周期正常化及并购、产能、主营结构变化尚未有来源复核；保持研究，暂停条件价')
    return dict(ready=not reasons, reasons=reasons)


def own_valuation_history(rows, cutoff, calendar):
    end=date.fromisoformat(cutoff[:10])
    try:
        start=end.replace(year=end.year-5).isoformat()
    except ValueError:
        start=end.replace(year=end.year-5,day=28).isoformat()
    days={d for d in calendar if start <= d <= end.isoformat()}
    by_day={}
    for row in rows:
        day=row.get('trade_date', '')
        if start <= day <= end.isoformat():
            # Conflicting duplicate observations are unusable, not last-write wins.
            if day in by_day and by_day[day] != row:
                by_day[day] = None
            elif day not in by_day:
                by_day[day] = row
    history=[by_day[d] for d in sorted(by_day) if by_day[d] is not None]
    latest=history[-1] if history else {}
    def finite(value):
        return not isinstance(value,bool) and isinstance(value,(int,float)) and isfinite(value)
    metrics={}
    for key in ('pe_ttm','pb'):
        values=[r[key] for r in history if finite(r.get(key)) and r[key] > 0]
        current=latest.get(key)
        usable=finite(current) and current>0
        metrics[key]=dict(current=current,observations=len(values),
            percentile=sum(v<=current for v in values)/len(values) if usable and values else None,
            reason='' if usable and values else '最新指标缺失或非正；不回退到历史正值')
    full_calendar=bool(days) and min(calendar)<=start and max(calendar)>=end.isoformat()
    return dict(requested_start=start,requested_end=end.isoformat(),actual_start=history[0]['trade_date'] if history else None,
        actual_end=history[-1]['trade_date'] if history else None,observations=len(history),expected_sessions=len(days) if full_calendar else None,
        coverage=len({r['trade_date'] for r in history}&days)/len(days) if full_calendar else None,metrics=metrics,
        limitation='最近5年供应商重建估值日，非当时可知历史财报；非正PE/PB另列缺失，不用于正倍数分位。交易日历不足5年时覆盖率未知')
