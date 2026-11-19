"""Explicit currency and listing-entitlement bridge; absent evidence blocks output."""
from datetime import date,datetime,timedelta,timezone
from math import isfinite


def listing_binding(identity,anchor,currency,fx,capital):
    missing=[];quote=identity.get('currency');rate=1.
    if not quote:missing.append('报价币种未核实')
    if currency!=quote:
        try:
            age=(date.fromisoformat(anchor)-date.fromisoformat(fx['date'])).days
            if not 0<=age<=7 or fx['from_currency']!=currency or fx['to_currency']!=quote or not fx.get('source'):raise ValueError()
            rate=float(fx['rate'])
            if not isfinite(rate) or rate<=0:raise ValueError()
        except (TypeError,KeyError,ValueError):missing.append('缺少不晚于锚点且7日内、方向一致的有来源汇率')
    try:
        ratio=float(capital['underlying_per_listed'])
        if not capital.get('confirmed') or not capital.get('sources') or not capital['effective_date']<=anchor<=capital['verified_through'] or ratio<=0 or not isfinite(ratio):raise ValueError()
    except (KeyError,ValueError,TypeError):ratio=None;missing.append('上市单位/ADR股权比例及资本行动覆盖未核实')
    return dict(ready=not missing,instrument_id=identity['instrument_id'],market=identity['market'],
        valuation_currency=currency,quote_currency=quote,fx=fx,capital=capital,rate=rate if not missing else None,
        underlying_per_listed=ratio,missing=missing)


def fetch_fx(from_currency,to_currency,as_of):
    if from_currency==to_currency:return dict(from_currency=from_currency,to_currency=to_currency,rate=1.,date=as_of,source='same_currency',pair=None)
    import yfinance as yf
    for a,b,inverse in [(from_currency,to_currency,False),(to_currency,from_currency,True)]:
        pair=a+b+'=X'
        try:
            frame=yf.Ticker(pair).history(start=(date.fromisoformat(as_of)-timedelta(days=7)).isoformat(),
                end=(date.fromisoformat(as_of)+timedelta(days=1)).isoformat(),auto_adjust=False,timeout=12)
        except Exception:
            continue
        if frame is None or frame.empty or 'Close' not in frame:continue
        values=frame['Close'].dropna()
        if values.empty:continue
        value=float(values.iloc[-1])
        if not isfinite(value) or value<=0:continue
        return dict(from_currency=from_currency,to_currency=to_currency,rate=1/value if inverse else value,
            date=values.index[-1].date().isoformat(),source='yfinance/FX',pair=pair,inverted=inverse,observed_at=datetime.now(timezone.utc).isoformat())
    return None


def validate_listing_capital(listing,capital,anchor,cutoff):
    """Require continuous coverage from the actual denominator's effective date."""
    from copy import deepcopy
    from src.schemas.a_share_integrated import stamp
    result=deepcopy(listing or {})
    coverage=result.get('capital') or {};capital=capital or {}
    try:
        valid=(date.fromisoformat(coverage['effective_date'])<=date.fromisoformat(capital['period'])
            <=date.fromisoformat(anchor)<=date.fromisoformat(coverage['verified_through'])
            and bool(stamp(capital['available_at'])) and stamp(capital['available_at'])<=stamp(cutoff))
    except (KeyError,TypeError,ValueError):valid=False
    if not valid:
        result['ready']=False
        result['missing']=list(dict.fromkeys(result.get('missing',[])+['总股数生效日至报价锚点的资本行动未连续覆盖，请补充同期股数及原文']))
    return result
