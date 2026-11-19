from copy import deepcopy
import pytest
from tests.test_a_share_value_valuation import operating_case
from src.services.a_share_value_valuation import evaluate_value


def inputs(binding_ready=False):
    snapshot=dict(snapshot_id='S',code='hk:00700',market='hk',currency='CNY',name='Tencent',cutoff='2026-11-16T08:00:00+00:00',
        financial_view=dict(current_capital=dict(value=10,period='2026-10-31',available_at='2026-11-16T08:00:00+00:00')),
        economic_model=dict(allowed_methods=['fcff'],model='operating'),facts=[],evidence=[dict(id='F1')],
        binding=dict(eligibility=dict(eligible=True),quote=dict(price=8.,valid=True,basis='raw',trade_date='2026-11-13',currency='HKD',instrument_id='hk:00700'),
            listing=dict(ready=binding_ready,instrument_id='hk:00700',valuation_currency='CNY',quote_currency='HKD',rate=1.1,
                underlying_per_listed=2.,missing=[] if binding_ready else ['汇率或股权比例未核实'],capital=dict(effective_date='2026-10-31',verified_through='2026-11-13'))))
    cases=[operating_case(scenario=k)|dict(currency='CNY',discount_currency='CNY') for k in ('conservative','base','upside')]
    assumptions=dict(snapshot_id='S',code='hk:00700',market='hk',currency='CNY',cases=cases,primary_method='fcff',margin_required=.25)
    return assumptions,snapshot


def test_native_valuation_survives_missing_listing_but_comparisons_block():
    a,s=inputs();r=evaluate_value(a,s)
    assert all(c['state']=='ready' for c in r['valuation_cases'])
    assert r['currency']=='CNY' and r['comparison']['margin'] is None
    assert r['comparison']['upside'] is None and r['comparison']['conditional_price'] is None


def test_valid_fx_and_entitlement_convert_only_per_listing_output():
    a,s=inputs(True);r=evaluate_value(a,s)
    native=r['valuation_cases'][0]['value_per_share']
    assert native==pytest.approx(10.,rel=.001)  # ACT/365.25 dates include leap-day differences.
    assert r['valuation_cases'][0]['quote_value_per_share']==pytest.approx(native*2.2)
    assert r['comparison']['reference_value']==pytest.approx(native*2.2)
    assert r['comparison']['margin']==pytest.approx((native*2.2-8)/(native*2.2))


def test_mismatched_discount_currency_blocks_native_calculation():
    a,s=inputs(True);a['cases'][0]['discount_currency']='USD'
    r=evaluate_value(a,s)
    assert r['valuation_cases'][0]['state']=='blocked'


def test_different_listing_or_unadjusted_quote_cannot_be_compared():
    a,s=inputs(True);s['binding']['quote']['instrument_id']='us:TCEHY'
    assert evaluate_value(a,s)['comparison']['margin'] is None
    s['binding']['quote']['instrument_id']='hk:00700';s['binding']['quote']['basis']='adjusted'
    assert evaluate_value(a,s)['comparison']['margin'] is None


def test_supplied_native_currency_cannot_be_missing_on_offshore_assumptions():
    from src.schemas.a_share_value import ValueAssumptions
    a,s=inputs(True);a.pop('currency')
    with pytest.raises(ValueError):ValueAssumptions.model_validate(a)


def test_blocked_currency_cannot_leak_native_stress_values():
    a,s=inputs(True)
    for c in a['cases']:c['discount_currency']='USD'
    result=evaluate_value(a,s)
    assert not any(row.get('value') is not None for row in result['sensitivities'])


def test_native_reference_uses_explicit_offshore_identity_currency():
    from tests.test_a_share_value_reference import snapshot
    from src.services.a_share_value_reference import build_value_reference
    s=snapshot();s.update(code='us:AAPL',market='us',currency='USD')
    for group in ('ttm','latest'):
        for field in s['financial_view'][group].values():field['unit']='USD'
    result=build_value_reference(s)
    assert result['state']=='ready'
    assert result['assumptions']['market']=='us' and result['report']['currency']=='USD'
    assert result['report']['comparison']['margin'] is None


def test_capital_action_coverage_must_start_at_the_share_fact_effective_date():
    a,s=inputs(True);a['confirmed']=True
    a['risk_review']={k:dict(status='reviewed',sources=['F1']) for k in ('audit','debt','capital','reinvestment','nonoperating_assets')}
    s['financial_view']['current_capital']['period']='2026-07-01'
    s['binding']['listing']['capital']['effective_date']='2026-08-01'
    result=evaluate_value(a,s)
    assert result['valuation_state']!='conditional'
    assert result['comparison']['conditional_price'] is None
