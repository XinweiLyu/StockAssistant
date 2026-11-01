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


def dividend_capital_case():
    row=dict(new_shares=0,issuance_cash=0,repurchased_shares=0,repurchase_cash=0,cancelled_shares=0,
        treasury_reissued_shares=0,treasury_reissue_cash=0,operating_cashflow=8,capex=0,net_debt_financing=0,earnings=10,financing_cash_costs=0,minority_distributions=0)
    years=[deepcopy(row) for _ in range(5)]
    years[0].update(repurchased_shares=1,repurchase_cash=2)
    years[1]['cancelled_shares']=1
    return dict(method='ddm',scenario='base',shares=10,fixed_capital=False,discount=.1,terminal_growth=0,
        dividends=[8]*5,terminal_dividend=8,capital_feasible=True,
        evidence_ids=['F1'],capital_bridge=dict(basis='model_proposal',sources=['F1'],rationale='有来源的假设路径，非已知未来',
            timing='actions_before_dividend',initial_treasury_shares=1,opening_available_cash=20,minimum_cash=1,
            terminal_capital_stable=True,terminal_earnings=10,terminal_operating_cashflow=8,terminal_capex=0,terminal_financing_cash_costs=0,terminal_minority_distributions=0,years=years))


def test_dividend_valuation_bridges_buybacks_treasury_cancellation_and_cash():
    result=evaluate_method('ddm',dividend_capital_case(),{}, {})
    assert result['state']=='ready'
    assert result['value_per_share']==pytest.approx(10)
    assert result['shares']==9
    assert result['capital_bridge']['years'][0]['dividend_shares']==8
    assert result['capital_bridge']['years'][1]['issued_shares']==9
    assert result['capital_bridge']['years'][1]['treasury_shares']==1
    assert result['capital_bridge']['years'][0]['ending_cash']==18


@pytest.mark.parametrize('change',['cash','cancellation','terminal','references'])
def test_dividend_capital_bridge_blocks_unfunded_or_unreconciled_scenarios(change):
    case=dividend_capital_case();b=case['capital_bridge']
    if change=='cash': b['opening_available_cash']=0;b['years'][0]['operating_cashflow']=0
    elif change=='cancellation': b['years'][0]['cancelled_shares']=3
    elif change=='terminal': b['terminal_capital_stable']=False
    else: b['sources']=[]
    assert evaluate_method('ddm',case,{}, {})['state']=='blocked'


@pytest.mark.parametrize('bridge',[1,[1],{'basis':'model_proposal','sources':[None]},None])
def test_malformed_dynamic_capital_is_a_blocked_case_not_a_server_error(bridge):
    case=dividend_capital_case()|dict(capital_bridge=bridge)
    assert evaluate_method('ddm',case,{}, {})['state']=='blocked'


def test_dividend_funding_deducts_financing_costs_and_minority_cash_claims():
    case=dividend_capital_case()
    case['capital_bridge']['years'][0].update(financing_cash_costs=1,minority_distributions=1)
    result=evaluate_method('ddm',case,{}, {})
    assert result['capital_bridge']['years'][0]['ending_cash']==16


def test_known_treasury_stock_cannot_use_all_issued_shares_as_static_dividend_denominator():
    case=dict(method='ddm',shares=10,fixed_capital=True,discount=.1,terminal_growth=0,dividends=[10]*5,terminal_dividend=10,capital_feasible=True)
    view={'latest':{'treasury_share_cost':{'value':2}}}
    assert evaluate_method('ddm',case,view,{})['state']=='blocked'


def test_cash_constraint_does_not_reject_exact_cent_amounts_due_to_binary_rounding():
    case=dividend_capital_case();b=case['capital_bridge'];case['dividends']=[.3]*5
    b.update(opening_available_cash=0,minimum_cash=.16)
    for y in b['years']:y.update(operating_cashflow=1.01,capex=.33,financing_cash_costs=.22,repurchased_shares=0,repurchase_cash=0,cancelled_shares=0,earnings=1)
    assert evaluate_method('ddm',case,{}, {})['state']=='ready'


def test_terminal_cash_constraint_uses_the_same_exact_cent_ledger():
    case=dividend_capital_case();case['terminal_dividend']=.1
    case['capital_bridge'].update(terminal_operating_cashflow=.3,terminal_capex=.1,terminal_financing_cash_costs=.1,terminal_minority_distributions=0)
    assert evaluate_method('ddm',case,{}, {})['state']=='ready'
