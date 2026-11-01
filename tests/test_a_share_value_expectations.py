import pytest
from src.services.a_share_value_expectations import reverse_value
from tests.test_a_share_value_valuation import dividend_capital_case


def test_reverse_nav_solves_one_parameter_and_discloses_cache_input_and_fixed_claims():
    case=dict(method='nav',scenario='base',shares=10,fixed_capital=True,assets=[dict(id='a',value=100)],liabilities=[],costs=0,complete=True)
    r=reverse_value(case,{},15,dict(valid=False))
    assert r['state']=='solved'
    assert r['parameter']=='asset_scale'
    assert r['solution']==pytest.approx(1.5,rel=1e-5)
    assert r['price_basis']=='unverified_input'
    assert r['held_assumptions'] and r['limitation']


def test_reverse_dividends_rechecks_funding_and_never_promotes_reference_to_market_consensus():
    case=dividend_capital_case()|dict(parameter_origin='reference_sensitivity_v1')
    r=reverse_value(case,{},100,dict(valid=True))
    assert r['state']=='unreachable'
    assert r['reference_origin']=='reference_sensitivity_v1'
    assert r['price_basis']=='reference_input'


@pytest.mark.parametrize('price',[None,0,-1,float('inf'),True])
def test_reverse_invalid_prices_do_not_produce_values(price):
    assert reverse_value({'method':'ddm'}, {}, price, {})['state']=='unavailable'
