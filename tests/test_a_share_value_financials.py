from data_provider.a_share_value_facts import normalize_value_statements
from src.services.a_share_value_financials import build_financial_view

NOW = '2026-10-30T12:00:00+08:00'


def income(period, revenue):
    return normalize_value_statements('000807', [dict(ts_code='000807.SZ', report_type='1',
        end_date=period, ann_date='20261020', total_revenue=revenue)], 'tushare/income', NOW)


def test_ttm_requires_exact_cumulative_comparables():
    facts = income('20251231', 120)+income('20260930', 100)+income('20250930', 80)
    result = build_financial_view(facts, NOW)
    assert result['ttm']['revenue']['value'] == 140
    assert len(result['ttm']['revenue']['fact_ids']) == 3
    assert 'revenue' not in build_financial_view(facts[:2], NOW)['ttm']


def test_future_observation_and_conflicting_values_are_not_selected():
    facts = income('20260930', 100)
    assert not build_financial_view(facts, '2026-10-01T12:00:00+08:00')['latest']
    result = build_financial_view(facts+income('20260930', 200), NOW)
    assert 'revenue' not in result['latest']
    assert result['conflicts']


def test_instant_balance_is_not_ttm_or_added():
    facts = normalize_value_statements('000807', [dict(end_date='20260930', ann_date='20261020',
        report_type='1', total_assets=70)], 'tushare/balancesheet', NOW)
    view = build_financial_view(facts, NOW)
    assert view['latest']['assets']['value'] == 70
    assert 'assets' not in view['ttm']
    assert view['quality']['cash_profit_ratio'] is None


def test_current_capital_does_not_hide_latest_financial_period():
    from data_provider.a_share_value_facts import normalize_current_capital
    capital = normalize_current_capital('000807', [dict(item='股票代码',value='000807'),dict(item='总股本',value=20)], NOW)
    result = build_financial_view(income('20251231',120)+capital, NOW)
    assert result['latest_period'] == '2025-12-31'
    assert result['latest']['revenue']['value'] == 120
    assert result['current_capital']['value'] == 20


def test_conflicting_current_capital_cannot_silently_override_verified_source():
    from data_provider.a_share_value_facts import normalize_current_capital
    one=normalize_current_capital('000807',[dict(item='股票代码',value='000807'),dict(item='总股本',value=20)],NOW)
    two=normalize_current_capital('000807',[dict(item='股票代码',value='000807'),dict(item='总股本',value=30)],NOW)
    view=build_financial_view(one+two,NOW)
    assert view['current_capital'] is None
    assert any(x['metric']=='current_shares' for x in view['conflicts'])
