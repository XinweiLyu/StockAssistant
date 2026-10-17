from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from src.services.a_share_rules import (
    indicators, percentile, rank_universe, buy_plan, check_trigger,
    holding_risk, forward_observation, session_slot,
)

NOW = datetime(2026, 10, 9, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))


def bars(count=160):
    return [dict(date=f'2025-{1 + i // 28:02d}-{1 + i % 28:02d}', close=10 + i * .02,
                 high=10.3 + i * .02, low=9.7 + i * .02,
                 adjusted_close=10 + i * .02, amount=100_000_000) for i in range(count)]


def candidate():
    return dict(code='600001', sector='制造', entry=20., atr=.5, high=20.,
                as_of='2026-10-08', valid_date='2026-10-09', market_ok=True)


def account():
    return dict(nav=100000., cash=100000., total_value=0., stock_value=0., sector_value=0., complete=True)


def quote(**overrides):
    result = dict(price=20.1, source_time=NOW.isoformat(), trade_date='2026-10-09',
                  suspended=False, limit_up=22., limit_down=18., amount=1e8)
    return result | overrides


def test_future_or_incomplete_daily_never_changes_indicators():
    data = bars()
    base = indicators(data, '2025-06-20')
    assert indicators(data + [dict(data[-1], date='2026-10-09', close=999)], '2025-06-20') == base
    assert base['r20'] == pytest.approx(13.18 / 12.78 - 1)
    assert base['atr'] == pytest.approx(.6)


def test_bad_ohlc_missing_adjustment_and_duplicate_dates_rejected():
    data = bars()
    with pytest.raises(ValueError):
        indicators(data + [data[-1]], data[-1]['date'])
    with pytest.raises(ValueError):
        indicators(data[:-1] + [dict(data[-1], high=1)], data[-1]['date'])
    with pytest.raises(ValueError):
        indicators(data[:-1] + [dict(data[-1], adjusted_close=None)], data[-1]['date'])


def test_ties_have_average_rank_and_single_sample_is_neutral():
    assert percentile([1, 1, 3]) == [.25, .25, 1.]
    assert percentile([7]) == [.5]


def test_real_small_pool_does_not_force_recommendations():
    stocks = [dict(code='600001', name='样本', sector='制造', listed_sessions=200,
                   bars=bars(), st=False, suspended=False)]
    assert rank_universe(stocks, [], bars(), bars()[-1]['date'], demo=False)['candidates'] == []


def test_risk_cash_and_lot_cap_includes_costs():
    plan = buy_plan(candidate(), account(), {})
    assert plan['quantity'] == 400  # 10% NAV cap / ¥20 then lot; fees prevent 500.
    assert plan['stop'] == 19.
    assert buy_plan(candidate(), account() | {'sector_value': 20000}, {})['quantity'] == 0
    assert buy_plan(candidate(), account() | {'complete': False}, {})['quantity'] is None


@pytest.mark.parametrize('changes', [{'source_time': None}, {'source_time': '2026-10-09T09:40:00+08:00'},
                                      {'suspended': None}, {'limit_up': None}, {'price': 21.}])
def test_unknown_stale_untradeable_and_chased_price_never_trigger(changes):
    assert check_trigger(candidate(), quote(**changes), account(), NOW, ['2026-10-09'], {})['status'] != 'triggered'


def test_confirmed_trigger_still_is_not_a_fill_and_risk_event_vetoes():
    result = check_trigger(candidate(), quote(), account(), NOW, ['2026-10-09'], {})
    assert result['status'] == 'triggered'
    assert 'filled' not in result
    assert check_trigger(candidate() | {'major_risk': True}, quote(), account(), NOW, ['2026-10-09'], {})['status'] == 'blocked'


def test_stop_loss_does_not_assume_t_plus_one_sellability():
    result = holding_risk(dict(code='600001', quantity=1000, stop=20, sellable=None), quote(price=19), NOW)
    assert result['action'] == '退出条件触发'
    assert result['sellable'] is None
    assert result['executable'] is False


def test_market_calendar_and_lunch_slots():
    assert session_slot(NOW, []) is None
    assert session_slot(NOW.replace(hour=12), ['2026-10-09']) is None
    assert session_slot(NOW.replace(minute=2), ['2026-10-09']) == '2026-10-09T10:00'


def test_forward_missing_endpoint_never_shifts_date_or_claims_profit():
    calendar = ['2026-10-08', '2026-10-09', '2026-10-12', '2026-10-13']
    data = [dict(date=d, adjusted_close=p) for d,p in [('2026-10-09', 10), ('2026-10-13', 20)]]
    out = forward_observation('2026-10-08', data, calendar, [1, 2])
    assert out[0]['return'] is None
    assert out[1]['return'] == 1.
    assert out[1]['end_date'] == '2026-10-13'


def test_benchmark_can_gate_market_without_irrelevant_turnover_field():
    benchmark=[dict(r,amount=None) for r in bars()]
    assert rank_universe([],[],benchmark,bars()[-1]['date'],demo=True)['market_ok'] is True


def test_sellability_larger_than_position_is_not_executable():
    result=holding_risk(dict(code='600001',quantity=100,sellable=1000,stop=20),quote(price=19),NOW)
    assert not result['executable']


def test_bad_quote_range_and_after_close_never_confirm_action():
    assert check_trigger(candidate(),quote(limit_down=21),account(),NOW,['2026-10-09'],{})['status']!='triggered'
    assert check_trigger(candidate(),quote(),account(),NOW.replace(hour=15,minute=1),['2026-10-09'],{})['status']=='expired'


def test_last_snapshot_slot_is_collected_even_a_few_seconds_after_close():
    assert session_slot(NOW.replace(hour=15,minute=0,second=20),['2026-10-09'])=='2026-10-09T15:00'


def test_holding_never_marked_executable_after_close():
    result=holding_risk(dict(code='600001',quantity=100,sellable=100,stop=20),
                        quote(price=19,source_time=NOW.replace(hour=15).isoformat()),
                        NOW.replace(hour=15,minute=1),['2026-10-09'])
    assert not result['executable']


def test_benchmark_and_sector_calendar_gaps_disable_their_rules():
    data=bars()
    calendar=[r['date'] for r in data]
    incomplete=data[:-2]+data[-1:]
    sectors=[dict(code=str(i),classification='same',bars=incomplete) for i in range(12)]
    result=rank_universe([],sectors,incomplete,data[-1]['date'],calendar=calendar)
    assert result['market_ok'] is None
    assert not result['sector_ready'] and not result['sectors']
