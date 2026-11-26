"""Offshore market adapters. Raw and adjusted series share one acquisition."""
from datetime import date,datetime,timedelta,timezone
from math import isfinite
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import hashlib


def finite(value):
    try:
        value=float(value)
        return value if isfinite(value) else None
    except (TypeError,ValueError):return None


def yahoo_price_pair(frame,fetched_at):
    raw,adjusted,actions=[],[],[]
    for index,row in frame.iterrows():
        prices={key:finite(row.get(field)) for key,field in [('open','Open'),('high','High'),('low','Low'),('close','Close')]}
        if any(v is None or v<=0 for v in prices.values()):continue
        day=index.date().isoformat()
        volume=finite(row.get('Volume'))
        bar=dict(date=day,**prices,volume=volume if volume is not None and volume>=0 else None,amount=None)
        raw.append(bar)
        adj=finite(row.get('Adj Close'))
        if adj is not None and adj>0:
            factor=adj/prices['close']
            adjusted.append(bar|{k:v*factor for k,v in prices.items()})
        dividend,split=finite(row.get('Dividends')),finite(row.get('Stock Splits'))
        if dividend or split:actions.append(dict(date=day,dividend=dividend,split=split))
    if not raw:raise ValueError('未取得有效原始日线')
    basis=hashlib.sha256(json.dumps([raw,adjusted,actions],sort_keys=True,allow_nan=False).encode()).hexdigest()
    return dict(raw=raw,adjusted=adjusted,actions=actions,source='yfinance',basis='yahoo-total-return:'+basis,fetched_at=fetched_at)


def yahoo_quote(identity,info):
    price=finite(info.get('regularMarketPrice'))
    if price is None or price<=0:raise ValueError('未取得有效常规时段价格')
    timestamp=finite(info.get('regularMarketTime'))
    when=datetime.fromtimestamp(timestamp,timezone.utc) if timestamp is not None else None
    previous=finite(info.get('regularMarketPreviousClose'))
    return dict(price=price,change=price/previous-1 if previous and previous>0 else None,source='yfinance',
        source_time=when.isoformat() if when else None,trade_date=when.astimezone(ZoneInfo(identity.timezone)).date().isoformat() if when else None,
        currency=info.get('currency'),open=finite(info.get('regularMarketOpen')),high=finite(info.get('regularMarketDayHigh')),
        low=finite(info.get('regularMarketDayLow')),volume=finite(info.get('regularMarketVolume')),delay_state='unknown')


class WorkspaceProvider:
    def catalog(self,market):
        from src.data.stock_index_loader import get_stock_index_candidate_paths
        for path in get_stock_index_candidate_paths():
            if not path.is_file():continue
            try:rows=json.loads(path.read_text())
            except (ValueError,OSError):continue
            output=[]
            for row in rows:
                if len(row)<8 or row[6]!=market.upper() or row[7]!='stock':continue
                output.append(dict(symbol=row[1],name=row[2],aliases=row[5] if len(row)>5 else []))
            if output:return output
        return []

    def identity(self,identity):
        import yfinance as yf
        info=yf.Ticker(identity.source_symbol).get_info()
        if not info or info.get('quoteType') not in ('EQUITY','ETF','MUTUALFUND','INDEX'):
            raise ValueError('供应商未返回可核实证券身份')
        currency=info.get('currency')
        return dict(name=info.get('longName') or info.get('shortName') or identity.symbol,
            exchange=info.get('exchange') or 'unknown',asset_type='stock' if info.get('quoteType')=='EQUITY' else info['quoteType'].lower(),
            currency=currency,financial_currency=info.get('financialCurrency'),industry=info.get('industry'),
            sector=info.get('sector'),verified=bool(currency and info.get('symbol','').upper()==identity.source_symbol.upper()),
            info=info)

    def history(self,identity,start,end):
        import yfinance as yf
        try:
            frame=yf.Ticker(identity.source_symbol).history(start=start,end=(date.fromisoformat(end)+timedelta(days=1)).isoformat(),
                interval='1d',auto_adjust=False,actions=True,timeout=15,raise_errors=True)
            return yahoo_price_pair(frame,datetime.now(timezone.utc).isoformat())
        except Exception:
            if identity.market != 'us':
                raise
            from data_provider.yahoo_chart import fetch_yahoo_chart, yahoo_chart_daily_frame
            first, last = date.fromisoformat(start), date.fromisoformat(end)
            chart = fetch_yahoo_chart(identity.source_symbol, first, last)
            frame = yahoo_chart_daily_frame(chart, first, last)
            return yahoo_price_pair(frame, datetime.now(timezone.utc).isoformat()) | {'source': 'yahoo_chart'}

    def quote(self,identity):
        import yfinance as yf
        try:return yahoo_quote(identity,yf.Ticker(identity.source_symbol).get_info())
        except Exception:pass
        from data_provider.yfinance_fetcher import YfinanceFetcher
        quote=YfinanceFetcher().get_realtime_quote(identity.source_symbol)
        if not quote or not finite(getattr(quote,'price',None)) or quote.price<=0:raise ValueError('行情源未返回有效报价')
        # Provider source timestamp must be real; retrieval time is not a market timestamp.
        value=quote.to_dict() if hasattr(quote,'to_dict') else vars(quote)
        when=value.get('provider_timestamp') or value.get('source_time')
        if hasattr(when,'isoformat'):when=when.isoformat()
        trade_date = value.get('trade_date')
        if isinstance(when, str) and when and not trade_date:
            trade_date = datetime.fromisoformat(when).astimezone(ZoneInfo(identity.timezone)).date().isoformat()
        return dict(price=quote.price,change=(finite(getattr(quote,'change_pct',None))/100 if finite(getattr(quote,'change_pct',None)) is not None else None),
            source=value.get('source','yfinance'),source_time=when if isinstance(when,str) else None,
            trade_date=trade_date,currency=getattr(quote,'currency',None),
            open=getattr(quote,'open_price',None),high=getattr(quote,'high',None),low=getattr(quote,'low',None),volume=getattr(quote,'volume',None),
            delay_state='unknown')
