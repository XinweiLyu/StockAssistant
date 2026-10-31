import pytest
from src.services.a_share_value_holding import cashflow_schedule, evaluate_holding, add_months
from src.services.a_share_value_valuation import evaluate_method
from tests.test_a_share_value_valuation import operating_case


def test_cashflow_schedule_reconciles_today_and_holding_value():
    case = dict(method='ddm', discount=.1, terminal_growth=0, shares=10, fixed_capital=True,
                dividends=[10]*5, terminal_dividend=10, capital_feasible=True, start_date='2026-10-30')
    valuation = evaluate_method('ddm', case, {}, {})
    held = evaluate_holding(case | dict(price=8, realization_factor=.75), valuation, '2026-10-30', 12)
    t = held['year_fraction']
    pv_dividends = sum(v['amount']/(1+.1)**v['time'] for v in cashflow_schedule(case, '2026-10-30') if v['date'] <= held['end_date'])/10
    assert valuation['value_per_share'] == pytest.approx(pv_dividends+held['intrinsic_value']/(1.1)**t)
    assert held['price'] == pytest.approx(held['intrinsic_value']*.75)
    assert held['dividends'] == 1
    assert held['net_return'] is None


def test_natural_month_end_and_fcf_retention_gate():
    assert add_months('2026-10-30', 6) == '2027-04-30'
    assert add_months('2023-08-31', 6) == '2024-02-29'
    result = evaluate_holding(operating_case(), {}, '2026-10-30', 20)
    assert result['state'] == 'blocked'
    result = evaluate_holding(operating_case(), evaluate_method('fcff', operating_case(), {}, {}), '2026-10-30', 24)
    assert result['state'] == 'insufficient'
    assert '留存' in result['reason']


def test_missing_realization_factor_never_implies_convergence():
    case = dict(method='ddm', dividends=[10]*5, discount=.1, terminal_growth=0, shares=10,
                fixed_capital=True, capital_feasible=True, terminal_dividend=10, price=8)
    result = evaluate_holding(case, evaluate_method('ddm', case, {}, {}), '2026-10-30', 6)
    assert result['state'] == 'insufficient'
