"""Bounded Yahoo Chart fallback for US stock daily bars and regular-session quotes."""
import json
from datetime import date, datetime, time, timedelta, timezone
from math import isfinite
from urllib import request
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

import pandas as pd

from .realtime_types import RealtimeSource, UnifiedRealtimeQuote
from .us_index_mapping import is_us_stock_code

_NEW_YORK = ZoneInfo("America/New_York")
_ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart"
_MAX_RESPONSE_BYTES = 4_000_000


def _finite(value):
    try:
        number = float(value)
        return number if isfinite(number) else None
    except (ValueError, TypeError, OverflowError):
        return None


def fetch_yahoo_chart(symbol: str, start: date, end: date) -> dict:
    """Request an inclusive range of dates in the US exchange timezone."""
    if not is_us_stock_code(symbol) or end < start:
        raise ValueError("Invalid US stock or chart date range")
    yahoo_symbol = symbol.upper().replace(".", "-")
    query = urlencode({
        "period1": int(datetime.combine(start, time.min, _NEW_YORK).timestamp()),
        "period2": int(datetime.combine(end + timedelta(days=1), time.min, _NEW_YORK).timestamp()),
        "interval": "1d",
        "events": "div,splits",
    })
    req = request.Request(
        f"{_ENDPOINT}/{quote(yahoo_symbol, safe='')}?{query}",
        headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
    )
    with request.urlopen(req, timeout=8) as response:
        body = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(body) > _MAX_RESPONSE_BYTES:
        raise ValueError("Yahoo Chart response exceeded size limit")
    chart = json.loads(body)["chart"]
    results = chart.get("result") or []
    if chart.get("error") or len(results) != 1:
        raise ValueError("Yahoo Chart returned no matching result")
    result = results[0]
    metadata = result["meta"]
    if metadata.get("symbol", "").upper() != yahoo_symbol or metadata.get("currency") != "USD":
        raise ValueError("Yahoo Chart returned a different symbol or currency")
    return result


def yahoo_chart_daily_frame(result: dict, start: date, end: date) -> pd.DataFrame:
    """Return raw OHLCV and adjusted close in the same shape as yfinance history."""
    timestamps = pd.to_datetime(result.get("timestamp") or [], unit="s", utc=True)
    sessions = timestamps.tz_convert(_NEW_YORK).normalize().tz_localize(None)
    indicators = result["indicators"]
    bars = indicators["quote"][0]
    adjusted = indicators.get("adjclose") or [{}]
    frame = pd.DataFrame(
        {field.title(): bars[field] for field in ("open", "high", "low", "close", "volume")},
        index=sessions.rename("Date"),
    )
    frame["Adj Close"] = adjusted[0].get("adjclose")
    frame = frame.sort_index().loc[str(start):str(end)]
    frame = frame.apply(pd.to_numeric, errors="coerce").replace([float("inf"), -float("inf")], float("nan"))
    prices = ["Open", "High", "Low", "Close"]
    frame = frame.loc[(frame[prices] > 0).all(axis=1)].copy()
    if frame.empty or frame.index.has_duplicates:
        raise ValueError("Yahoo Chart returned no usable daily bars")

    events = result.get("events") or {}
    for name, column in (("dividends", "Dividends"), ("splits", "Stock Splits")):
        frame[column] = 0.0
        for event in (events.get(name) or {}).values():
            day = pd.to_datetime(event["date"], unit="s", utc=True).tz_convert(_NEW_YORK).date()
            key = pd.Timestamp(day)
            if key not in frame.index:
                continue
            value = _finite(event.get("amount") if name == "dividends" else event.get("numerator"))
            denominator = 1 if name == "dividends" else _finite(event.get("denominator"))
            if value is not None and value > 0 and denominator and denominator > 0:
                frame.loc[key, column] = value / denominator
    return frame


def fetch_yahoo_chart_quote(symbol: str) -> UnifiedRealtimeQuote:
    today = datetime.now(_NEW_YORK).date()
    start = today - timedelta(days=10)
    result = fetch_yahoo_chart(symbol, start, today)
    meta = result["meta"]
    price = _finite(meta.get("regularMarketPrice"))
    timestamp = _finite(meta.get("regularMarketTime"))
    if price is None or price <= 0 or timestamp is None or not 0 < timestamp <= datetime.now(timezone.utc).timestamp() + 60:
        raise ValueError("Yahoo Chart returned an invalid regular-session price or timestamp")
    when = datetime.fromtimestamp(timestamp, timezone.utc)
    trade_date = when.astimezone(_NEW_YORK).date()
    daily = yahoo_chart_daily_frame(result, start, trade_date)
    earlier = daily.loc[daily.index < pd.Timestamp(trade_date)]
    previous = float(earlier["Close"].iloc[-1]) if not earlier.empty else None
    change = price - previous if previous else None
    quote_session = daily.loc[daily.index == pd.Timestamp(trade_date)]
    opening = float(quote_session["Open"].iloc[0]) if not quote_session.empty else None
    volume = _finite(meta.get("regularMarketVolume"))
    return UnifiedRealtimeQuote(
        code=symbol.upper(),
        name=str(meta.get("shortName") or meta.get("longName") or ""),
        source=RealtimeSource.YAHOO_CHART,
        provider_timestamp=when.isoformat(),
        fallback_from="yfinance",
        market="us",
        currency="USD",
        data_quality="partial",
        price=price,
        pre_close=previous,
        change_amount=round(change, 4) if change is not None else None,
        change_pct=round(change / previous * 100, 2) if change is not None else None,
        open_price=opening,
        high=_finite(meta.get("regularMarketDayHigh")),
        low=_finite(meta.get("regularMarketDayLow")),
        volume=int(volume) if volume is not None and volume >= 0 else None,
    )
