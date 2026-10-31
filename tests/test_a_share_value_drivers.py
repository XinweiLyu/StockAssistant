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
