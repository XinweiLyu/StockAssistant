import pytest
from src.services.a_share_value_strategy import build_value_strategy
from tests.test_a_share_value_economics import fv
from tests.test_a_share_value_valuation import operating_case


def snapshot(model='operating'):
    annual=[]
    for i in range(5):
        p=f'{2021+i}-12-31';rev=100*1.1**i
        metrics={k:fv(v,p,'parent_common' if k=='net_profit' else 'all_claims') for k,v in
            dict(revenue=rev,net_profit=rev*.1,operating_profit=rev*.15,operating_cashflow=rev*.2,capex=rev*.05).items()}
        annual.append(dict(period=p,metrics=metrics))
    ttm={k:fv(v,'2026-09-30','parent_common' if k=='net_profit' else 'all_claims') for k,v in
        dict(revenue=140,net_profit=14,operating_profit=21,operating_cashflow=28,capex=7).items()}
    facts=[dict(fact_id=i) for row in annual for f in row['metrics'].values() for i in f['fact_ids']]
    facts.extend(dict(fact_id=i) for f in ttm.values() for i in f['fact_ids'])
    return dict(code='605499',name='公司',cutoff='2026-11-01T10:00:00+08:00',snapshot_id='s',facts=facts,evidence=[],events=[],
        economic_model=dict(model=model,allowed_methods=['ddm','fcff'] if model=='operating' else ['rim']),
        financial_view=dict(latest_period='2026-09-30',annual=annual,periods=annual,ttm=ttm,latest={},current_capital=None),missing=[])


def test_company_history_generates_sourced_driver_ranges_and_labeled_projections_not_target_prices():
    s=snapshot();r=build_value_strategy(s)
    driver=r['company_drivers']
    assert driver['growth_range']['median']==pytest.approx(.1)
    assert driver['projections'][1]['years'][4]['revenue']==pytest.approx(225.4714)
    assert driver['origin']=='company_history'
    assert driver['state']=='historical_projection'
    assert driver['sources'] and set(driver['sources'])<={f['fact_id'] for f in s['facts']}
    assert 'price' not in driver['projections'][0]['years'][0]


def test_financial_missing_and_future_assumptions_are_separate_and_wrong_methods_are_not_missing_data():
    r=build_value_strategy(snapshot('bank'))
    assert any(g['kind']=='fact' and '股本' in g['item'] for g in r['gaps'])
    assert any(g['kind']=='assumption' for g in r['gaps'])
    assert r['company_drivers']['projections']==[]
    assert any(g['kind']=='method' and 'fcff' in g['item'] for g in r['gaps'])


def test_discontinuous_history_and_losses_do_not_become_smooth_growth_forecasts():
    s=snapshot();s['financial_view']['annual']=s['financial_view']['annual'][::2]
    r=build_value_strategy(s)['company_drivers']
    assert not r['projections']
    assert r['reason']
    s=snapshot();s['financial_view']['ttm']['net_profit']['value']=-1
    assert not build_value_strategy(s)['company_drivers']['projections']


def test_recent_historical_break_is_not_hidden_by_three_older_growth_samples():
    s=snapshot();row=s['financial_view']['annual'][-1];row['period']='2027-12-31'
    for f in row['metrics'].values():f['period']=row['period']
    assert not build_value_strategy(s)['company_drivers']['projections']


def test_terminal_dependence_and_unsupported_growth_are_explicit_review_checks():
    s=snapshot();case=operating_case();t=case['operating']['terminal'];t.update(growth=.04,capex_ratio=.05,nwc_ratio=0)
    case['terminal_growth']=.04
    r=build_value_strategy(s,{'cases':[case]}, {'valuation_cases':[dict(method='fcff',scenario='base',terminal_share=.9)]})
    assert any('终值' in c['message'] for c in r['economic_checks'])
    assert any('再投资' in c['message'] for c in r['economic_checks'])
