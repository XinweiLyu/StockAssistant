"""Target and analogue regimes must use the same completed benchmark history."""
from datetime import date, timedelta

import pytest

from src.services.a_share_event_cases import event_context
from src.services.a_share_outlook import _environment


@pytest.mark.parametrize('prices,expected', [
    ([float(p) for p in range(100, 165)], 'up'),
    ([float(p) for p in range(164, 99, -1)], 'down'),
    ([100.] * 65, 'range'),
    # MA60 = 100.0167, prior MA60 = 108.3333: a final close above MA
    # does not establish an up regime while the average is falling.
    ([200.] * 5 + [100.] * 59 + [101.], 'range'),
    ([float(p) for p in range(100, 164)], 'unknown'),
])
def test_target_and_historical_event_share_the_same_market_regime(prices, expected):
    calendar = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(len(prices))]
    stock = [dict(date=day, open=10., high=10., low=10., close=10., adjusted_close=10.)
             for day in calendar]
    benchmark = [dict(date=day, close=price, adjusted_close=price) for day, price in zip(calendar, prices)]
    event = event_context(dict(published_at=calendar[-1]),
        dict(stock=stock, benchmark=benchmark), calendar, calendar[-1])
    baseline = _environment(stock, benchmark, [], calendar, calendar[-1])
    assert event['market_state'] == expected
    assert baseline['market_state'] == expected


def test_missing_benchmark_session_keeps_both_market_regimes_unknown():
    calendar = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(66)]
    stock = [dict(date=day, open=10., high=10., low=10., close=10., adjusted_close=10.)
             for day in calendar]
    benchmark = [dict(date=day, close=100.+i, adjusted_close=100.+i)
                 for i, day in enumerate(calendar) if i != 30]
    event = event_context(dict(published_at=calendar[-1]),
        dict(stock=stock, benchmark=benchmark), calendar, calendar[-1])
    baseline = _environment(stock, benchmark, [], calendar, calendar[-1])
    assert event['market_state'] == 'unknown'
    assert baseline['market_state'] == 'unknown'
