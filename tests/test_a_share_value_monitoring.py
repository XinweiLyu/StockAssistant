from src.services.a_share_value_monitoring import build_monitoring
from tests.test_a_share_value_strategy import snapshot
from tests.test_a_share_value_economics import fv
import pytest


def history():
    f=fv(90,'2025-09-30')
    old=dict(code='605499',snapshot_id='old',cutoff='2025-11-01',financial_view=dict(latest_period='2025-09-30',ttm={'revenue':f}),facts=[dict(fact_id=f['fact_ids'][0])],evidence=[])
    obs=dict(metric='revenue',period='2026-09-30',value=120,unit='CNY',basis='ttm',sources=f['fact_ids'],origin='user_assumption')
    return dict(created_at='2025-11-01T10:00:00+08:00',payload=dict(code='605499',revision=1,snapshot_id='old',forecast_observations=[obs]),snapshot=old)


def test_current_rules_distinguish_breach_pending_and_due_review_without_orders():
    s=snapshot();a=dict(code='605499',monitor_rules=[dict(id='r',metric='revenue',operator='lt',threshold=150,
        unit='CNY',basis='ttm',target_period='2026-09-30',review_on='2026-10-31',rationale='低于收入假设',sources=['source'])])
    r=build_monitoring(s,a,None)
    assert r['rules'][0]['state']=='breached' and r['rules'][0]['actual']==140
    assert r['rules'][0]['review_due'] is True
    assert 'order' not in r
    a['monitor_rules'][0]['target_period']='2027-09-30'
    assert build_monitoring(s,a,None)['rules'][0]['state']=='pending'


def test_forward_check_uses_frozen_pre_period_version_and_does_not_replace_it_with_later_edits():
    h=history();later=history();later['created_at']='2026-11-01T10:00:00+08:00';later['payload']['revision']=2
    later['payload']['forecast_observations'][0]['value']=140
    r=build_monitoring(snapshot(),None,None,history=[later,h])
    row=r['forward_checks'][0]
    assert row['forecast']==120 and row['actual']==140 and row['error']==20
    assert row['revision']==1
    assert row['vintage']=='当前修订实际值，非历史当时可知回测'


def test_unmatured_wrong_units_missing_original_sources_and_other_company_are_not_validated():
    h=history();s=snapshot();h['payload']['forecast_observations'][0]['period']='2027-09-30'
    assert build_monitoring(s,None,None,history=[h])['forward_checks'][0]['state']=='pending'
    h=history();h['payload']['forecast_observations'][0]['unit']='ratio'
    assert build_monitoring(s,None,None,history=[h])['forward_checks'][0]['state']=='insufficient'
    h=history();h['snapshot']['facts']=[]
    assert build_monitoring(s,None,None,history=[h])['forward_checks'][0]['state']=='insufficient'
    h=history();h['payload']['code']='000807'
    assert build_monitoring(s,None,None,history=[h])['forward_checks']==[]


@pytest.mark.parametrize('invalid',[{'attribution':'all_claims'},{'scope':'parent'},{'period_basis':'quarter'},{'period_basis':None},{'formula':'reported'}])
def test_incompatible_parent_profit_actual_never_validates_forecast_or_thesis(invalid):
    s=snapshot();s['financial_view']['ttm']['net_profit'].update(invalid)
    h=history();h['payload']['forecast_observations'][0].update(metric='net_profit',value=12)
    a=dict(code='605499',monitor_rules=[dict(id='profit',metric='net_profit',operator='lt',threshold=18,unit='CNY')])
    r=build_monitoring(s,a,None,history=[h])
    assert r['forward_checks'][0]['state']=='insufficient'
    assert r['rules'][0]['state']=='insufficient'


def test_historical_ttm_requires_previous_ytd_and_annual_basis():
    s=snapshot();s['financial_view']['latest_period']='2027-09-30'
    s['financial_view']['periods']=[dict(period=p,metrics={'revenue':fv(v,p)|dict(period_basis=basis)}) for p,v,basis in
        [('2026-09-30',100,'ytd'),('2025-12-31',120,'quarter'),('2025-09-30',80,'ytd')]]
    h=history()
    assert build_monitoring(s,None,None,history=[h])['forward_checks'][0]['state']=='insufficient'


def test_portfolio_concentration_and_price_stop_are_separate_from_value_thesis_failure():
    s=snapshot();s['binding']={'quote':{'valid':True,'price':100}}
    p=dict(complete=True,nav=1000,positions=[dict(code='605499',market_value=300,stop=110,sector='x')],
        risk=dict(stock_cap=.2,sector_cap=.5,total_cap=.8))
    r=build_monitoring(s,None,None,portfolio=p)
    assert r['portfolio']['stock_weight']==.3
    assert any('集中度' in signal['message'] for signal in r['signals'])
    assert any('不自动判定长期假说失效' in signal['message'] for signal in r['signals'])


def test_quarter_review_date_does_not_slide_forward_on_every_page_read():
    s=snapshot()
    r=build_monitoring(s,None,None,as_of='2027-03-01')
    assert r['next_review']=='2027-02-01'
    assert any(signal['kind']=='scheduled_review' for signal in r['signals'])
