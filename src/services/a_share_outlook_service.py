"""Cached local price outlooks, distinct from LLM scenarios and executable plans."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from math import isfinite
from statistics import mean
from zoneinfo import ZoneInfo

from src.services.a_share_market_service import price_family

TZ = ZoneInfo('Asia/Shanghai')


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode()).hexdigest()


def merged_bars(raw, adjusted):
    mapping = {b['date']: b['close'] for b in (adjusted or {}).get('items', [])}
    return [dict(b, adjusted_close=mapping.get(b['date'])) for b in (raw or {}).get('items', [])]


def archive_metrics(records, bars, calendar, now, source, as_of=None):
    """Score issued 20-session endpoint intervals; never a portfolio backtest."""
    lookup = {b['date']: b for b in bars}
    anchors = {r['payload']['as_of'] for r in records if r['payload'].get('as_of')}
    local_now = now.astimezone(TZ)
    bound = local_now.date() if (local_now.hour, local_now.minute) >= (18, 40) else local_now.date() - timedelta(days=1)
    cutoff = as_of or bound.isoformat()
    counted = set()
    observed, errors = [], []
    # Oldest *eligible20-day* issuance wins. An earlier5-day-only warmup
    # cannot prevent a later same-anchor20-day forecast from maturing.
    for record in reversed(records):
        saved = record['payload']
        issued = timestamp(saved.get('generated_at'))
        if not issued or issued > now or price_family(saved.get('source')) != price_family(source):
            continue
        anchor = saved.get('as_of')
        if anchor in counted or anchor not in calendar:
            continue
        after = [d for d in calendar if d > anchor]
        if len(after) < 20:
            continue
        target = after[19]
        if target > cutoff or target <= issued.astimezone(TZ).date().isoformat():
            continue
        row = lookup.get(target)
        forecast = next((f for f in saved.get('forecasts', []) if f['horizon_sessions'] == 20), None)
        if not row or not forecast or not isfinite(row['close']) or row['close'] <= 0:
            continue
        counted.add(anchor)
        observed.append(forecast['low'] <= row['close'] <= forecast['high'])
        errors.append(abs(row['close'] - forecast['median']))
    return dict(snapshots=len(anchors), matured=len(observed),
                coverage=mean(observed) if observed else None,
                mean_absolute_error=mean(errors) if errors else None)


class OutlookService:
    def __init__(self, assistant):
        self.assistant = assistant

    def _events(self, code, now):
        svc = self.assistant
        records = svc.repo.records(svc.settings.mode, 'event', limit=5000)
        event_keys = {r['id']: r['key'] for r in records}
        verified = {}
        for record in svc.repo.records(svc.settings.mode, 'verification', limit=5000):
            value = record['payload']
            when = timestamp(value.get('verified_at'))
            if when is not None and when <= now:
                verified.setdefault(event_keys.get(value.get('event_id'), str(value.get('event_id'))), value)
        selected = []
        for record in records:
            value = record['payload']
            if value.get('code') not in (None, code) and value.get('related_code') != code:
                continue
            if value.get('code') is None and value.get('related_code') not in (None, code):
                continue
            first = timestamp(value.get('first_seen'))
            revised = timestamp(value.get('revised_at'))
            if (first and first > now) or (revised and revised > now):
                continue
            confirmation = verified.get(record['key'])
            selected.append(value | dict(id=str(record['id']), event_key=record['key'],
                                         verified=bool(confirmation), verification=confirmation))
        material = any(e.get('verification', {}).get('major_risk')
                       for e in selected if isinstance(e.get('verification'), dict)
                       and e['verification'].get('code') == code)
        return selected, material

    def _history(self, code, end, refresh):
        svc, market = self.assistant, self.assistant.market
        profile = svc.settings.mode
        cutoff = date.fromisoformat(end)
        try:
            start = cutoff.replace(year=cutoff.year - 5).isoformat()
        except ValueError:
            start = cutoff.replace(year=cutoff.year - 5, day=28).isoformat()
        raw = market.repo.get_history(profile, 'stock:' + code, 'raw', '1900-01-01', end)
        adjusted = market.repo.get_history(profile, 'stock:' + code, 'qfq', '1900-01-01', end)
        states = []
        if profile != 'demo':
            for basis, cached in [('raw', raw), ('qfq', adjusted)]:
                if refresh or not cached or cached['requested_start'] > start or cached['requested_end'] < end:
                    states.append(market.history(code, start, end, basis, refresh).state)
        benchmark = market.repo.get_history(profile, 'benchmark:000300', 'raw', '1900-01-01', end)
        if profile != 'demo' and (refresh or not benchmark or benchmark['requested_start'] > start or benchmark['requested_end'] < end):
            states.append(market.benchmark_history(start, end, refresh).state)
        groups = market.repo.associations(profile, [code]).get(code, [])
        industries = [g for g in groups if g['kind'] == 'industry'
                      and g['classification'] == 'eastmoney-industry']
        sector = None
        # Ambiguous classifications do not become an invented industry benchmark.
        if len(industries) == 1:
            sector = market.repo.get_history(profile, industries[0]['sector_id'], 'raw', '1900-01-01', end)
            if profile != 'demo' and (refresh or not sector or sector['requested_start'] > start or sector['requested_end'] < end):
                states.append(market.sector_history(industries[0]['sector_id'], start, end, refresh).state)
        return raw, adjusted, benchmark, sector, states

    def get(self, code, min_reward_risk=2.0, refresh=False):
        from src.services.a_share_outlook import VERSION, build_outlook, event_observations
        if isinstance(min_reward_risk, bool) or not isfinite(min_reward_risk) or not 1 <= min_reward_risk <= 5:
            raise ValueError('最低潜在收益/风险必须在1–5之间')
        svc, market = self.assistant, self.assistant.market
        profile = svc.settings.mode
        stock = market.stock(code)
        end, now = market.completed_day(), market.clock()
        raw, adjusted, benchmark, sector, states = self._history(code, end, refresh)
        same_source = bool(raw and adjusted and price_family(raw['source']) == price_family(adjusted['source']))
        repairing = False
        if raw and adjusted and not same_source and profile != 'demo':
            repairing = market.repair_pair(profile, code, end, priority=5)
        valid_end = bool(same_source and raw['items'] and adjusted['items']
                         and raw['items'][-1]['date'] == end and adjusted['items'][-1]['date'] == end)
        bars = merged_bars(raw, adjusted) if valid_end else []
        # Source-published benchmark/sector indices have no per-stock split factor.
        # Their index closes are the consistent return series, explicitly marked.
        bm = [dict(b, adjusted_close=b['close']) for b in (benchmark or {}).get('items', [])]
        industry = [dict(b, adjusted_close=b['close']) for b in (sector or {}).get('items', [])]
        calendar = market.calendar()
        selected_events, material_risk = self._events(code, now)
        data_hash = fingerprint([VERSION, code, end, bars, (raw or {}).get('source'),
                                 (adjusted or {}).get('adjustment_basis'), bm, industry,
                                 [d for d in calendar if d <= (date.fromisoformat(end) + timedelta(days=120)).isoformat()],
                                 min_reward_risk])
        journal_key = f'{profile}:{code}:{min_reward_risk:g}'
        saved = svc.repo.latest(profile, 'outlook', key=journal_key)
        numerical_valid = True
        if saved and saved.get('data_hash') == data_hash:
            result = deepcopy(saved)
        else:
            try:
                result = build_outlook(bars, calendar, end, benchmark=bm, sector=industry,
                                       min_reward_risk=min_reward_risk)
            except ValueError as error:
                numerical_valid = False
                result = build_outlook([], calendar, end, min_reward_risk=min_reward_risk)
                result['status'] = 'failed'
                result['limitations'].append('长期历史输入不满足完整性校验：' + str(error))
            result.update(code=code, version=VERSION, as_of=end, generated_at=now.isoformat(),
                          source=(raw or {}).get('source'), adjustment_basis=(adjusted or {}).get('adjustment_basis'),
                          data_hash=data_hash, demo=profile == 'demo', price_basis='raw',
                          raw_anchor=bars[-1]['close'] if bars else None,
                          qfq_anchor=bars[-1].get('adjusted_close') if bars else None)
            if result.get('forecasts'):
                svc.repo.append(profile, 'outlook', journal_key, result)
        # Data rejected by the numerical validator cannot be parsed again in
        # an unguarded evidence branch. Keep event metadata, withhold impacts.
        result['events'] = event_observations(selected_events, bars if numerical_valid else [], calendar, end,
                                              benchmark=bm if numerical_valid else [], sector=industry if numerical_valid else [])
        result['archive'] = archive_metrics(svc.repo.records(profile, 'outlook', limit=1000, key=journal_key),
                                            bars, calendar, now, (raw or {}).get('source'), as_of=end)
        if not valid_end:
            result['status'] = 'pending' if repairing or 'pending' in states else 'failed' if 'failed' in states else 'insufficient'
            result['limitations'].append('原始与复权日线必须同源，并覆盖最近完整交易日；当前没有混用来源训练预测')
        elif 'pending' in states:
            result['status'] = 'pending'
            result['limitations'].append('正在后台补齐所选股票的长期历史；完成后自动更新')
        elif 'failed' in states:
            result['status'] = 'partial' if result['forecasts'] else 'failed'
            result['limitations'].append('长期历史补齐失败；已有缓存研究保留，可重试')
        if not stock.get('identity_verified'):
            result['plan']['status'] = 'observe'
            result['plan']['reasons'].append('证券身份未核实，不能生成新增买入条件')
        if stock.get('st') is not False or stock.get('board') != 'main':
            result['plan']['status'] = 'observe'
            result['plan']['reasons'].append('ST状态或主板资格未满足当前新增买入范围')
        if material_risk:
            result['plan']['status'] = 'observe'
            result['plan']['reasons'].append('已核实重大风险，新增买入条件暂停')
        if profile == 'demo':
            result['limitations'].append('虚构样本；指标、模型验证和事件统计均不代表真实市场表现')
        result['limitations'] = list(dict.fromkeys(result['limitations'] + [
            '数值预测基于历史价格；事件比较是观察证据，尚未证明新闻对预测的增量效果',
            '区间覆盖率和价格误差不是交易胜率；未经过组合收益回测',
            '除权除息及未来公司行动可能改变实际价格；止损参考不保证成交',
        ]))
        return result
