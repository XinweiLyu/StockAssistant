"""Selected-stock refresh; unfinished source candles stay outside research history."""
from datetime import date, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo
from src.schemas.a_share import AssistantSettings
from src.schemas.a_share_market import MarketQuote

TZ=ZoneInfo('Asia/Shanghai')


def key_for(market,code):
    from src.services.a_share_market_service import configuration_stamp
    return 'live:'+code+':'+configuration_stamp(market.assistant.settings)


def read(market,code):
    market.stock(code)
    saved=market.repo.get_state(market.profile,key_for(market,code),{})
    value=dict(code=code,state='unavailable',task_id=None,requested_at=None,fetched_at=None,
               quote=market.repo.quotes(market.profile,[code]).get(code),bars={'raw':None,'qfq':None},
               provisional=False,source=None,adjustment_basis=None,message='尚未手动刷新最新行情',
               completed_day=market.completed_day(),history_updated=False,history_binding={'raw':None,'qfq':None},demo=market.profile=='demo')
    value.update(saved.get('result') or {})
    task=market.repo.task(saved.get('id')) if saved.get('id') else None
    value.update(task_id=saved.get('id'),requested_at=saved.get('requested_at'))
    if task and task['state']=='pending' and task.get('error'):
        value.update(state='failed',message='行情来源调用失败，队列等待重试；可点击按钮立即重试，原资料保留',history_updated=False)
    elif task and task['state'] in ('pending','running'):
        value.update(state='pending',message='正在获取所选股票最新日线快照；不调用AI')
    elif task and task['state']=='failed':
        value.update(state='failed',message='行情来源调用失败，已保留上次资料；可手动重试',history_updated=False)
    return value


def request(market,code):
    value=read(market,code)
    if market.profile=='demo':
        return value | dict(message='虚构样本不查询真实行情',state='unavailable')
    if value['state']=='pending':
        return value
    now=market.clock().astimezone(TZ)
    today=now.date().isoformat()
    if today not in market.calendar():
        return value | dict(state='unavailable',message='今天不是已核实交易日；保留最近交易日行情')
    end=date.fromisoformat(today)
    cached=[market.repo.get_history(market.profile,'stock:'+code,a,'1900-01-01',today) for a in ('raw','qfq')]
    starts=[v['requested_start'] for v in cached if v]
    # Refresh the existing cache's full span. Moving a five-year floor one day
    # forward must not silently discard the earliest cached observation.
    start=min(starts) if starts else (end-timedelta(days=500)).isoformat()
    key=key_for(market,code)
    identity=market._submit('stock_live','live-refresh:'+code+':'+uuid4().hex,-10,
                           code=code,start=start,end=today,pointer_key=key)
    market.repo.set_state(market.profile,key,dict(id=identity,requested_at=now.isoformat(),result=value))
    return read(market,code)


def handle(market,task,provider):
    from src.services.a_share_market_service import price_family
    payload,profile=task['payload'],task['profile']
    settings=AssistantSettings.model_validate(payload['settings'])
    code,start,end=payload['code'],payload['start'],payload['end']
    pointer=market.repo.get_state(profile,payload['pointer_key'],{})
    if pointer.get('id')!=task['id']:
        return
    previous=pointer.get('result') or {}
    def publish(result):
        with market._publication(task):
            current=market.repo.get_state(profile,payload['pointer_key'],{})
            if current.get('id')!=task['id']:
                return False
            market.repo.set_state(profile,payload['pointer_key'],current | {'result':result})
            return True
    cutoff=market.completed_day(profile)
    now=market.clock().astimezone(TZ)
    if end!=now.date().isoformat():
        publish(previous | dict(state='failed',history_updated=False,message='行情请求日期已过期，请重新刷新'))
        return
    prior={a:market.repo.get_history(profile,'stock:'+code,a,'1900-01-01',end) for a in ('raw','qfq')}
    sources=['tushare'] if profile.startswith('tushare') else ['akshare/eastmoney']
    if settings.free_fallback:
        sources+=['akshare/eastmoney','akshare/tencent','akshare/sina']
    preferred=price_family((prior['raw'] or {}).get('source'))
    sources=list(dict.fromkeys(([preferred] if preferred in sources else [])+sources))
    pair=None
    for source in sources:
        try:
            fetched={a:provider.history(code,start,end,a,source=source) for a in ('raw','qfq')}
            if any(p.code!=code or p.adjust!=a or price_family(p.source)!=source or not p.items
                   or p.items[-1].date!=end for a,p in fetched.items()):
                raise ValueError('当日日线尚未提供或来源身份不匹配')
            if any(min(b.open,b.high,b.low,b.close)<=0 for p in fetched.values() for b in p.items):
                raise ValueError('价格须为正数')
            if [b.date for b in fetched['raw'].items]!=[b.date for b in fetched['qfq'].items]:
                raise ValueError('日线日期未对齐')
            if cutoff>=end and abs(fetched['raw'].items[-1].close-fetched['qfq'].items[-1].close)>1e-6:
                raise ValueError('收盘原始与前复权锚点不同')
            pair=fetched
            break
        except (ValueError,RuntimeError,KeyError,TypeError):
            continue
    if pair is None:
        publish(previous | dict(state='failed',history_updated=False,
                                message='来源未提供有效当日开高低收，已保留上次资料；请稍后重试'))
        return
    raw,adjusted=pair['raw'],pair['qfq']
    # Turnover is in actual shares/CNY even when prices are adjusted. Use the
    # raw series' verified units (or unknown), not adjusted OHLC to infer them.
    adjusted.items=[b.model_copy(update={'volume':r.volume,'amount':r.amount}) for b,r in zip(adjusted.items,raw.items)]
    bar=raw.items[-1]
    quote=MarketQuote(code=code,name=market.repo.stock(profile,code)['name'],price=bar.close,
                      change=raw.latest_change,volume=bar.volume,amount=bar.amount,
                      source=raw.source,source_time=None,fetched_at=raw.fetched_at,trade_date=end).model_dump(mode='json')
    completed={a:[b for b in p.items if b.date<=cutoff] for a,p in pair.items()}
    covers=all(completed[a] and (not prior[a] or {b['date'] for b in prior[a]['items']}.issubset({b.date for b in completed[a]})) for a in pair)
    result=dict(code=code,state='ready',fetched_at=raw.fetched_at,quote=quote,
                bars={a:p.items[-1].model_dump(mode='json') for a,p in pair.items()},
                provisional=end>cutoff,source=raw.source,adjustment_basis=adjusted.adjustment_basis,
                completed_day=cutoff,history_updated=bool(covers),
                # Bind each live candle to the exact completed publication it was
                # fetched with. Source/date labels alone do not identify factors.
                history_binding={a:(dict(source=p.source,adjustment_basis=p.adjustment_basis,
                                        fetched_at=p.fetched_at,anchor_date=completed[a][-1].date,
                                        anchor_close=completed[a][-1].close) if covers else None)
                                 for a,p in pair.items()},demo=False,
                message=('当日临时K线未完成，不参与指标与预测。' if end>cutoff else '已获取当日收盘日线。')+
                        ' 来源未提供精确行情时间，显示实际获取时间。'+
                        (' 涨跌幅基准未提供，保留未知。' if raw.latest_change is None else '')+
                        ' '.join(raw.limitations)+
                        ('' if covers else ' 返回历史较短，已保留原长历史；仅更新最新报价。'))
    with market._publication(task):
        current=market.repo.get_state(profile,payload['pointer_key'],{})
        if current.get('id')!=task['id']:
            return
        with market.repo.engine.begin() as conn:
            if covers:
                for a,p in pair.items():
                    market.repo.replace_history(profile,'stock:'+code,a,p.source,p.adjustment_basis,completed[a],p.fetched_at,
                                                requested_start=start,requested_end=cutoff,conn=conn)
            market.repo.put_quotes(profile,'manual:'+task['id'],[quote],update_batch=False,conn=conn)
            market.repo.set_state(profile,payload['pointer_key'],current | {'result':result},conn=conn)
