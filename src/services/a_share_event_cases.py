"""Chronological event observations, not estimates of causal treatment effects."""
from __future__ import annotations

from collections import Counter
from math import isfinite
import re
import numpy as np
from src.schemas.a_share_integrated import stamp, digest, earnings_stage
from src.services.a_share_event_lifecycle import event_anchor_index
from src.services.a_share_outlook import benchmark_state

HORIZONS = (1, 5, 20, 60, 120, 250)


def effective_event_families(events):
    """Latest known family state supersedes earlier positive statements, even if withdrawn."""
    selected,seen=[],set()
    def order(event):
        return (event.get('published_at') or '', bool(re.search(r'更正|修订|修正',event.get('title',''))),
                bool(event.get('text_status')=='ready' and event.get('text')))
    for index,event in enumerate(sorted(events,key=order,reverse=True)):
        if event.get('kind')=='earnings' and event.get('report_period'):
            subtype={1:'guidance',2:'flash',3:'report'}.get(earnings_stage(event.get('title','')))
            event=event | dict(family_id=digest([event.get('code'),'earnings',event['report_period'],subtype]) if subtype else event.get('id'))
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
    # Background earnings in a contract or penalty do not quantify that event.
    # Mixed documents require a metric/period-aware extractor before publication.
    if document.get('kind') != 'earnings' or document.get('mixed_events'):
        return result
    if re.search(r'(?:更正|修订|修正|调整)[前后]|原预计|原披露|原公告|此前(?:预计|披露)', text):
        return result
    # Keep an exact supporting span. A YoY change is not a consensus surprise.
    # Accept an explicit subject/comparison phrase; arbitrary intervening prose
    # can switch to a different metric even within the same sentence.
    pattern = r'净利润[：:\s]*(?:(?:预计|预期|将)[：:\s]*)?(?:同比|比上年同期)(增长|增加|上升|下降|减少)[：:\s]*(-?\d+(?:\.\d+)?)\s*%\s*(?:(?:至|到|—|－|~|～|-)\s*(-?\d+(?:\.\d+)?)\s*%)?'
    matches = list(re.finditer(pattern, text))
    # Multiple metrics or periods cannot be resolved by choosing the first span.
    if len(matches) != 1:
        return result
    match = matches[0]
    prefix = re.split(r'[。；;!?！？]', text[:match.start()])[-1][-160:]
    subject = re.split(r'[，,]', prefix)[-1]
    deducted = r'(?:扣非|扣除非经常性损益(?:后)?(?:的)?)'
    parent = r'(?:归母|归属于上市公司股东的?)'
    join = r'\s*(?:与|及|和|、|/)\s*'
    if re.search(parent+join+deducted+'|'+deducted+join+parent, subject):
        return result
    unit = 'deducted_profit_yoy_ratio' if re.search(deducted, subject) else 'profit_yoy_ratio'
    quote = text[match.start()-len(subject):match.end()] if unit=='deducted_profit_yoy_ratio' else match[0]
    if re.search(r'上年|去年|上一(?:年|报告期)|此前|原预计|原披露|原公告', prefix):
        return result
    period = str(document.get('report_period') or '')
    title_years = re.findall(r'(20\d{2})年', document.get('title', ''))
    year = period[:4] if re.fullmatch(r'20\d{2}-\d{2}-\d{2}', period) else title_years[0] if len(set(title_years)) == 1 else None
    explicit_years = re.findall(r'(20\d{2})年', prefix)
    if explicit_years and (not year or any(y != year for y in explicit_years)):
        return result
    # Only recognize a few explicit reporting periods; otherwise retain the gap.
    periods = [(r'(?:第一|一)季度', '03-31'),
               (r'半年度|中期|上半年|1\s*[-至—]\s*6\s*月', '06-30'),
               (r'前三季度|(?:第三|三)季度|1\s*[-至—]\s*9\s*月', '09-30'),
               (r'全年|(?<!半)年度|1\s*[-至—]\s*12\s*月', '12-31')]
    explicit_periods = {end for expression, end in periods if re.search(expression, prefix)}
    if explicit_periods and (len(explicit_periods) != 1 or period[5:] not in explicit_periods):
        return result
    if explicit_years and not explicit_periods and period[5:] != '12-31':
        return result
    low = float(match[2])
    high = float(match[3]) if match[3] is not None else low
    amount = (low + high) / 200
    if match[1] in ('下降', '减少'):
        amount = -abs(amount)
    # The optional completion argument remains API-compatible, but a clipped quote
    # cannot override the full document's ambiguity or current-period checks.
    return result | dict(direction='positive' if amount > 0 else 'negative' if amount < 0 else 'neutral',
                         intensity=amount, intensity_unit=unit, evidence_quote=quote,
                         extraction_status='quoted_numeric', mixed_events=False)


def event_context(event, histories, calendar, cutoff, elapsed_sessions=0):
    if isinstance(elapsed_sessions,bool) or not isinstance(elapsed_sessions,int) or not 0 <= elapsed_sessions <= 1250:
        raise ValueError('事件阶段须为0至1250个已完成交易日')
    calendar = sorted(set(d for d in calendar if d <= str(cutoff)[:10]))
    published = stamp(event.get('published_at'))
    output = dict(event, outcomes={}, pre5=None, pre20=None, market_state='unknown')
    if not published or published > stamp(cutoff):
        return output
    anchor = event_anchor_index(published, calendar)
    if anchor is None:
        return output
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
    output['stage_anchor_date'] = calendar[anchor]
    output['realized_since_event'] = base/original_price-1 if original_price else None
    for h in (5, 20):
        previous = close('stock', anchor - h)
        span = calendar[max(0, anchor-h):anchor+1]
        if previous and all(close('stock', calendar.index(d)) for d in span):
            output[f'pre{h}'] = base / previous - 1
    benchmark = [close('benchmark', i) for i in range(max(0, anchor-64), anchor+1)]
    output['market_state'] = benchmark_state(benchmark)
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
    if not target.get('id'):
        message = '没有已核对原文并可量化的跟踪事件，尚未启动历史可比匹配；不代表历史事件不存在'
        return dict(status='no_target', message=message, horizons={str(h):dict(horizon_sessions=h,
            sample_size=0, companies=0, numerical_eligible=False, reason=message) for h in horizons},
            cases=[], reference_cases=[], excluded={}, missing_dimensions=[], optional_missing=[], limitations=[])
    required = ('market_state', 'pre20', 'intensity', 'industry_id')
    target_stage = earnings_stage(target.get('title', '')) if target.get('kind') == 'earnings' else 0
    missing = [k for k in required if target.get(k) in (None, '', 'unknown')]
    optional_missing = [k for k in ('valuation_percentile',) if not finite(target.get(k))]
    for case in sorted(cases, key=lambda e: e.get('published_at') or '', reverse=True):
        reason = None
        when = stamp(case.get('published_at'))
        family = (case.get('code'), case.get('family_id') or case.get('id'))
        duplicate = family in families
        if when and when <= cutoff_stamp and case.get('public_verified'):
            families.add(family)
        if case.get('id') == target.get('id') or (target.get('family_id') and family == (target.get('code'), target['family_id'])):
            reason = 'self'
        elif not when or when > cutoff_stamp:
            reason = 'future'
        elif not case.get('public_verified'):
            reason = 'unverified_publication'
        elif case.get('kind') != target.get('kind'):
            reason = 'event_kind'
        elif target_stage and earnings_stage(case.get('title', '')) != target_stage:
            reason = 'earnings_stage'
        elif case.get('stage_state') == 'superseded':
            reason = 'superseded_at_stage'
        elif case.get('intensity_unit') != target.get('intensity_unit'):
            reason = 'intensity_unit'
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
    optional_state = tuple(k for k in ('event_pre20', 'realized_since_event') if finite(target.get(k)))
    population = {k: [e.get(k) for e in eligible] for k in ('pre20', 'intensity', 'valuation_percentile')+optional_state}
    matched = []
    for case in eligible:
        mismatch = []
        if case.get('market_state') != target.get('market_state'):
            mismatch.append('market_state')
        for k in ('pre20', 'intensity')+optional_state:
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
    return dict(status='matched', horizons=groups, cases=matched[:100], reference_cases=references[:100], excluded=dict(excluded),
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
