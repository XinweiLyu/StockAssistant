from src.services.a_share_value_drivers import apply_driver_changes
from tests.test_a_share_value_valuation import operating_case


def test_event_changes_have_auditable_counterfactual_and_no_double_application():
    event = dict(event_id='E1', family_id='family1', published_at='2026-10-20T00:00:00+08:00')
    s = dict(cutoff='2026-10-30T00:00:00+08:00', events=[event], facts=[], evidence=[])
    change = dict(event_id='E1', field='ebit_margin', unit='ratio', old=.2, new=.18,
                  years=[1, 2], half_life_years=1, already_in_baseline=False, rationale='已披露成本影响', sources=['E1'])
    a = dict(cases=[operating_case()], driver_changes=[change, change])
    result = apply_driver_changes(s, a)
    assert result['cases'][0]['operating']['years'][0]['ebit_margin'] == .18
    assert result['cases'][0]['operating']['years'][1]['ebit_margin'] == .19
    assert len(result['effects']) == 1
    assert result['rejected']
    assert a['cases'][0]['operating']['years'][0]['ebit_margin'] == .2


def test_future_and_already_included_events_cannot_change_value():
    s = dict(cutoff='2026-10-30', events=[dict(event_id='E1', published_at='2026-11-30')], facts=[], evidence=[])
    a = dict(cases=[operating_case()], driver_changes=[dict(event_id='E1', field='growth', new=.5, unit='ratio')])
    result = apply_driver_changes(s, a)
    assert not result['effects']
    assert result['cases'] == a['cases']


def test_structural_event_changes_stable_period_and_growth_consistently():
    s=dict(cutoff='2026-10-30',events=[dict(id='E',published_at='2026-10-20')],facts=[],evidence=[])
    c=dict(event_id='E',field='growth',unit='ratio',old=0,new=.03,years=[1,2,3,4,5],
        temporal_type='structural',include_terminal=True,terminal_old=0,already_in_baseline=False,rationale='长期产能变化',sources=['E'])
    r=apply_driver_changes(s,dict(cases=[operating_case()],driver_changes=[c]))
    assert not r['rejected']
    assert r['cases'][0]['operating']['terminal']['growth']==.03
    assert r['cases'][0]['terminal_growth']==.03
    c['include_terminal']=False
    assert apply_driver_changes(s,dict(cases=[operating_case()],driver_changes=[c]))['rejected']


def test_ddm_capital_rim_and_nav_have_explicit_event_routes():
    from tests.test_a_share_value_valuation import dividend_capital_case
    from src.services.a_share_value_valuation import evaluate_method
    s=dict(cutoff='2026-10-30',events=[dict(id='E',published_at='2026-10-20')],facts=[],evidence=[])
    common=dict(event_id='E',temporal_type='one_off',years=[1],already_in_baseline=False,rationale='原文变化',sources=['E'])
    ddm=dividend_capital_case();ddm['capital_bridge']['opening_available_cash']=0
    r=apply_driver_changes(s,dict(cases=[ddm],driver_changes=[common|dict(field='capital.operating_cashflow',unit='CNY',old=8,new=0)]))
    assert r['cases'][0]['capital_bridge']['years'][0]['operating_cashflow']==0
    assert evaluate_method('ddm',r['cases'][0],{}, {})['state']=='blocked'
    rim=dict(method='rim',scenario='base',years=[dict(roe=.1,dividend=10,oci=0) for _ in range(5)])
    r=apply_driver_changes(s,dict(cases=[rim],driver_changes=[common|dict(field='roe',unit='ratio',old=.1,new=.08)]))
    assert r['cases'][0]['years'][0]['roe']==.08
    nav=dict(method='nav',scenario='base',assets=[dict(id='factory',value=100)],liabilities=[])
    r=apply_driver_changes(s,dict(cases=[nav],driver_changes=[common|dict(field='asset',item_id='factory',unit='CNY',old=100,new=80)]))
    assert r['cases'][0]['assets'][0]['value']==80
    assert len(r['effects'])==1
