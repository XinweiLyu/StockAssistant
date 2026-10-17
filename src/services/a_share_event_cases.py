"""Chronological event observations, not estimates of causal treatment effects."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from math import isfinite
import re
import numpy as np
from src.schemas.a_share_integrated import stamp

HORIZONS = (1, 5, 20, 60)


def effective_event_families(events):
    """Latest known family state supersedes earlier positive statements, even if withdrawn."""
    selected,seen=[],set()
    for index,event in enumerate(sorted(events,key=lambda e:e.get('published_at') or '',reverse=True)):
        key=(event.get('code'),event.get('family_id') or event.get('id') or str(index))
        if key not in seen:
            selected.append(event)
            seen.add(key)
    return selected


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def extract_event_facts(document, numeric_facts, completion=None):
    text = document.get('text') or ''
    result = dict(document, direction='unknown', intensity=None, intensity_unit=None,
                  evidence_quote=None, expectation_surprise=None,
                  extraction_status='insufficient', public_verified=bool(document.get('text_status') == 'ready'))
    if not text:
        return result
    if re.search(r'撤销|撤回|作废', document.get('title','')):
        return result | dict(extraction_status='withdrawn')
    # Keep an exact supporting span. A YoY change is not a consensus surprise.
    pattern = r'净利润[\s\S]{0,60}?(?:同比|比上年同期)(增长|增加|上升|下降|减少)[：:\s]*(-?\d+(?:\.\d+)?)\s*%\s*(?:(?:至|到|—|－|~|～|-)\s*(-?\d+(?:\.\d+)?)\s*%)?'
    match = re.search(pattern, text)
    if match:
        low = float(match[2])
        high = float(match[3]) if match[3] is not None else low
        amount = (low + high) / 200
        if match[1] in ('下降', '减少'):
            amount = -abs(amount)
        return result | dict(direction='positive' if amount > 0 else 'negative' if amount < 0 else 'neutral',
                             intensity=amount, intensity_unit='profit_yoy_ratio', evidence_quote=match[0],
                             extraction_status='quoted_numeric', mixed_events=bool(document.get('mixed_events')))
    if completion is not None:
        candidate = completion(document, numeric_facts)
        quote = candidate.get('evidence_quote') if isinstance(candidate, dict) else None
        # AI can point to a span; the same deterministic numeric verifier must accept it.
        if isinstance(quote, str) and quote and quote in text:
            checked = extract_event_facts(dict(document, text=quote), numeric_facts)
            if checked['intensity'] is not None:
                return result | {k: checked[k] for k in ('direction', 'intensity', 'intensity_unit', 'evidence_quote', 'extraction_status')}
    return result


def event_context(event, histories, calendar, cutoff, elapsed_sessions=0):
    if isinstance(elapsed_sessions,bool) or not isinstance(elapsed_sessions,int) or not 0 <= elapsed_sessions <= 20:
        raise ValueError('事件已过去的交易日须为0至20')
    calendar = sorted(set(d for d in calendar if d <= str(cutoff)[:10]))
    published = stamp(event.get('published_at'))
    output = dict(event, outcomes={}, pre5=None, pre20=None, market_state='unknown')
    if not published or published > stamp(cutoff):
        return output
    day = published[:10]
    after_close = datetime.fromisoformat(published).hour >= 15
    before = [d for d in calendar if d <= day] if after_close else [d for d in calendar if d < day]
    if not before:
        return output
    anchor = calendar.index(before[-1])
    maps = {k: {r['date']: r for r in v if r['date'] <= str(cutoff)[:10]} for k, v in histories.items()}

    def close(kind, index):
        if index < 0 or index >= len(calendar):
            return None
        row = maps.get(kind, {}).get(calendar[index], {})
        price = row.get('adjusted_close')
        return price if finite(price) and price > 0 else None

    original_anchor = anchor
    original_price, previous = close('stock',anchor), close('stock',anchor-20)
    output['event_pre20'] = original_price/previous-1 if original_price and previous else None
    anchor += elapsed_sessions
    output['elapsed_sessions'] = elapsed_sessions
    output['event_anchor_date'] = calendar[original_anchor]
    base = close('stock', anchor)
    if base is None:
        return output
    for h in (5, 20):
        previous = close('stock', anchor - h)
        span = calendar[max(0, anchor-h):anchor+1]
        if previous and all(close('stock', calendar.index(d)) for d in span):
            output[f'pre{h}'] = base / previous - 1
    benchmark = [close('benchmark', i) for i in range(max(0, anchor-59), anchor+1)]
    if len(benchmark) == 60 and all(benchmark):
        average = float(np.mean(benchmark))
        output['market_state'] = 'up' if benchmark[-1] > average*1.005 else 'down' if benchmark[-1] < average*.995 else 'range'
    for h in HORIZONS:
        end = anchor + h
        if end >= len(calendar) or not all(close('stock', i) for i in range(anchor, end+1)):
            continue
        stock_return = close('stock', end) / base - 1
        row = dict(start_date=calendar[anchor+1], end_date=calendar[end], anchor_date=calendar[anchor],
                   stock_return=stock_return, execution_status='unverified')
        for kind in ('benchmark', 'industry'):
            first, last = close(kind, anchor), close(kind, end)
            result = last/first-1 if first and last and all(close(kind, i) for i in range(anchor, end+1)) else None
            key = 'market' if kind == 'benchmark' else kind
            row[key + '_return'] = result
            row[key + '_excess'] = stock_return-result if result is not None else None
        window = [maps['stock'][calendar[i]] for i in range(anchor+1, end+1)]
        scaled = [(b, b['adjusted_close']/b['close']) for b in window if finite(b.get('close')) and b['close'] > 0]
        row['adverse'] = min((b['low']*scale/base-1 for b, scale in scaled), default=None)
        row['favorable'] = max((b['high']*scale/base-1 for b, scale in scaled), default=None)
        first = window[0]
        open_price = first.get('open')
        row['post_open_return'] = close('stock', end)/(open_price*first['adjusted_close']/first['close'])-1 if finite(open_price) and open_price > 0 else None
        output['outcomes'][str(h)] = row
    return output


def _bin(value, population):
    population = [v for v in population if finite(v)]
    if not finite(value) or not population:
        return None
    lower, upper = np.quantile(population, [.25, .75])
    if abs(upper-lower) < 1e-10:
        return -1 if value < lower-1e-10 else 1 if value > upper+1e-10 else 0
    return -1 if value < lower else 1 if value > upper else 0


def match_event_cases(target, cases, cutoff, horizons=HORIZONS):
    cutoff_stamp = stamp(cutoff)
    cutoff_day = cutoff_stamp[:10]
    excluded, families, eligible, references = Counter(), set(), [], []
    required = ('market_state', 'pre20', 'intensity', 'industry_id')
    missing = [k for k in required if target.get(k) in (None, '', 'unknown')]
    optional_missing = [k for k in ('valuation_percentile',) if not finite(target.get(k))]
    for case in sorted(cases, key=lambda e: e.get('published_at') or '', reverse=True):
        reason = None
        when = stamp(case.get('published_at'))
        family = (case.get('code'), case.get('family_id') or case.get('id'))
        duplicate = family in families
        if when and when <= cutoff_stamp and case.get('public_verified'):
            families.add(family)
        if case.get('id') == target.get('id'):
            reason = 'self'
        elif not when or when > cutoff_stamp:
            reason = 'future'
        elif not case.get('public_verified'):
            reason = 'unverified_publication'
        elif case.get('kind') != target.get('kind'):
            reason = 'event_kind'
        elif case.get('direction') != target.get('direction') or case.get('direction') == 'unknown':
            reason = 'direction'
        elif case.get('industry_quality') not in ('historical', 'archived'):
            reason = 'unverified_industry'
        elif case.get('industry_id') != target.get('industry_id'):
            reason = 'industry'
        if not reason and duplicate:
            reason = 'duplicate_family'
        if reason:
            excluded[reason] += 1
            continue
        eligible.append(case)
    population = {k: [e.get(k) for e in eligible] for k in ('pre20', 'intensity', 'valuation_percentile')}
    matched = []
    for case in eligible:
        mismatch = []
        if case.get('market_state') != target.get('market_state'):
            mismatch.append('market_state')
        for k in ('pre20', 'intensity'):
            a, b = _bin(target.get(k), population[k]), _bin(case.get(k), population[k])
            if a is None or b is None or a != b:
                mismatch.append(k)
        if finite(target.get('valuation_percentile')) and finite(case.get('valuation_percentile')):
            if _bin(target[k := 'valuation_percentile'], population[k]) != _bin(case[k], population[k]):
                mismatch.append(k)
        if mismatch:
            references.append(case | dict(mismatch=mismatch))
        else:
            matched.append(case)
    groups = {}
    for h in horizons:
        rows, windows = [], {}
        for case in matched:
            outcome = case.get('outcomes', {}).get(str(h))
            if not outcome or outcome.get('end_date', '9999') > cutoff_day or not finite(outcome.get('stock_return')) or outcome['stock_return'] <= -1:
                continue
            start, end = outcome.get('start_date'), outcome.get('end_date')
            if not start or not end or end < start:
                continue
            prior = windows.setdefault(case['code'], [])
            if any(start <= b and end >= a for a, b in prior):
                continue
            prior.append((start, end))
            rows.append(dict(case_id=case['id'], code=case['code'], **outcome))
        returns = [r['stock_return'] for r in rows]
        quantiles = [float(v) for v in np.quantile(returns, [.1, .5, .9])] if returns else [None]*3
        median = lambda key: float(np.median([r[key] for r in rows if finite(r.get(key))])) if any(finite(r.get(key)) for r in rows) else None
        companies = len({r['code'] for r in rows})
        groups[str(h)] = dict(horizon_sessions=h, sample_size=len(rows), companies=companies,
            numerical_eligible=not missing and len(rows) >= 10 and companies >= 5,
            low_return=quantiles[0], median_return=quantiles[1], high_return=quantiles[2],
            median_market_excess=median('market_excess'), median_industry_excess=median('industry_excess'),
            median_adverse=median('adverse'), positive_share=sum(v > 0 for v in returns)/len(returns) if returns else None,
            observations=rows, reason='需至少10个非重叠事件及5家公司；分布不是未来概率',
            concentration_warning=len({r['start_date'][:4] for r in rows}) < 2 if rows else False)
    return dict(horizons=groups, cases=matched[:100], reference_cases=references[:100], excluded=dict(excluded),
                missing_dimensions=missing, optional_missing=optional_missing,
                matching=dict(method='hierarchical-v1', bins={k:[float(v) for v in np.quantile([v for v in vs if finite(v)], [.25,.75])] if any(finite(v) for v in vs) else [] for k,vs in population.items()}),
                limitations=['事件表现为条件相关性，不证明因果；未知历史行业不能用今日分类替代',
                             '多事件和同时期市场冲击可能混杂；未验证可执行组合收益'])


def case_price_references(matches, reference_price):
    if not finite(reference_price) or reference_price <= 0:
        return []
    return [dict(id='C'+str(h), horizon_sessions=int(h), low=reference_price*(1+row['low_return']),
                 median=reference_price*(1+row['median_return']), high=reference_price*(1+row['high_return']),
                 sample_size=row['sample_size'], kind='historical_distribution', calibrated=False)
            for h,row in matches.get('horizons', {}).items() if row.get('numerical_eligible')]
