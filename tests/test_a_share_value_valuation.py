from copy import deepcopy
import pytest
from src.services.a_share_value_valuation import project_operating_case, evaluate_method, compare_price, evaluate_value


def operating_case(method='fcff', scenario='base'):
    year = dict(growth=0, ebit_margin=.2, da_ratio=.05, capex_ratio=.1, nwc_ratio=.1,
                tax=.25, after_tax_interest=0, net_borrowing=0, minority_cashflow=0)
    return dict(method=method, scenario=scenario, discount=.1, terminal_growth=0, shares=10,
        fixed_capital=True, operating=dict(revenue0=100, nwc0=10, years=[deepcopy(year) for _ in range(5)], terminal=deepcopy(year)),
        nonoperating=dict(treatment='separate', value=0), debt=0, senior_claims=0, minority_value=0,
        evidence_ids=['F1'], rationale='测试用已披露经营与投资桥接')


def test_operating_bridge_and_fcfe_hand_calculation():
    case = operating_case('fcfe')
    assert project_operating_case(case, {})['flows'] == [10]*5
    result = evaluate_method('fcfe', case, {}, {})
    assert result['value_per_share'] == pytest.approx(10)
    assert result['operating_equity'] == pytest.approx(100)


def test_fcff_claims_bridge_and_missing_is_not_zero():
    case = operating_case() | dict(nonoperating=dict(treatment='separate', value=20), debt=30, senior_claims=5, minority_value=5)
    assert evaluate_method('fcff', case, {}, {})['value_per_share'] == pytest.approx(8)
    del case['debt']
    assert evaluate_method('fcff', case, {}, {})['state'] == 'blocked'


def test_terminal_year_is_recomputed():
    case = operating_case()
    case['operating']['terminal']['ebit_margin'] = 1/3
    assert evaluate_method('fcff', case, {}, {})['terminal_value'] == pytest.approx(200)


@pytest.mark.parametrize('changes', [dict(discount=0), dict(terminal_growth=.095), dict(shares=0), dict(fixed_capital=False), dict(discount=True)])
def test_invalid_inputs_are_blocked(changes):
    assert evaluate_method('fcff', operating_case() | changes, {}, {})['state'] == 'blocked'


def test_sector_constraints_and_missing_investment():
    assert evaluate_method('fcff', operating_case(), {}, {'allowed_methods': ['rim']})['state'] == 'blocked'
    case = operating_case()
    del case['operating']['years'][0]['capex_ratio']
    assert evaluate_method('fcff', case, {}, {})['state'] == 'blocked'


def test_rim_ddm_and_nav_have_independent_hand_calculations():
    common = dict(discount=.1, terminal_growth=0, shares=10, fixed_capital=True)
    rim = common | dict(book_equity=100, years=[dict(roe=.1, dividend=10, oci=0) for _ in range(5)], omega=0)
    assert evaluate_method('rim', rim, {}, {})['value_total'] == pytest.approx(100)
    ddm = common | dict(dividends=[10]*5, terminal_dividend=10, capital_feasible=True)
    assert evaluate_method('ddm', ddm, {}, {})['value_per_share'] == pytest.approx(10)
    nav = common | dict(assets=[dict(id='asset1', value=150)], liabilities=[dict(id='debt1', value=40)], costs=10, complete=True)
    assert evaluate_method('nav', nav, {}, {})['value_per_share'] == 10
    nav['assets'].append(dict(id='asset1', value=100))
    assert evaluate_method('nav', nav, {}, {})['state'] == 'blocked'


def test_margin_and_upside_use_different_denominators():
    quote = dict(price=60, valid=True)
    result = compare_price(80, quote, .3, {'eligible': True})
    assert result['margin'] == .25
    assert result['upside'] == pytest.approx(1/3)
    assert result['conditional_price'] == 56
    assert compare_price(80, quote, .3, {'eligible': False})['conditional_price'] is None
    assert compare_price(0, quote, .3, {'eligible': True})['margin'] is None


def test_three_scenarios_and_disagreement_do_not_get_averaged():
    cases = [operating_case(scenario=s) for s in ['conservative', 'base', 'upside']]
    cross = operating_case('fcfe')
    cross['nonoperating']['value'] = 50
    assumptions = dict(code='000807', snapshot_id='s1', confirmed=True, revision=1, primary_method='fcff', cases=cases+[cross])
    snapshot = dict(code='000807', name='测试', snapshot_id='s1', cutoff='2026-10-30T10:00:00+08:00', binding={})
    result = evaluate_value(assumptions, snapshot)
    assert result['valuation_state'] == 'disputed'
    assert result['comparison']['conditional_price'] is None


def test_missing_quote_date_does_not_break_a_current_capital_valuation():
    cases=[operating_case(scenario=s) for s in ('conservative','base','upside')]
    a=dict(code='000807',snapshot_id='s',primary_method='fcff',cases=cases)
    s=dict(code='000807',name='样本',snapshot_id='s',cutoff='2026-10-30T10:00:00+08:00',
           binding={'quote':{'trade_date':None}},financial_view={'current_capital':{'value':10,'period':'2026-10-30','available_at':'2026-10-30T10:00:00+08:00'}})
    assert evaluate_value(a,s)['comparison']['conditional_price'] is None
