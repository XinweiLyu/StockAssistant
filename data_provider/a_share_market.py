"""Market adapters preserving actual price fields, identity and provenance."""
from __future__ import annotations
from datetime import datetime, date
from zoneinfo import ZoneInfo
from data_provider.a_share import number, normalize_spot, normalize_alternate_spot
from src.schemas.a_share_market import MarketStock, MarketBar, MarketQuote, SectorRecord, HistoryPage


def now():
    return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()


def code_of(value):
    value=str(value or '').strip().removeprefix('sh').removeprefix('sz').removeprefix('bj')
    if value.isdigit() and len(value)<=6:
        return value.zfill(6)
    raise ValueError('来源证券代码无效')


def day_of(value):
    text=str(value or '')[:10]
    if len(text)==8 and text.isdigit():
        text=text[:4]+'-'+text[4:6]+'-'+text[6:]
    return date.fromisoformat(text).isoformat()


def normalize_listing(rows,exchange,board,source):
    output=[]
    fetched=now()
    for row in rows:
        code=code_of(row.get('证券代码',row.get('A股代码',row.get('ts_code','').split('.')[0])))
        name=str(row.get('证券简称',row.get('A股简称',row.get('name','')))).strip()
        listing=row.get('上市日期',row.get('A股上市日期',row.get('list_date')))
        try:
            listed_date=day_of(listing)
        except ValueError:
            listed_date=None
        actual_board=('growth' if row.get('板块')=='创业板' else board)
        output.append(MarketStock(code=code,name=name,exchange=exchange,board=actual_board,
                    st=('ST' in name.upper() or '退' in name) if name else None,
                    listed_date=listed_date,identity_verified=bool(name),source=source,fetched_at=fetched))
    if not output or len({r.code for r in output})!=len(output):
        raise ValueError('上市目录为空或代码冲突')
    return output


def normalize_history(rows,source,validate_turnover=True):
    if source not in ('akshare/eastmoney','akshare/sina','akshare/tencent'):
        raise ValueError('价格来源或单位尚未核实')
    result=[]
    for r in rows:
        em=source=='akshare/eastmoney'
        volume=number(r.get('成交量' if em else 'volume'))
        if em and volume is not None:
            volume*=100
        amount=number(r.get('成交额',r.get('amount')))
        low,high=number(r.get('最低',r.get('low'))),number(r.get('最高',r.get('high')))
        if validate_turnover and volume and amount and low and high and not low*.95<=amount/volume<=high*1.05:
            # Price fields are still useful when a provider's turnover units
            # contradict its daily price range. Do not guess a scale factor.
            volume=amount=None
        result.append(MarketBar(date=day_of(r.get('日期',r.get('date'))),
            open=number(r.get('开盘',r.get('open'))),high=number(r.get('最高',r.get('high'))),
            low=number(r.get('最低',r.get('low'))),close=number(r.get('收盘',r.get('close'))),
            volume=volume,amount=amount))
    result.sort(key=lambda r:r.date)
    if not result or len({r.date for r in result})!=len(result):
        raise ValueError('历史为空或日期重复')
    return result


def normalize_tushare_history(rows,factors,adjust):
    factors={day_of(r['trade_date']):number(r.get('adj_factor')) for r in factors}
    if not rows:
        raise ValueError('日线为空')
    last=max(day_of(r['trade_date']) for r in rows)
    final=factors.get(last)
    output=[]
    for r in rows:
        day=day_of(r['trade_date'])
        if adjust=='qfq' and (not final or not factors.get(day) or final<=0 or factors[day]<=0):
            raise ValueError('复权因子缺失，不能拼接价格')
        scale=factors[day]/final if adjust=='qfq' else 1
        prices={k:number(r.get(k)) for k in ('open','high','low','close')}
        if any(v is None for v in prices.values()):
            raise ValueError('价格缺失')
        output.append(MarketBar(date=day,**{k:v*scale for k,v in prices.items()},
            volume=number(r['vol'])*100 if number(r.get('vol')) is not None else None,
            amount=number(r['amount'])*1000 if number(r.get('amount')) is not None else None))
    return sorted(output,key=lambda r:r.date)


class MarketProvider:
    def __init__(self,provider,settings):
        self.provider=provider
        self.settings=settings.model_copy(deep=True)

    def listing_slice(self,exchange,board):
        if exchange=='SSE':
            name='stock_info_sh_name_code'
            params={'symbol':'科创板' if board=='star' else '主板A股'}
        elif exchange=='SZSE':
            name,params='stock_info_sz_name_code',{'symbol':'A股列表'}
        else:
            name,params='stock_info_bj_name_code',{}
        return normalize_listing(self.provider.call(name,params),exchange,board,'akshare/'+exchange.lower())

    def catalog(self):
        if self.settings.mode.startswith('tushare'):
            rows=self.provider.call('stock_basic',{'list_status':'L','fields':'ts_code,name,exchange,market,list_date'},tushare=True)
            output=[]
            for exchange,board,market in [('SSE','main','主板'),('SSE','star','科创板'),('SZSE','main','主板'),('SZSE','growth','创业板'),('BSE','beijing','北交所')]:
                group=[r for r in rows if r.get('exchange')==exchange and (r.get('market')==market or exchange=='BSE')]
                if group:
                    output.extend(normalize_listing(group,exchange,board,'tushare/stock_basic'))
            if output:
                return output
            raise ValueError('Tushare上市目录缺失')
        rows=self.provider.call('stock_info_a_code_name')
        fetched=now()
        return [MarketStock(code=code_of(r['code']),name=str(r['name']),
                 st=('ST' in str(r['name']).upper() or '退' in str(r['name'])),source='akshare/stock_info_a_code_name',fetched_at=fetched) for r in rows]

    def quotes(self):
        errors=[]
        names=[('stock_zh_a_spot_em','akshare/eastmoney')]
        if self.settings.free_fallback:
            names.extend([('stock_zh_a_spot_tx','akshare/tencent'),('stock_zh_a_spot','akshare/sina')])
        for name,source in names:
            try:
                rows=self.provider.call(name)
                fetched=now()
                output=[]
                for r in rows:
                    q=normalize_spot(r,fetched) if source=='akshare/eastmoney' else normalize_alternate_spot(r,fetched,source)
                    q['change']=number(r.get('zdf')) if source=='akshare/tencent' else number(r.get('涨跌幅',r.get('change_percent',r.get('pct_chg',r.get('percent')))))
                    if q['change'] is not None:
                        q['change']/=100
                    output.append(MarketQuote(**{k:q.get(k) for k in MarketQuote.model_fields}))
                if not output:
                    raise ValueError('行情为空')
                return output
            except (ValueError,RuntimeError,KeyError) as exc:
                errors.append(source+': '+str(exc)[:120])
        raise ValueError('行情不可用：'+'; '.join(errors))

    def sectors(self,kind,classification=None):
        if classification and classification!='eastmoney-'+kind:
            raise ValueError('该分类尚未通过成员/历史契约验证，不能跨来源替代')
        rows=self.provider.call('stock_board_'+kind+'_name_em')
        output=[]
        fetched=now()
        for r in rows:
            code=str(r['板块代码'])
            change=number(r.get('涨跌幅'))
            output.append(SectorRecord(sector_id='em:'+kind+':'+code,code=code,name=str(r['板块名称']),kind=kind,
                classification='eastmoney-'+kind,source='akshare/eastmoney',change=change/100 if change is not None else None,
                amount=number(r.get('成交额')),up=r.get('上涨家数'),down=r.get('下跌家数'),fetched_at=fetched))
        if not output:
            raise ValueError('板块目录为空')
        return output

    def members(self,sector):
        sector=sector.model_dump() if hasattr(sector,'model_dump') else sector
        if sector['source']!='akshare/eastmoney':
            raise ValueError('此来源成分接口尚未核实')
        if sector['kind'] not in ('industry','concept'):
            raise ValueError('板块分类无效')
        try:
            rows=self.provider.call('stock_board_'+sector['kind']+'_cons_em',{'symbol':sector['code']})
            codes=sorted({code_of(r['代码']) for r in rows})
            if not codes: raise ValueError('成分股为空')
            self.members_source='akshare/eastmoney'
            return codes
        except (RuntimeError,ValueError,KeyError,TypeError):
            rows=self.provider.call('stock_board_members_f10_em',{'symbol':sector['code']})
            if not rows or any(str(r.get('BOARD_CODE'))!=str(int(sector['code'][2:])) for r in rows):
                raise ValueError('F10成分股为空或板块不匹配')
            self.members_source='eastmoney/F10'
            return sorted({code_of(r['SECURITY_CODE']) for r in rows})

    def history(self,code,start,end,adjust,source=None):
        source=source or ('tushare' if self.settings.mode.startswith('tushare') else 'akshare/eastmoney')
        a,b=start.replace('-',''),end.replace('-','')
        if source=='tushare':
            ts=code+('.SH' if code.startswith('6') else '.SZ' if code.startswith(('0','3')) else '.BJ')
            rows=self.provider.call('daily',dict(ts_code=ts,start_date=a,end_date=b),tushare=True)
            factors=self.provider.call('adj_factor',dict(ts_code=ts,start_date=a,end_date=b),tushare=True) if adjust=='qfq' else []
            bars=normalize_tushare_history(rows,factors,adjust)
            source='tushare/daily+adj_factor' if adjust=='qfq' else 'tushare/daily'
        else:
            names={'akshare/eastmoney':'stock_zh_a_hist','akshare/sina':'stock_zh_a_daily','akshare/tencent':'stock_zh_a_hist_tx'}
            if source not in names:
                raise ValueError('未授权价格来源')
            symbol=code if source=='akshare/eastmoney' else ('sh' if code.startswith('6') else 'sz' if code.startswith(('0','3')) else 'bj')+code
            params=dict(symbol=symbol,start_date=a,end_date=b,adjust='qfq' if adjust=='qfq' else '')
            if source in ('akshare/eastmoney','akshare/tencent'):
                params['timeout']=25
            rows=self.provider.call(names[source],params)
            bars=normalize_history(rows,source,validate_turnover=adjust=='raw')
        bars=[r for r in bars if start<=r.date<=end]
        if not bars:
            raise ValueError('请求期间无有效历史')
        reported_change=None
        if adjust=='raw' and source in ('akshare/eastmoney','tushare/daily'):
            for row in rows:
                row_day=day_of(row.get('trade_date',row.get('日期',row.get('date'))))
                if row_day==bars[-1].date:
                    value=number(row.get('pct_chg') if source=='tushare/daily' else row.get('涨跌幅'))
                    reported_change=value/100 if value is not None else None
                    break
        limitations=[]
        if any(b.volume is None and b.amount is None for b in bars):
            limitations.append('部分成交量/额缺失或单位未通过价格一致性校验，保留未知')
        return HistoryPage(code=code,items=bars,adjust=adjust,source=source,adjustment_basis=source.split('/')[0]+':'+date.today().isoformat(),
                    requested_start=start,requested_end=end,actual_start=bars[0].date,actual_end=bars[-1].date,state='ready',fetched_at=now(),latest_change=reported_change,limitations=limitations)

    def sector_history(self,sector,start,end):
        sector=sector.model_dump() if hasattr(sector,'model_dump') else sector
        if sector['source']!='akshare/eastmoney':
            raise ValueError('板块历史来源未验证')
        rows=self.provider.call('stock_board_'+sector['kind']+'_hist_em',dict(symbol=sector['code'],period='日k',
                 start_date=start.replace('-',''),end_date=end.replace('-',''),adjust=''))
        # Published board index units differ by endpoint; only its verified OHLC is used.
        prices=[{k:v for k,v in r.items() if k not in ('成交量','成交额','volume','amount')} for r in rows]
        bars=normalize_history(prices,'akshare/eastmoney')
        bars=[r for r in bars if start<=r.date<=end]
        if not bars:
            raise ValueError('板块历史为空')
        return HistoryPage(code=sector['sector_id'],items=bars,adjust='raw',source='akshare/eastmoney',adjustment_basis='published-index',
                    requested_start=start,requested_end=end,actual_start=bars[0].date,actual_end=bars[-1].date,state='ready',fetched_at=now())

    def benchmark_history(self,start,end,source='akshare/eastmoney'):
        if source=='akshare/eastmoney':
            rows=self.provider.call('stock_zh_index_daily_em',dict(symbol='sh000300',start_date=start.replace('-',''),end_date=end.replace('-','')))
        else:
            rows=self.provider.call('stock_zh_a_hist_tx',dict(symbol='sh000300',start_date=start.replace('-',''),end_date=end.replace('-',''),adjust='',timeout=25))
        prices=[{k:v for k,v in r.items() if k not in ('成交量','成交额','volume','amount')} for r in rows]
        bars=normalize_history(prices,source)
        bars=[r for r in bars if start<=r.date<=end]
        if not bars:
            raise ValueError('沪深300历史为空')
        return HistoryPage(code='benchmark:000300',items=bars,adjust='raw',source=source,adjustment_basis='published-index',
                    requested_start=start,requested_end=end,actual_start=bars[0].date,actual_end=bars[-1].date,state='ready',fetched_at=now())
