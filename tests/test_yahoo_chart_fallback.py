import io
import json
from datetime import datetime
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
import yfinance
from yfinance.exceptions import YFRateLimitError

from data_provider.market_workspace import WorkspaceProvider
from data_provider.yfinance_fetcher import YfinanceFetcher
from src.services.market_workspace_symbols import resolve_instrument


@pytest.fixture
def yahoo_chart(monkeypatch):
    ny = ZoneInfo("America/New_York")
    sessions = [int(datetime(2026, 11, d, 9, 30, tzinfo=ny).timestamp()) for d in (23, 24, 25)]
    quote_time = int(datetime(2026, 11, 25, 11, 4, tzinfo=ny).timestamp())
    result = {
        "meta": {
            "symbol": "PDD", "currency": "USD", "shortName": "PDD Holdings",
            "exchangeTimezoneName": ny.key, "regularMarketTime": quote_time,
            "regularMarketPrice": 85, "regularMarketDayHigh": 87,
            "regularMarketDayLow": 84, "regularMarketVolume": 3000,
        },
        "timestamp": sessions,
        "indicators": {
            "quote": [{
                "open": [89, 88, 86], "high": [91, 90, 87], "low": [87, 86, 84],
                "close": [90, 87, 85], "volume": [1000, 2000, 3000],
            }],
            "adjclose": [{"adjclose": [81, 87, 85]}],
        },
        "events": {"dividends": {"test": {"date": sessions[1], "amount": 1.25}}},
    }
    calls = []

    def get_chart(request, *, timeout):
        url = urlsplit(request.full_url)
        assert url.path == "/v8/finance/chart/PDD"
        assert parse_qs(url.query)["interval"] == ["1d"]
        calls.append(url)
        return io.BytesIO(json.dumps({"chart": {"result": [result]}}).encode())

    def unavailable(*args, **kwargs):
        raise YFRateLimitError()

    monkeypatch.setattr(yfinance, "download", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr(yfinance, "Ticker", unavailable)
    monkeypatch.setattr("urllib.request.urlopen", get_chart)

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 25, 11, 5, tzinfo=ny).astimezone(tz)

    monkeypatch.setattr("data_provider.yahoo_chart.datetime", FixedClock)
    monkeypatch.setattr(YfinanceFetcher, "_get_us_stock_quote_from_stooq", lambda *_: None)
    return result, calls


def test_home_report_provider_recovers_pdd_quote_and_adjusted_daily_bars(yahoo_chart):
    _, calls = yahoo_chart
    fetcher = YfinanceFetcher()
    quote = fetcher.get_realtime_quote("PDD")
    frame = fetcher.get_daily_data("PDD", "2026-11-23", "2026-11-24")

    assert quote.price == 85
    assert quote.pre_close == 87
    assert quote.currency == "USD"
    assert quote.provider_timestamp == "2026-11-25T16:04:00+00:00"
    assert quote.source.value == "yahoo_chart"
    assert frame["close"].tolist() == [81, 87]
    assert frame["ma5"].tolist() == [81, 84]
    assert len(calls) == 2


def test_assistant_recovers_both_price_bases_and_the_quote_timestamp(yahoo_chart):
    provider = WorkspaceProvider()
    identity = resolve_instrument("us", "PDD")
    prices = provider.history(identity, "2026-11-23", "2026-11-24")
    quote = provider.quote(identity)

    assert [bar["close"] for bar in prices["raw"]] == [90, 87]
    assert [bar["close"] for bar in prices["adjusted"]] == [81, 87]
    assert prices["actions"] == [{"date": "2026-11-24", "dividend": 1.25, "split": 0.0}]
    assert prices["source"] == "yahoo_chart"
    assert quote["source"] == "yahoo_chart"
    assert quote["trade_date"] == "2026-11-25"
    assert quote["source_time"] == "2026-11-25T16:04:00+00:00"


@pytest.mark.parametrize("changes", [{"symbol": "AAPL"}, {"regularMarketTime": None}, {"regularMarketPrice": "Infinity"}])
def test_quote_does_not_publish_mismatched_or_invalid_chart_data(yahoo_chart, changes):
    result, _ = yahoo_chart
    result["meta"].update(changes)

    assert YfinanceFetcher().get_realtime_quote("PDD") is None
