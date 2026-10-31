"""Executed counterexamples from the final review; no external/model requests."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import threading
import pytest

from src.schemas.a_share_value import ValueAssumptions, ValueFact, SupplementFact, SaveValueRequest, EvaluateValueRequest
from src.services.a_share_value_drivers import apply_driver_changes
from src.services.a_share_value_peers import build_peer_comparison
from src.services.a_share_value_research import ValueResearchEngine
from src.services.a_share_value_valuation import evaluate_value
from tests.test_a_share_value_service import value_service
from tests.test_a_share_value_valuation import operating_case
from tests.test_a_share_value_peers import peer
from data_provider.a_share_value_facts import normalize_current_capital


def test_holding_case_cannot_override_valued_capital_or_cashflows():
    with pytest.raises(ValueError):
        ValueAssumptions(code='600034', snapshot_id='s', holding_cases=[dict(months=12,
            method='ddm', scenario='base', realization_factor=1, shares=1, dividends=[1000]*5, fixed_capital=False)])


@pytest.mark.parametrize('bad', [dict(unit='CNY'), dict(period_basis='annual'), dict(attribution='minority'), dict(value=0)])
def test_current_capital_requires_ordinary_shares_and_instant_basis(bad):
    f = normalize_current_capital('600034', [dict(item='股票代码', value='600034'), dict(item='总股本', value=10)], '2026-10-30T10:00:00+08:00')[0]
    with pytest.raises(ValueError):
        ValueFact.model_validate(f | bad)
    manual = {k:f[k] for k in ('metric','value','unit','report_period','period_basis','scope','attribution')}
    with pytest.raises(ValueError):
        SupplementFact.model_validate(manual | dict(url='https://example.com/report',title='报告',published_at='2026-10-30',quote='总股本',reason='核对') | bad)


def test_same_event_can_change_three_scenarios_but_not_the_same_cell_twice():
    event = dict(id='E',family_id='family',published_at='2026-10-20')
    change = dict(event_id='E',field='ebit_margin',unit='ratio',old=.2,new=.18,years=[1,2],half_life_years=1,
        already_in_baseline=False,rationale='成本原文桥接',sources=['E'])
    cases = [operating_case(scenario=s) for s in ('conservative','base','upside')]
    changes = [change | dict(scenario=s) for s in ('conservative','base','upside')]
    result = apply_driver_changes(dict(cutoff='2026-10-30',events=[event]),dict(cases=cases,driver_changes=changes+[changes[0]]))
    assert len(result['effects']) == 3
    assert len(result['rejected']) == 1
    assert all(c['operating']['years'][0]['ebit_margin'] == .18 for c in result['cases'])


@pytest.mark.parametrize('section', ['driver_changes','theses','economic_model_override'])
def test_nested_model_references_must_have_been_delivered(tmp_path, section):
    svc=value_service(tmp_path);snapshot=svc.value.capture('600034');fact=snapshot['facts'][0]['fact_id']
    # Present in snapshot but too large to be sent: existing != delivered.
    snapshot['evidence'].append(dict(id='OMITTED',source='source',content={'large':'x'*60000}))
    proposed=dict(code='600034',snapshot_id=snapshot['snapshot_id'],cases=[operating_case() | dict(evidence_ids=[fact])])
    proposed[section] = ([dict(event_id='OMITTED',sources=['OMITTED'])] if section=='driver_changes' else
        [dict(text='未送达的论点',sources=['OMITTED'])] if section=='theses' else
        dict(model='operating',reason='业务',evidence_ids=['OMITTED']))
    response=dict(perspectives=[dict(text='资料',sources=[fact])],proposed_assumptions=proposed)
    result=ValueResearchEngine(svc.repo,lambda *_:response).run(snapshot,svc.settings,lambda _:None)
    assert 'OMITTED' not in result['sent_ids']
    assert result['proposed_assumptions'] is None
    assert result['status'] != 'complete'


def test_peer_valuation_dates_and_definitions_are_aligned_per_metric():
    target=peer('0') | dict(metric_basis={'pe':dict(date='2026-10-30',definition='pe_ttm',source='vendor')})
    candidates=[peer(str(i)) | dict(metric_basis={'pe':dict(date='2025-10-30',definition='pe_ttm',source='vendor')}) for i in range(1,6)]
    confirmations=[dict(code=p['code'],evidence_ids=['B']) for p in candidates]
    result=build_peer_comparison(target,candidates,confirmations)
    assert result['metrics']['pe']['n']==0
    assert result['metrics']['pe']['percentile'] is None
    assert result['metrics']['pe']['excluded']


def test_peer_row_keeps_own_economic_identity_and_metric_observation(tmp_path, monkeypatch):
    svc=value_service(tmp_path)
    industries={'600034':dict(sector_id='industry:food',name='食品',classification='eastmoney-industry'),
                '600001':dict(sector_id='industry:bank',name='银行',classification='eastmoney-industry')}
    monkeypatch.setattr(svc.integrated,'_industry',lambda code:industries.get(code))
    data=dict(facts=[dict(fact_id='FV',source='eastmoney/stock_value_em',values={'pe_ttm':10,'pb':2,'trade_date':'2026-10-29'})])
    row=svc.value._peer_row(dict(code='600001',name='银行',identity_verified=True),data,{}, {'latest_period':'2026-09-30','latest':{},'ttm':{}},industries['600034'])
    assert row['economic_model']=='bank'
    assert row['industry_id']=='industry:bank'
    assert row['metric_basis']['pe']['date']=='2026-10-29'


def test_review_becomes_history_when_assumptions_change(tmp_path):
    svc=value_service(tmp_path);s=svc.value.capture('600034')
    svc.repo.append('free','value_review','free:600034',dict(snapshot_id=s['snapshot_id'],published_revision=0,
        model=svc.settings.model,status='partial',theses=[dict(text='A',sources=[])]))
    saved=svc.value.save_assumptions('600034',SaveValueRequest(snapshot_id=s['snapshot_id'],expected_revision=0,
        assumptions=dict(code='600034',snapshot_id=s['snapshot_id'],theses=[dict(text='B')]),confirmed=False))
    result=svc.value.get('600034')
    assert saved['revision']==1
    assert result['review'] is None
    assert result['historical_review']['theses'][0]['text']=='A'


def test_attempt_claim_is_atomic_across_worker_recovery(tmp_path):
    svc=value_service(tmp_path);repo=svc.market.repo
    task_id=repo.enqueue('free','value-race','value_research',{},25)
    old=repo.claim('free',datetime.now(timezone.utc),kinds=['value_research'])
    repo.recover_running('free',kinds=['value_research'])
    new=repo.claim('free',datetime.now(timezone.utc),kinds=['value_research'])
    assert old['id']==new['id']==task_id
    barrier=threading.Barrier(2)
    def attempt(task):
        barrier.wait()
        return repo.begin_value_attempt(task, 's')
    with ThreadPoolExecutor(2) as pool:
        states=list(pool.map(attempt,[old,new]))
    assert states.count('claimed')==1
    assert 'claim_lost' in states
    assert repo.begin_value_attempt(new,'s')=='attempted'


def conditional_fixture():
    now='2026-10-30T10:00:00+08:00'
    f=normalize_current_capital('600034',[dict(item='股票代码',value='600034'),dict(item='总股本',value=10)],now)[0]
    a=dict(code='600034',snapshot_id='s',confirmed=True,revision=1,margin_required=.3,primary_method='fcff',
        cases=[operating_case(scenario=x) | dict(evidence_ids=[f['fact_id']]) for x in ('conservative','base','upside')],
        risk_review={k:dict(status='reviewed',sources=[f['fact_id']]) for k in ('audit','debt','capital','reinvestment','nonoperating_assets')})
    s=dict(code='600034',name='样本',snapshot_id='s',cutoff=now,facts=[f],economic_model=dict(model='cyclical',allowed_methods=['fcff']),
        financial_view=dict(annual=[],current_capital=dict(value=10,period='2026-10-30',available_at=now)),
        binding=dict(eligibility={'eligible':True},quote=dict(price=6,valid=True,trade_date='2026-10-30')))
    return a,s


def test_cycle_missing_history_and_structural_assessment_blocks_conditional_price():
    a,s=conditional_fixture()
    result=evaluate_value(a,s)
    assert result['valuation_state']!='conditional'
    assert result['comparison']['conditional_price'] is None
    assert any('周期' in m for m in result['missing'])


def test_old_integrated_case_cache_cannot_be_revived_as_value_evidence(tmp_path, monkeypatch):
    svc=value_service(tmp_path)
    svc.repo.append('free','research_pointer','free:600034',dict(data_hash='old'))
    monkeypatch.setattr(svc.integrated,'bundle',lambda _:dict(code='600034',version='obsolete',cutoff='2026-10-20',cases=[dict(id='OLD')]))
    assert not svc.value.capture('600034')['cases']
