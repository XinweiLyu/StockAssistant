"""Pure, chronological multi-cycle research; numerical forecasts never call an LLM.

All displayed levels use adjusted return history rebased to the last raw close.
The ridge baseline is a price-only statistical reference, not a trading strategy.
Each historical forecast fits preprocessing and forward labels available at its
own close. Its interval uses earlier, matured out-of-sample residuals only.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from math import exp, isfinite, log
import re
from zoneinfo import ZoneInfo

import numpy as np

VERSION = 'price-ridge-outlook-v1'
HORIZONS = (5, 20, 60)
PERIODS = (20, 60, 120, 250)
FEATURE_START = 249
MIN_TRAIN = 80
MIN_RESIDUALS = 8
MIN_EVENTS = 5
NOMINAL_COVERAGE = .8
RIDGE = 10.0
TZ = ZoneInfo('Asia/Shanghai')
METHOD = 'ridge_log_return_v1; rolling-origin purged non-overlapping; historical residual quantiles'


def _number(value, *, zero=False):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and isfinite(value) and (value >= 0 if zero else value > 0)


def _day(value):
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError('日期须为ISO日历日期') from exc


def _rows(bars, as_of):
    rows = []
    for item in bars or ():
        if not isinstance(item, dict):
            raise ValueError('日线须为字段映射')
        day = _day(item.get('date'))
        if day > as_of:
            continue
        if not all(_number(item.get(k)) for k in ('open', 'high', 'low', 'close')):
            raise ValueError('日线价格须为有限正数')
        if item['low'] > min(item['open'], item['close']) or item['high'] < max(item['open'], item['close']) or item['low'] > item['high']:
            raise ValueError('OHLC价格不一致')
        if item.get('adjusted_close') is not None and not _number(item['adjusted_close']):
            raise ValueError('复权价格须为有限正数')
        if any(item.get(k) is not None and not _number(item[k], zero=True) for k in ('volume', 'amount')):
            raise ValueError('成交量/额须为有限非负数')
        rows.append(dict(item, date=day))
    rows.sort(key=lambda r: r['date'])
    if len({r['date'] for r in rows}) != len(rows):
        raise ValueError('日线日期重复')
    return rows


def _calendar(calendar):
    return sorted({_day(d) for d in calendar or ()})


def _complete(rows, calendar, as_of):
    if not rows or not calendar:
        return False
    expected = [d for d in calendar if rows[0]['date'] <= d <= as_of]
    return expected == [r['date'] for r in rows]


def _adjusted(rows):
    return bool(rows) and all(_number(r.get('adjusted_close')) for r in rows)


def _price_series(rows):
    adjusted = _adjusted(rows)
    values = np.array([r['adjusted_close'] if adjusted else r['close'] for r in rows], dtype=float)
    scale = rows[-1]['close'] / values[-1] if rows else 1.0
    return values * scale


def _trend(values, period):
    if len(values) < period:
        return dict(period=period, ma=None, distance=None, slope=None, state='insufficient')
    ma = float(np.mean(values[-period:]))
    distance = float(values[-1] / ma - 1)
    slope = float(ma / np.mean(values[-period - 5:-5]) - 1) if len(values) >= period + 5 else None
    state = 'insufficient' if slope is None else 'range'
    if slope is not None and distance > .005 and slope > .001:
        state = 'up'
    elif slope is not None and distance < -.005 and slope < -.001:
        state = 'down'
    return dict(period=period, ma=ma, distance=distance, slope=slope, state=state)


def _week(day):
    d = date.fromisoformat(day)
    return d - timedelta(days=d.weekday())


def _weekly(rows, calendar, as_of, values):
    result = dict(as_of=None, ma10=None, ma30=None, state='insufficient')
    if not rows or not calendar:
        return result
    by_date = {r['date']: float(v) for r, v in zip(rows, values)}
    weeks = defaultdict(list)
    for d in calendar:
        weeks[_week(d)].append(d)
    completed = []
    cutoff = date.fromisoformat(as_of)
    calendar_end = date.fromisoformat(calendar[-1])
    for monday, days in sorted(weeks.items()):
        # A calendar spanning the following week can prove a shortened holiday
        # week has finished. A truncated Wednesday-only calendar cannot.
        finished = cutoff >= monday + timedelta(days=4) or (
            calendar_end >= monday + timedelta(days=7) and days[-1] <= as_of)
        if finished and days[-1] <= as_of and all(d in by_date for d in days):
            completed.append((days[-1], by_date[days[-1]]))
        elif completed and days[-1] <= as_of:
            # A missing week breaks weekly warmup; never compress suspension gaps.
            completed = []
    if not completed:
        return result
    result['as_of'] = completed[-1][0]
    closes = np.array([v for _, v in completed])
    if len(closes) >= 10:
        result['ma10'] = float(np.mean(closes[-10:]))
    if len(closes) >= 30:
        result['ma30'] = float(np.mean(closes[-30:]))
        result['state'] = 'range'
        if closes[-1] > result['ma10'] > result['ma30']:
            result['state'] = 'up'
        elif closes[-1] < result['ma10'] < result['ma30']:
            result['state'] = 'down'
    return result


def _technical(rows, calendar, as_of):
    values = _price_series(rows)
    trends = []
    for period in PERIODS:
        tail = rows[-period - 5:]
        if tail and _complete(tail, calendar, as_of):
            trends.append(_trend(values, period))
        else:
            trends.append(dict(period=period, ma=None, distance=None, slope=None, state='insufficient'))
    return dict(trends=trends, weekly=_weekly(rows, calendar, as_of, values))


def technical_summary(bars, calendar, as_of):
    """Cheap reusable long-cycle facts for existing price evidence; no model fit."""
    as_of = _day(as_of)
    return _technical(_rows(bars, as_of), _calendar(calendar), as_of)


def _relative(rows, other, calendar, as_of, horizon):
    dates = [d for d in calendar if d <= as_of][-horizon - 1:]
    own, peer = {r['date']: r for r in rows}, {r['date']: r for r in other}
    if len(dates) != horizon + 1 or any(d not in own or d not in peer for d in dates):
        return None
    if any(not _number(own[d].get('adjusted_close')) or not _number(peer[d].get('adjusted_close')) for d in dates):
        return None
    a, b = dates[0], dates[-1]
    return float(own[b]['adjusted_close'] / own[a]['adjusted_close'] - peer[b]['adjusted_close'] / peer[a]['adjusted_close'])


def _environment(rows, benchmark, sector, calendar, as_of):
    state = 'unknown'
    if len(benchmark) >= 65 and _adjusted(benchmark[-65:]) and _complete(benchmark[-65:], calendar, as_of):
        state = _trend(_price_series(benchmark[-65:]), 60)['state']
    return dict(market_state=state, relative20=_relative(rows, benchmark, calendar, as_of, 20),
                relative60=_relative(rows, benchmark, calendar, as_of, 60),
                sector_relative20=_relative(rows, sector, calendar, as_of, 20),
                sector_relative60=_relative(rows, sector, calendar, as_of, 60))


def _features(prices):
    """Backward-only features; no preprocessing is fitted over this array."""
    logs = np.log(prices)
    matrix = np.full((len(prices), 10), np.nan)
    for i in range(FEATURE_START, len(prices)):
        p = prices[i]
        window = prices[i - 19:i + 1]
        distances = [p / np.mean(prices[i - period + 1:i + 1]) - 1 for period in PERIODS]
        matrix[i] = [logs[i] - logs[i - h] for h in (5, 20, 60)] + distances + [
            float(np.std(np.diff(logs[i - 20:i + 1]), ddof=1)),
            float(np.max(window) / np.min(window) - 1),
            float(np.mean(prices[i - 19:i + 1]) / np.mean(prices[i - 24:i - 4]) - 1)]
    return matrix, logs


def _fit_predict(matrix, logs, origin, horizon):
    last_origin = origin - horizon
    if last_origin - FEATURE_START + 1 < MIN_TRAIN:
        return None
    # Training labels end no later than the issuance close: explicit h-session purge.
    x = matrix[FEATURE_START:last_origin + 1]
    y = logs[FEATURE_START + horizon:last_origin + horizon + 1] - logs[FEATURE_START:last_origin + 1]
    center, scale = np.mean(x, axis=0), np.std(x, axis=0)
    scale = np.where(scale > 1e-10, scale, 1.0)
    normalized = (x - center) / scale
    y_center = float(np.mean(y))
    weights = np.linalg.solve(normalized.T @ normalized + RIDGE * np.eye(matrix.shape[1]), normalized.T @ (y - y_center))
    prediction = float(y_center + ((matrix[origin] - center) / scale) @ weights)
    if not isfinite(prediction):
        return None
    return prediction, len(y), last_origin + horizon


def _quantiles(values):
    return tuple(float(v) for v in np.quantile(values, (.1, .5, .9)))


def _price_at(anchor, log_return):
    # Numerical guard, not a target constraint: do not fabricate bounded levels.
    try:
        result = anchor * exp(log_return)
    except OverflowError:
        return None
    return result if _number(result) else None


def _model(rows, matrix, logs, horizon, calendar):
    last = len(rows) - 1
    fitted = _fit_predict(matrix, logs, last, horizon)
    if fitted is None:
        return None
    residuals, audit, errors, baseline_errors, covered = [], [], [], [], []
    first = FEATURE_START + MIN_TRAIN - 1 + horizon
    # Spacing at least h ensures no two validation outcome windows overlap.
    for origin in range(first, last - horizon + 1, max(20, horizon)):
        prediction, _, train_end = _fit_predict(matrix, logs, origin, horizon)
        actual = float(logs[origin + horizon] - logs[origin])
        historical = len(residuals) >= MIN_RESIDUALS
        low, bias, high = _quantiles(residuals) if historical else (0., 0., 0.)
        adjusted_prediction = prediction + bias
        raw = rows[origin]['close']
        forecast_price, actual_price = _price_at(raw, adjusted_prediction), _price_at(raw, actual)
        if forecast_price is None or actual_price is None:
            return None
        errors.append(abs(forecast_price - actual_price))
        baseline_errors.append(abs(raw - actual_price))
        if historical:
            covered.append(prediction + low <= actual <= prediction + high)
        audit.append(dict(origin_date=rows[origin]['date'], target_date=rows[origin + horizon]['date'],
                          last_training_label_date=rows[train_end]['date'], predicted_log_return=adjusted_prediction,
                          calibration_last_target_date=audit[-1]['target_date'] if historical else None))
        residuals.append(actual - prediction)
    if len(residuals) < MIN_RESIDUALS:
        return None
    prediction, sample_size, _ = fitted
    qlow, bias, qhigh = _quantiles(residuals)
    levels = [_price_at(rows[-1]['close'], prediction + q) for q in (qlow, bias, qhigh)]
    if any(v is None for v in levels):
        return None
    future = [d for d in calendar if d > rows[-1]['date']]
    target = future[horizon - 1] if len(future) >= horizon else None
    validation = dict(state='measured', samples=len(audit), coverage=float(np.mean(covered)) if len(covered) >= MIN_RESIDUALS else None,
                      coverage_samples=len(covered), mean_absolute_error=float(np.mean(errors)),
                      baseline_mean_absolute_error=float(np.mean(baseline_errors)),
                      method='rolling-origin purged non-overlapping; price error rebased to each origin raw close', origins=audit)
    return dict(horizon_sessions=horizon, target_date=target, low=levels[0], median=levels[1], high=levels[2],
                sample_size=sample_size, calibration_samples=len(residuals), method=METHOD,
                nominal_coverage=NOMINAL_COVERAGE, calibration_state='historical', validation=validation)


def _plan(rows, forecasts, technical, environment, ratio):
    result = dict(status='observe', horizon_sessions=20, entry_low=None, entry_high=None, stop=None,
                  target_low=None, target_high=None, reward_risk=None, min_reward_risk=ratio,
                  valid_until=None, conditions=['长周期与已完成周线趋势维持', '价格基线通过历史比较且盈亏比达标', '大盘趋势及个股相对强度保持'],
                  invalidation=['止损观察参考被触及', '长周期趋势或大盘环境转弱', '新数据改变预测或观察期限到期'], reasons=[])
    forecast = next((f for f in forecasts if f['horizon_sessions'] == 20), None)
    if forecast is None or len(rows) < 21 or not _adjusted(rows[-21:]):
        result['reasons'].append('20交易日预测的历史样本或复权价格不足')
        return result
    current = rows[-1]['close']
    scale = current / rows[-1]['adjusted_close']
    closes = np.array([r['adjusted_close'] * scale for r in rows[-21:]])
    highs = np.array([r['high'] * r['adjusted_close'] / r['close'] * scale for r in rows[-20:]])
    lows = np.array([r['low'] * r['adjusted_close'] / r['close'] * scale for r in rows[-20:]])
    atr = float(np.mean(np.maximum.reduce([highs - lows, np.abs(highs - closes[:-1]), np.abs(lows - closes[:-1])])))
    entry_low, stop = current - .5 * atr, float(np.min(lows) - .5 * atr)
    result.update(entry_low=entry_low if entry_low > 0 else None, entry_high=current,
                  stop=stop if stop > 0 else None, target_low=forecast['median'], target_high=forecast['high'],
                  valid_until=forecast['target_date'])
    risk = current - stop
    reward = forecast['median'] - current
    result['reward_risk'] = reward / risk if risk > 0 and stop > 0 else None
    if result['reward_risk'] is None or result['reward_risk'] < ratio:
        result['reasons'].append('独立预测目标对应的盈亏比未达门槛，维持观察')
    if any(t['state'] != 'up' for t in technical['trends'] if t['period'] in (60, 120, 250)) or technical['weekly']['state'] != 'up':
        result['reasons'].append('长周期或已完成周线趋势未同步向上')
    if environment['market_state'] != 'up' or environment['relative20'] is None or environment['relative20'] <= 0:
        result['reasons'].append('大盘环境或相对强度不足/未知')
    v = forecast['validation']
    if v['state'] != 'measured' or v['mean_absolute_error'] >= v['baseline_mean_absolute_error']:
        result['reasons'].append('历史价格误差未优于价格不变基线')
    if not result['reasons']:
        result['status'] = 'conditional'
    return result


def _timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.replace(tzinfo=TZ) if parsed.tzinfo is None else parsed.astimezone(TZ)
    except ValueError:
        return None


def _kind(event):
    if event.get('kind') and event['kind'] not in ('unknown', 'other', 'news'):
        return str(event['kind'])
    title = str(event.get('title', ''))
    for kind, pattern in (('risk', '处罚|立案|调查|退市|重大风险|风险警示'),
                          ('earnings', '业绩|盈利|利润|财报|earnings'),
                          ('corporate_action', '分红|除权|配股|拆股|dividend'),
                          ('shareholding', '增持|减持|股权|回购'), ('policy', '政策|监管|policy'),
                          ('sector', '行业|产业')):
        if re.search(pattern, title, re.I):
            return kind
    return 'other'


def _deduplicate(events, as_of):
    grouped = defaultdict(list)
    for event in events or ():
        if not isinstance(event, dict):
            continue
        key = str(event.get('event_key') or event.get('url') or event.get('id') or
                  (str(event.get('source', '')) + ':' + str(event.get('title', '')) + ':' + str(event.get('published_at', ''))))
        grouped[key].append(event)
    end = datetime.combine(date.fromisoformat(as_of), time.max, TZ)
    result = []
    for key, revisions in sorted(grouped.items()):
        ordered = sorted(revisions, key=lambda e: (_timestamp(e.get('first_seen')) or datetime.max.replace(tzinfo=TZ), str(e.get('id', ''))))
        first = ordered[0]
        available = [e for e in ordered if (_timestamp(e.get('revised_at') or e.get('first_seen')) or end) <= end]
        selected = max(available, key=lambda e: (_timestamp(e.get('revised_at') or e.get('first_seen')) or end, str(e.get('revision', '')), str(e.get('id', '')))) if available else first
        result.append(dict(selected, event_key=key, first_seen=first.get('first_seen'),
                           published_at=first.get('published_at'), source=first.get('source'), kind=_kind(first)))
    return result


def event_observations(events, bars, calendar, as_of, *, benchmark=(), sector=()):
    """Descriptive same-category observations; revisions are one event, never causal estimates.

    Timestamped observations before the close align to that response session.
    Date-only availability is conservatively aligned to the following session.
    Missing first-seen, verification, prices, benchmark or maturity stays unknown.
    Sector is accepted for the shared API; benchmark excess is never silently
    replaced by sector excess or by unadjusted stock returns.
    """
    as_of = _day(as_of)
    days = _calendar(calendar)
    own = {r['date']: r for r in _rows(bars, as_of)}
    peer = {r['date']: r for r in _rows(benchmark, as_of)}
    outcomes, annotations = defaultdict(list), []
    for event in _deduplicate(events, as_of):
        seen, published = _timestamp(event.get('first_seen')), _timestamp(event.get('published_at'))
        # Date precision describes a whole day, not an observed 00:00 arrival.
        # Publication at 09:00 does not improve a date-only ingestion timestamp.
        if seen and len(str(event.get('first_seen', ''))) == 10:
            seen = seen.replace(hour=23, minute=59, second=59, microsecond=999999)
        if published and len(str(event.get('published_at', ''))) == 10:
            published = published.replace(hour=23, minute=59, second=59, microsecond=999999)
        effective = max(seen, published) if seen and published else seen
        # A publication day alone is not evidence that our system knew the item.
        precision_day = effective is not None and ((seen == effective and len(str(event.get('first_seen', ''))) == 10) or
                                                  (published == effective and len(str(event.get('published_at', ''))) == 10))
        response = None
        if effective:
            day = effective.date().isoformat()
            after_close = precision_day or effective.time().replace(tzinfo=None) >= time(15)
            response = next((i for i, d in enumerate(days) if d > day or (d == day and not after_close)), None)
        horizon = 5
        impact = dict(state='insufficient', samples=0, horizon_sessions=horizon, median_excess=None, low=None, high=None,
                      reason='首次可用时间、验证、成熟期或同日基准数据不足；事件观察不代表因果影响')
        observation = dict(id=str(event.get('id', event['event_key'])), event_key=event['event_key'],
                           title=str(event.get('title', '')), url=event.get('url'),
                           date=days[response] if response is not None else None,
                           published_at=event.get('published_at'), first_seen=event.get('first_seen'),
                           source=event.get('source'), kind=event['kind'], verified=event.get('verified') is True, impact=impact)
        annotations.append(observation)
        if event['kind'] == 'other' or not observation['verified'] or response is None or response < 1 or response + horizon - 1 >= len(days):
            continue
        window = days[response - 1:response + horizon]
        if window[-1] > as_of or any(d not in own or d not in peer for d in window):
            continue
        if any(not _number(own[d].get('adjusted_close')) or not _number(peer[d].get('adjusted_close')) for d in window):
            continue
        a, b = window[0], window[-1]
        excess = own[b]['adjusted_close'] / own[a]['adjusted_close'] - peer[b]['adjusted_close'] / peer[a]['adjusted_close']
        outcomes[event['kind']].append((response - 1, response + horizon - 1, float(excess), observation))
    for kind, values in outcomes.items():
        independent, last_end = [], -1
        for start, end, excess, annotation in sorted(values, key=lambda v: (v[0], v[3]['event_key'])):
            if start >= last_end:
                independent.append(excess)
                last_end = end
        for _, _, _, annotation in values:
            impact = annotation['impact']
            impact['samples'] = len(independent)
            if len(independent) >= MIN_EVENTS:
                low, median, high = _quantiles(independent)
                impact.update(state='observed', median_excess=median, low=low, high=high,
                              reason='同类已验证事件的非重叠5交易日基准超额收益观察；非新闻预测模型，不能证明因果关系')
            else:
                impact['reason'] = '同类成熟、对齐且非重叠的事件样本不足5个；不能估计稳定影响'
    return sorted(annotations, key=lambda e: (e['date'] or '9999', e['event_key']), reverse=True)


def build_outlook(bars, calendar, as_of, *, benchmark=(), sector=(), events=(), min_reward_risk=2.0):
    """Build deterministic numerical, technical, risk-plan and event observations."""
    if not _number(min_reward_risk) or not 1 <= min_reward_risk <= 5:
        raise ValueError('最小盈亏比须为1–5之间的有限数值')
    as_of = _day(as_of)
    rows, days = _rows(bars, as_of), _calendar(calendar)
    benchmark, sector = _rows(benchmark, as_of), _rows(sector, as_of)
    technical = _technical(rows, days, as_of)
    environment = _environment(rows, benchmark, sector, days, as_of)
    limitations = ['历史价格误差和区间覆盖不代表投资组合收益；名义80%区间不是已验证准确率',
                   '价格模型仅使用过去价格特征，不是已训练新闻或基本面预测模型；未建模交易成本、涨跌停或成交约束']
    complete, adjusted = _complete(rows, days, as_of), _adjusted(rows)
    forecasts = []
    if not complete:
        limitations.append('交易日历或完整日线存在空缺，暂停按交易日计算价格预测')
    if rows and not adjusted:
        limitations.append('完整复权历史不可得；原价技术参考保留，暂停训练以避免公司行动污染收益标签')
    if complete and adjusted and len(rows) >= FEATURE_START + MIN_TRAIN:
        matrix, logs = _features(np.array([r['adjusted_close'] for r in rows], dtype=float))
        needed = (1, 3, 5, 10, 20, 40, 60)
        models = {h: _model(rows, matrix, logs, h, days) for h in needed}
        points = {5: (1, 3, 5), 20: (5, 10, 20), 60: (20, 40, 60)}
        for h in HORIZONS:
            model = models[h]
            if model is not None:
                model['points'] = [dict(sessions=k, date=models[k]['target_date'], low=models[k]['low'],
                                        median=models[k]['median'], high=models[k]['high']) for k in points[h] if models[k] is not None]
                forecasts.append(model)
    for h in HORIZONS:
        if not any(f['horizon_sessions'] == h for f in forecasts):
            limitations.append(f'{h}交易日基线的训练或成熟非重叠残差样本不足，暂不发布区间')
    if forecasts and any(f['target_date'] is None for f in forecasts):
        limitations.append('未来交易日历覆盖不足，目标日期保持未知；期限为交易日数量')
    if environment['market_state'] == 'unknown':
        limitations.append('同日大盘复权数据不足，市场环境未知')
    plan = _plan(rows, forecasts, technical, environment, float(min_reward_risk))
    status = 'ready' if len(forecasts) == len(HORIZONS) else ('partial' if rows and (forecasts or len(rows) >= 20) else 'insufficient')
    return dict(status=status, version=VERSION, as_of=as_of, history_sessions=len(rows),
                reference_price=rows[-1]['close'] if rows else None, price_basis='raw',
                raw_anchor=rows[-1]['close'] if rows else None, qfq_anchor=rows[-1].get('adjusted_close') if rows else None,
                **technical, environment=environment, forecasts=forecasts, plan=plan,
                events=event_observations(events, rows, days, as_of, benchmark=benchmark, sector=sector), limitations=limitations)
