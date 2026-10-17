from copy import deepcopy
from datetime import date,timedelta
import pytest
from src.services.a_share_integrated_validation import evaluate_integrated_snapshots, compare_forecast_snapshots


def data():
    calendar=[(date(2026,1,1)+timedelta(days=i)).isoformat() for i in range(80)]
    bars=[dict(date=d,open=20.+i,close=20.+i,high=21.+i,low=19.+i) for i,d in enumerate(calendar)]
    saved=dict(code='000807',data_hash='issued',generated_at='2026-01-01T16:00:00+08:00',anchor_date='2026-01-01',reference_price=20.,
        history_binding=dict(source='fixture',raw_anchor=20.),status='complete',
        forecasts=[dict(horizon_sessions=5,scenario='base',low=24.,high=26.)],
        numeric_references=[dict(id='B5',horizon_sessions=5,low=20.,median=23.,high=26.)])
    return calendar,bars,[dict(payload=saved)]


def test_unmatured_predictions_do_not_become_accuracy_or_portfolio_profit():
    calendar,bars,records=data()
    result=evaluate_integrated_snapshots(records,bars,calendar,'2026-01-01',source='fixture')
    assert result['horizons']['5']['matured']==0
    assert result['horizons']['5']['mean_absolute_error'] is None
    assert result['portfolio_return'] is None


def test_real_forward_issuance_is_scored_with_paired_baselines():
    calendar,bars,records=data()
    result=evaluate_integrated_snapshots(records,bars,calendar,'2026-02-01',source='fixture')
    row=result['horizons']['5']
    assert row['matured']==1 and row['mean_absolute_error']==0.
    assert row['observed_scenario_coverage']==1.
    paired=compare_forecast_snapshots(records,bars,calendar,'2026-02-01',source='fixture')
    assert paired['horizons']['5']['samples']==1
    assert paired['horizons']['5']['unchanged_price_mae']==5.
    assert paired['horizons']['5']['price_model_mae']==2.
    assert paired['horizons']['5']['integrated_mae']==0.
    assert paired['financial_only']['status']=='unavailable'


@pytest.mark.parametrize('change', ['late_issue','future_issue','wrong_source','changed_anchor','missing_session'])
def test_reconstructed_or_unaligned_history_is_not_forward_performance(change):
    calendar,bars,records=data()
    if change=='late_issue': records[0]['payload']['generated_at']='2026-01-10T16:00:00+08:00'
    if change=='future_issue': records[0]['payload']['generated_at']='2027-01-01T16:00:00+08:00'
    if change=='wrong_source': records[0]['payload']['history_binding']['source']='other'
    if change=='changed_anchor': bars[0]['close']=21.
    if change=='missing_session': bars.pop(3)
    result=evaluate_integrated_snapshots(records,bars,calendar,'2026-02-01',source='fixture')
    assert result['horizons']['5']['matured']==0


def test_repeated_same_anchor_uses_first_eligible_issuance_not_best_later_prediction():
    calendar,bars,records=data()
    newer=deepcopy(records[0]);newer['payload']['generated_at']='2026-01-02T10:00:00+08:00';newer['payload']['forecasts'][0].update(low=30.,high=40.)
    result=evaluate_integrated_snapshots([newer]+records,bars,calendar,'2026-02-01',source='fixture')
    assert result['horizons']['5']['matured']==1
    assert result['horizons']['5']['mean_absolute_error']==0.


def test_missing_original_price_prediction_does_not_create_a_fake_ablation():
    calendar,bars,records=data();records[0]['payload']['numeric_references']=[]
    result=compare_forecast_snapshots(records,bars,calendar,'2026-02-01',source='fixture')
    assert result['horizons']['5']['samples']==0
    assert result['horizons']['5']['price_model_mae'] is None
