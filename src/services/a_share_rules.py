"""Versioned daily research rules. Scores are ranks, never probabilities.

Quotes only check a saved daily condition; they are not five-minute candles.
All monetary inputs use CNY and quantities use shares.
"""
from __future__ import annotations

from datetime import datetime, time
from math import floor, isfinite
from statistics import mean, stdev
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Shanghai')
DEFAULT_RISK = dict(stock_cap=.10, sector_cap=.20, total_cap=.60,
                    risk_per_trade=.005, commission=.0003, minimum_fee=5., transfer_fee=.00001)


def positive(value):
    return isinstance(value, (float, int)) and isfinite(value) and value > 0


def indicators(bars, as_of, require_amount=True):
    rows = sorted([r for r in bars if r['date'] <= as_of], key=lambda r: r['date'])
    if len(rows) < 120 or rows[-1]['date'] != as_of:
        raise ValueError('完整日线不足120条或截止日期不一致')
    if len({r['date'] for r in rows}) != len(rows):
        raise ValueError('日线日期重复')
    for r in rows:
        if not all(positive(r.get(k)) for k in ('close', 'high', 'low', 'adjusted_close')):
            raise ValueError('价格或复权缺失')
        if r['low'] > r['close'] or r['close'] > r['high']:
            raise ValueError('OHLC无效')
    prices = [r['adjusted_close'] for r in rows]
    # Rebase adjusted history to last actual closing price before ATR/trigger comparisons.
    scale = rows[-1]['close'] / prices[-1]
    closes = [p * scale for p in prices]
    trs = []
    for i in range(len(rows) - 20, len(rows)):
        r = rows[i]
        factor = r['adjusted_close'] / r['close'] * scale
        hi, lo, prev = r['high'] * factor, r['low'] * factor, closes[i-1]
        trs.append(max(hi - lo, abs(hi - prev), abs(lo - prev)))
    amounts = [r.get('amount') for r in rows[-20:]]
    if require_amount and not all(positive(v) for v in amounts):
        raise ValueError('成交额缺失')
    return dict(r20=prices[-1]/prices[-21]-1, r60=prices[-1]/prices[-61]-1,
                v20=stdev([prices[i]/prices[i-1]-1 for i in range(len(prices)-20, len(prices))]),
                sma20=mean(closes[-20:]), sma60=mean(closes[-60:]), atr=mean(trs),
                close=rows[-1]['close'], high=rows[-1]['high'], avg_amount=mean(amounts) if all(positive(v) for v in amounts) else None)


def percentile(values):
    if len(values) == 1:
        return [.5]
    if not values:
        return []
    ordered=sorted(enumerate(values),key=lambda item:item[1])
    result=[0.] * len(values)
    i=0
    while i<len(ordered):
        j=i+1
        while j<len(ordered) and ordered[j][1]==ordered[i][1]:
            j+=1
        rank=(i+j-1)/2/(len(values)-1)
        for index,_ in ordered[i:j]:
            result[index]=rank
        i=j
    return result


def complete_sessions(bars, calendar, as_of, count=120):
    expected=[d for d in sorted(set(calendar or [])) if d<=as_of][-count:]
    available={r['date'] for r in bars}
    if len(expected)<count or any(d not in available for d in expected):
        raise ValueError('交易日历或最近120个完整交易日日线存在空缺')


def validate_daily(bars, calendar, as_of, require_amount=True):
    complete_sessions(bars,calendar,as_of)
    return indicators(bars,as_of,require_amount=require_amount)


def rank_universe(stocks, sectors, benchmark, as_of, demo=False, calendar=None):
    valid, exclusions, sector_valid = [], [], []
    for stock in stocks:
        try:
            if not demo:
                complete_sessions(stock['bars'],calendar,as_of)
            m = indicators(stock['bars'], as_of)
            if stock.get('st') is not False or stock.get('suspended') is not False:
                raise ValueError('ST/停牌状态缺失或不适合新增买入')
            if stock.get('listed_sessions', 0) < 120 or m['avg_amount'] < 50_000_000:
                raise ValueError('上市时间或流动性不足')
            if not demo and not stock['code'].startswith(('600', '601', '603', '605', '000', '001', '002')):
                raise ValueError('当前仅研究沪深主板新增买入')
            valid.append({k:v for k,v in stock.items() if k != 'bars'} | m)
        except (ValueError, KeyError, TypeError) as exc:
            exclusions.append(dict(code=stock.get('code'), reason=str(exc)))
    for sector in sectors:
        try:
            if not demo:
                complete_sessions(sector['bars'],calendar,as_of)
            sector_valid.append({k:v for k,v in sector.items() if k != 'bars'} | indicators(sector['bars'], as_of, require_amount=False))
        except (ValueError, KeyError, TypeError):
            continue
    market_ok = None
    try:
        if not demo:
            complete_sessions(benchmark,calendar,as_of)
        bm = indicators(benchmark, as_of, require_amount=False)
        market_ok = bm['close'] > bm['sma60']
    except (ValueError, KeyError, TypeError):
        pass
    sector_ready = len(sector_valid) >= 10 and len({s.get('classification') for s in sector_valid}) == 1
    if sector_ready:
        a, b = percentile([s['r20'] for s in sector_valid]), percentile([s['r60'] for s in sector_valid])
        for i,s in enumerate(sector_valid):
            s['strength'] = round(100*(.6*a[i]+.4*b[i]), 2)
    sector_map = {s['code']:s for s in sector_valid}
    ready = len(valid) >= (1 if demo else 30)
    candidates = []
    if ready:
        r20, r60, v20 = [percentile([s[k] if k != 'v20' else -s[k] for s in valid]) for k in ('r20','r60','v20')]
        for i,s in enumerate(valid):
            scores = [('trend_v1', 100*(.5*r20[i]+.3*r60[i]+.2*v20[i]))]
            sector = sector_map.get(s.get('sector'))
            if sector_ready and sector:
                scores.append(('sector_trend_v1',100*(.4*r20[i]+.25*sector['strength']/100+.2*r60[i]+.15*v20[i])))
            for strategy, score in scores:
                if score < 70 or not s['close'] > s['sma20'] > s['sma60']:
                    continue
                if strategy == 'sector_trend_v1' and sector['strength'] < 70:
                    continue
                candidates.append(s | dict(strategy=strategy, score=round(score,2), as_of=as_of,
                                           entry=s['high'], market_ok=market_ok, status='observe'))
    candidates.sort(key=lambda x:(-x['score'], x['code'], x['strategy']))
    return dict(candidates=[c for strategy in ('trend_v1','sector_trend_v1') for c in [s for s in candidates if s['strategy']==strategy][:20]], sectors=sorted(sector_valid,key=lambda s:-s.get('strength',0)),
                market_ok=market_ok, sample_size=len(valid), sector_ready=sector_ready,
                limitations=[] if ready else ['可用同日研究样本不足30只，暂停真实候选排名'], exclusions=exclusions)


def buy_plan(candidate, account, risk):
    cfg = DEFAULT_RISK | risk
    entry, atr = candidate.get('entry'), candidate.get('atr')
    reason = []
    if not positive(entry) or not positive(atr):
        return dict(entry=entry, quantity=None, stop=None, reasons=['价格/ATR缺失'])
    stop = entry - 2*atr
    if not .02 <= 2*atr/entry <= .10:
        reason.append('止损距离不在2%–10%范围')
    if not account or not account.get('complete') or not positive(account.get('nav')) or not candidate.get('sector'):
        return dict(entry=entry, quantity=None, stop=round(stop,4), reasons=reason+['账户净值、持仓估值或行业覆盖不完整'])
    nav = account['nav']
    cap = min(max(0,nav*cfg['stock_cap']-account['stock_value']),
              max(0,nav*cfg['sector_cap']-account['sector_value']),
              max(0,nav*cfg['total_cap']-account['total_value']), max(0,account['cash']))
    qty = floor(min(nav*cfg['risk_per_trade']/(entry-stop), cap/entry)/100)*100
    while qty > 0 and qty*entry + max(cfg['minimum_fee'],qty*entry*cfg['commission']) + qty*entry*cfg['transfer_fee'] > cap:
        qty -= 100
    if reason:
        qty = 0
    if qty == 0 and not reason:
        reason.append('现金或仓位上限不足一个100股手数')
    return dict(entry=entry, quantity=qty, stop=round(stop,4), reasons=reason,
                planned_risk=round(qty*(entry-stop),2), max_stock_pct=cfg['stock_cap'])


def session_slot(now, calendar):
    now = now.astimezone(TZ)
    t = now.time().replace(tzinfo=None,second=0,microsecond=0)
    if now.date().isoformat() not in calendar:
        return None
    if not (time(9,35) <= t <= time(11,30) or time(13,5) <= t <= time(15,0)):
        return None
    return now.replace(minute=now.minute//5*5).strftime('%Y-%m-%dT%H:%M')


def quote_issues(quote, now):
    issues = []
    if not quote or not positive(quote.get('price')):
        return ['报价缺失/无效']
    source_time = quote.get('source_time')
    try:
        source_time = datetime.fromisoformat(source_time)
        if source_time.tzinfo is None:
            raise ValueError()
        age = (now-source_time).total_seconds()
        if age < -60 or age > 600:
            issues.append('报价已过期/来源时间异常')
    except (ValueError, TypeError):
        issues.append('源延迟未知，只供观察')
    if quote.get('trade_date') != now.astimezone(TZ).date().isoformat():
        issues.append('报价交易日期不一致')
    if quote.get('suspended') is not False:
        issues.append('停牌状态未知/停牌')
    if not positive(quote.get('limit_up')) or not positive(quote.get('limit_down')):
        issues.append('涨跌停价格未核实')
    elif quote['limit_down']>=quote['limit_up'] or quote['price'] >= quote['limit_up'] or quote['price'] <= quote['limit_down']:
        issues.append('涨跌停可能无法成交')
    if quote.get('cumulative_regressed'):
        issues.append('累计成交额回退')
    return issues


def check_trigger(candidate, quote, account, now, calendar, risk):
    issues = quote_issues(quote, now)
    status = 'observe'
    today = now.astimezone(TZ).date().isoformat()
    if candidate.get('valid_date') != today or now.astimezone(TZ).time().replace(tzinfo=None)>time(15,0):
        return dict(status='expired' if (candidate.get('valid_date') or '') <= today else 'observe', reasons=['条件未到有效日或已失效'])
    if candidate.get('major_risk') or candidate.get('market_ok') is not True:
        return dict(status='blocked', reasons=['已核实重大风险或市场环境不允许新增买入'])
    if not session_slot(now, calendar):
        issues.append('非连续交易时段或交易日历缺失')
    p = quote.get('price') if quote else None
    if positive(p) and candidate['high'] < p <= candidate['high']*1.01:
        plan = buy_plan(candidate | {'entry':p},account,risk)
        issues += plan['reasons']
        if plan['quantity'] is None or plan['quantity'] == 0:
            issues.append('无法确定合规计划股数')
        if not issues:
            status = 'triggered'
        return dict(status=status, reasons=issues, plan=plan)
    return dict(status=status, reasons=issues+['价格未突破前高或超过1%追高范围'])


def holding_risk(holding, quote, now, calendar=None):
    issues = quote_issues(quote, now)
    action = '持有观察'
    price = quote.get('price') if quote else None
    if holding.get('major_risk'):
        action = '重大风险待处理'
    elif positive(price) and positive(holding.get('stop')) and price <= holding['stop']:
        action = '退出条件触发' if not issues else '退出条件待报价核实'
    elif holding.get('overexposed'):
        action = '仓位超限待评估'
    elif holding.get('held_sessions',0) >= 20:
        action = '持有满20交易日待评估'
    elif holding.get('daily_close',float('inf')) < holding.get('sma60',0):
        action = '日线退出观察'
    elif holding.get('daily_close',float('inf')) < holding.get('sma20',0):
        action = '日线减仓观察'
    if not session_slot(now,calendar or []) or now.astimezone(TZ).time().replace(tzinfo=None)>time(15,0):
        issues.append('当前不具备交易时段及日历核实条件')
    sellable = holding.get('sellable')
    if sellable is None:
        issues.append('T+1可卖数量未确认')
    elif not isfinite(sellable) or sellable > holding.get('quantity',0):
        issues.append('可卖数量超过持仓或无效')
    elif sellable <= 0:
        issues.append('T+1当日无可卖数量')
    return dict(code=holding['code'], action=action, sellable=sellable,
                executable=not issues and positive(sellable), reasons=issues, stop=holding.get('stop'))


def forward_observation(saved_date, bars, calendar, horizons=(5,10,20)):
    dates = sorted(set(calendar))
    subsequent = [d for d in dates if d > saved_date]
    lookup = {r['date']:r.get('adjusted_close') for r in bars}
    result = []
    for h in horizons:
        start = subsequent[0] if subsequent else None
        end = subsequent[h] if len(subsequent) > h else None
        a, b = lookup.get(start), lookup.get(end)
        ret = b/a-1 if positive(a) and positive(b) else None
        result.append(dict(horizon=h,start_date=start,end_date=end,**{'return':ret},
                           limitation=None if ret is not None else '尚未到期或固定端点数据缺失',
                           kind='候选价格观察，非账户收益'))
    return result
