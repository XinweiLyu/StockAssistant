from copy import deepcopy
import json
from sqlalchemy import create_engine
import pytest

from src.repositories.a_share_repository import AssistantRepository
from src.schemas.a_share import AssistantSettings
from src.services.a_share_research import ResearchEngine
from src.services.a_share_integrated_prediction import validate_integrated_prediction, strategy_candidates, numeric_references


@pytest.fixture(autouse=True)
def isolated_model_config(monkeypatch):
    from types import SimpleNamespace
    # Inject the config dependency used by evidence budgets; never load a developer's .env in mocked model tests.
    monkeypatch.setattr('src.config.get_config',lambda:SimpleNamespace(llm_model_list=[],litellm_model='configured'))


def bundle():
    return dict(code='000807', name='云铝股份', data_hash='frozen-a', cutoff='2026-10-16T10:00:00+08:00',
        anchor_date='2026-10-15', reference_price=20., source='fixture', history_binding={'anchor_date':'2026-10-15'},
        context=dict(identity_verified=True, st=False, board='main', price=dict(features={'atr':1.})),
        baseline=dict(trends=[dict(period=p,state='up') for p in (60,120,250)], weekly=dict(state='up'),
            environment=dict(market_state='up',relative20=.1), plan=dict(status='conditional', reasons=[]),
            forecasts=[dict(horizon_sessions=h, low=17., median=22., high=27., target_date=None) for h in (5,20,60)]),
        facts=[dict(fact_id='F1',category='financial',source='original',available_at='2026-10-15T10:00:00+08:00',
            report_period='2026-06-30',values=dict(net_profit=123.),raw_fields=dict(PARENTNETPROFIT=123.)),
            dict(fact_id='N1',category='news',source='original',values=dict(title='原文',content='有来源的行业催化'))],
        events=[dict(id='event', text_status='ready', text='有原文的事件', direction='positive', public_verified=True, active_catalyst=True)],
        cases={'price_references':[]}, coverage=[],missing=[],demo=False)


def forecast(**changes):
    return dict(horizon_sessions=20,scenario='base',low=21.,high=23.,conditions=['业绩和趋势继续确认'],
                sources=['P1','F1'],basis_ids=['B20'],derivation='取价格模型参考范围内的情景，业绩仅支持条件判断',**changes)


def plan():
    return dict(horizon_sessions=20,strategy_kind='trend_pullback',status='conditional',entry_low=19.,entry_high=20.,
        stop_reference=18.,second_entry=dict(low=19.,high=19.5,conditions=['缩量回踩后确认'],invalidation=['跌破止损']),
        targets=[25.,26.],conditions=['趋势与业绩继续确认'],invalidation=['跌破支撑'],
        valid_until='2026-10-20',sources=['P1','F1'],basis_ids=['B20'],derivation='参考区间与风险尺度综合判断')


def test_valid_multidimensional_forecast_and_secondary_entry_have_traceable_basis():
    value = dict(forecasts=[forecast()],plans=[plan()])
    result = validate_integrated_prediction(value,bundle(),{'P1','F1','B20'},2.)
    assert result['status'] == 'ready'
    assert result['plans'][0]['reward_risk'] == 2.5
    assert result['plans'][0]['second_entry']['low'] == 19.
    assert result['forecasts'][0]['basis_ids'] == ['B20']
    assert result['calibrated'] is False


@pytest.mark.parametrize('patch', [dict(sources=['UNKNOWN']),dict(basis_ids=['C20']),
    dict(low=float('nan')),dict(low=30.,high=40.),dict(low=25.,high=24.),dict(confidence=.99)])
def test_bad_citations_or_numbers_do_not_reach_forecast(patch):
    f=forecast();f.update(patch)
    result=validate_integrated_prediction(dict(forecasts=[f],plans=[]),bundle(),{'P1','F1','B20'},2.)
    assert result['forecasts']==[] and result['rejected']>0


def test_no_reference_withholds_numeric_forecast():
    b=bundle();b['baseline']['forecasts']=[]
    result=validate_integrated_prediction(dict(forecasts=[forecast()],plans=[]),b,{'P1','F1'},2.)
    assert result['status']=='insufficient'


def test_old_event_and_prices_outside_cited_envelope_cannot_enable_strategy():
    b=bundle();b['events'][0]['active_catalyst']=False
    assert not next(s for s in strategy_candidates(b,2.) if s['strategy_kind']=='event_followthrough')['eligible']
    p=plan();p.update(entry_low=1.,entry_high=2.,stop_reference=.5,second_entry=None)
    result=validate_integrated_prediction(dict(plans=[p]),b,{'P1','F1','B20'})
    assert not result['plans'] and result['rejected'] == 1


def test_secondary_entry_cannot_smuggle_unverified_promises():
    p=plan();p['second_entry']['conditions']=['保证收益，立即买']
    result=validate_integrated_prediction(dict(plans=[p]),bundle(),{'P1','F1','B20'})
    assert not result['plans']


def test_low_reward_risk_is_observe_without_raising_target():
    p=plan();p['targets']=[21.,22.]
    result=validate_integrated_prediction(dict(forecasts=[],plans=[p]),bundle(),{'P1','F1','B20'},2.)
    assert result['plans'][0]['status']=='observe'
    assert result['plans'][0]['targets']==[21.,22.]


@pytest.mark.parametrize('valid_until', ['20260101', '20261231', '2026-W01-1',
    '2026-1-01', '2026-02-30', '2026-10-20T00:00:00+08:00', ' 2026-10-20 '])
def test_plan_dates_require_canonical_calendar_dates(valid_until):
    from pydantic import ValidationError
    from src.schemas.a_share_integrated import IntegratedPlan

    p=plan();p['valid_until']=valid_until
    with pytest.raises(ValidationError):
        IntegratedPlan.model_validate(p)


@pytest.mark.parametrize('valid_until', ['2026-01-01', '20260101', '2026-W01-1'])
def test_expired_plans_cannot_bypass_cutoff_with_alternative_iso_date_forms(valid_until):
    p=plan();p['valid_until']=valid_until
    result=validate_integrated_prediction(dict(plans=[p]),bundle(),{'P1','F1','B20'})
    assert result['plans']==[]
    assert result['rejected']==1


@pytest.mark.parametrize('valid_until', ['2026-10-16', '2026-10-20'])
def test_unexpired_canonical_plan_dates_are_preserved(valid_until):
    p=plan();p['valid_until']=valid_until
    result=validate_integrated_prediction(dict(plans=[p]),bundle(),{'P1','F1','B20'})
    assert result['plans'][0]['valid_until']==valid_until
    assert result['plans'][0]['status']=='conditional'


def test_reused_friday_bundle_cannot_publish_expired_saturday_plan_on_sunday():
    p=plan();p['valid_until']='2026-10-17'
    result=validate_integrated_prediction(dict(forecasts=[forecast()],plans=[p]),bundle(),
        {'P1','F1','B20'},as_of_day='2026-10-18')
    assert result['plans']==[]
    assert len(result['forecasts'])==1
    assert result['rejected']==1


def test_issuance_day_cannot_weaken_the_frozen_bundle_expiry_cutoff():
    p=plan();p['valid_until']='2026-10-15'
    result=validate_integrated_prediction(dict(plans=[p]),bundle(),
        {'P1','F1','B20'},as_of_day='2026-10-14')
    assert result['plans']==[]
    assert result['rejected']==1


@pytest.mark.parametrize('changes', [
    dict(targets=[],entry_low=1.),
    dict(entry_low=None,targets=[-100.]),
    dict(stop_reference=None,targets=[30.]),
    dict(entry_high=None,targets=[26.,25.]),
    dict(targets=[],entry_low=21.,entry_high=20.),
    dict(entry_low=None,stop_reference=21.),
    dict(stop_reference=None,targets=[19.]),
    dict(entry_low=None,second_entry=dict(low=24.,high=19.,conditions=['核对条件'],invalidation=['核对失效'])),
    dict(entry_low=None,second_entry=dict(low=1.,high=19.,conditions=['核对条件'],invalidation=['核对失效'])),
])
def test_incomplete_plans_still_reject_unsupported_or_inverted_prices(changes):
    p=plan();p.update(changes)
    result=validate_integrated_prediction(dict(plans=[p]),bundle(),{'P1','F1','B20'})
    assert result['plans']==[]
    assert result['rejected']==1


def test_partial_plan_with_valid_supplied_prices_remains_an_observation():
    p=plan();p.update(entry_low=None)
    result=validate_integrated_prediction(dict(plans=[p]),bundle(),{'P1','F1','B20'})
    assert result['plans'][0]['status']=='observe'
    assert result['plans'][0]['entry_low'] is None
    assert result['plans'][0]['targets']==[25.,26.]
    assert result['rejected']==0


@pytest.mark.parametrize('changes', [dict(stop_reference=1.e100),dict(targets=[1.e100]),
    dict(second_entry=dict(low=19.,high=1.e100,conditions=['核对条件'],invalidation=['核对失效']))])
def test_unrepresentable_plan_prices_are_rejected_without_losing_valid_forecasts(changes):
    p=plan();p.update(changes)
    result=validate_integrated_prediction(dict(forecasts=[forecast()],plans=[p]),bundle(),{'P1','F1','B20'})
    assert result['plans']==[]
    assert len(result['forecasts'])==1
    assert result['status']=='partial'
    assert result['rejected']==1


def test_current_verified_major_risk_blocks_every_strategy_independent_of_old_baseline():
    b=bundle();b['context']['major_risk']=True
    assert not any(s['eligible'] for s in strategy_candidates(b,2.))
    result=validate_integrated_prediction(dict(plans=[plan()]),b,{'P1','F1','B20'})
    assert result['plans'][0]['status']=='observe'


def test_verified_risk_or_long_downtrend_cannot_be_called_trend_reversal():
    b=bundle();b['baseline']['trends'][2]['state']='down'
    assert not any(s['strategy_kind']=='trend_pullback' and s['eligible'] for s in strategy_candidates(b,2.))
    b=bundle();b['baseline']['plan']['reasons']=['已核实重大风险']
    result=validate_integrated_prediction(dict(forecasts=[forecast()],plans=[plan()]),b,{'P1','F1','B20'},2.)
    assert result['plans'][0]['status']=='observe'


def test_integrated_roles_receive_real_financial_and_prior_evidence(tmp_path):
    repo=AssistantRepository(create_engine('sqlite:///'+str(tmp_path/'r.db')))
    inputs=[]
    def completion(messages,model):
        data=json.loads(messages[1]['content']);inputs.append(data)
        value=dict(claims=[dict(text='据原文和价格资料仍需核对持续性',sources=['P1'])])
        if data['role']=='research_manager': value.update(forecasts=[forecast()],plans=[plan()])
        return value
    engine=ResearchEngine(repo,completion)
    settings=AssistantSettings(mode='free',model='configured',research_enabled=True,daily_model_calls=0)
    result=engine.run_integrated(bundle(),settings,'2026-10-16',manual=True)
    assert result['status']=='complete'
    assert len(result['roles'])==6 and result['calls']==6
    manager=inputs[-1]
    assert len(manager['prior_roles'])==5
    financial=next(i for i in inputs if i['role']=='fundamentals_analyst')
    assert 'PARENTNETPROFIT' in json.dumps(financial)
    assert result['forecasts'][0]['low']==21.
    assert repo.manual_usage('free','2026-10-16')==6
    cached=engine.run_integrated(bundle(),settings,'2026-10-16',manual=True)
    assert cached['cached'] is True and len(inputs)==6
    changed=bundle();changed['data_hash']='frozen-b';changed['facts'][0]['raw_fields']['PARENTNETPROFIT']=456.
    engine.run_integrated(changed,settings,'2026-10-16',manual=True)
    assert any('456' in json.dumps(i) for i in inputs[6:])


@pytest.mark.parametrize('valid_until', ['2026-10-17','20261020','2026-W43-1','2026-02-30',None])
def test_complete_cache_with_expired_or_invalid_plan_dates_is_regenerated(tmp_path,valid_until):
    from src.schemas.a_share_integrated import VERSION, digest

    repo=AssistantRepository(create_engine('sqlite:///'+str(tmp_path/'cache.db')))
    b=bundle();saved_plan=plan();saved_plan['valid_until']=valid_until
    repo.append('free','integrated_cache',digest([VERSION,b['data_hash'],'configured']),
        dict(status='complete',forecasts=[forecast()],plans=[saved_plan]))
    def completion(messages,model):
        data=json.loads(messages[1]['content'])
        value=dict(claims=[dict(text='根据已提供资料核对条件',sources=['P1'])])
        if data['role']=='research_manager':
            value.update(forecasts=[forecast()],plans=[plan()])
        return value

    result=ResearchEngine(repo,completion).run_integrated(b,
        AssistantSettings(mode='free',model='configured',research_enabled=True),'2026-10-18')
    assert result['cached'] is False
    assert result['calls']==6
    assert result['plans'][0]['valid_until']=='2026-10-20'


@pytest.mark.parametrize('cached_plans', [[],[dict(valid_until='2026-10-18')],[dict(valid_until='2026-10-20')]])
def test_complete_cache_with_unexpired_or_no_plans_is_reused_without_model_calls(tmp_path,cached_plans):
    from src.schemas.a_share_integrated import VERSION, digest

    repo=AssistantRepository(create_engine('sqlite:///'+str(tmp_path/'cache.db')))
    b=bundle()
    repo.append('free','integrated_cache',digest([VERSION,b['data_hash'],'configured']),
        dict(status='complete',forecasts=[forecast()],plans=cached_plans))
    def unexpected_completion(*_):
        raise AssertionError('有效缓存不应调用研究模型')

    result=ResearchEngine(repo,unexpected_completion).run_integrated(b,
        AssistantSettings(mode='free',model='configured',research_enabled=True),'2026-10-18')
    assert result['cached'] is True
    assert result['calls']==0
    assert result['forecasts'][0]['low']==21.
    assert result['plans']==cached_plans


def test_failed_role_preserves_others_and_does_not_hide_attempts(tmp_path):
    repo=AssistantRepository(create_engine('sqlite:///'+str(tmp_path/'r.db')))
    def completion(messages,model):
        data=json.loads(messages[1]['content'])
        if data['role']=='fundamentals_analyst': raise TimeoutError('secret')
        return dict(claims=[dict(text='有事实引用',sources=['P1'])])
    result=ResearchEngine(repo,completion).run_integrated(bundle(),AssistantSettings(mode='free',model='x',research_enabled=True),'2026-10-16')
    assert result['status']=='partial'
    assert result['calls']==6
    assert any(r['status']=='failed' for r in result['roles'])
    assert 'secret' not in json.dumps(result)


def test_unavailable_experts_are_skipped_and_disabled_research_is_free(tmp_path):
    repo=AssistantRepository(create_engine('sqlite:///'+str(tmp_path/'r.db')))
    b=bundle();b['facts']=[];b['events']=[]
    result=ResearchEngine(repo,lambda *_:dict(claims=[dict(text='价格事实',sources=['P1'])])).run_integrated(
        b,AssistantSettings(mode='free',research_enabled=True,model='x'),'2026-10-16')
    assert result['calls']==4
    assert any(r['role']=='fundamentals_analyst' and r['status']=='skipped' for r in result['roles'])
    disabled=ResearchEngine(repo).run_integrated(b,AssistantSettings(),'2026-10-16')
    assert disabled['status']=='disabled' and disabled['calls']==0


def test_budget_uses_declared_capacity_and_does_not_pay_expert_after_its_facts_are_omitted(tmp_path,monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr('src.config.get_config',lambda:SimpleNamespace(llm_model_list=[dict(model_name='x',model_info=dict(assistant_research_input_bytes=10000))],litellm_model='x'))
    inputs=[]
    def completion(messages,model):
        inputs.append(json.loads(messages[1]['content']))
        return dict(claims=[dict(text='只研究已收到的资料',sources=['P1'])])
    b=bundle();b['facts'][0]['values']['large_note']='财务'*15000
    engine=ResearchEngine(AssistantRepository(create_engine('sqlite:///'+str(tmp_path/'r.db'))),completion)
    result=engine.run_integrated(b,AssistantSettings(mode='free',research_enabled=True,model='x'),'2026-10-16')
    assert all(len(json.dumps(i,ensure_ascii=False).encode())+6000<=10000 for i in inputs)
    assert 'fundamentals_analyst' not in {i['role'] for i in inputs}
    assert 'F1' in result['role_evidence']['fundamentals_analyst']['omitted_ids']


def test_progress_reports_completed_roles_and_observed_times_without_extra_calls(tmp_path,monkeypatch):
    seconds=[0.];events=[]
    monkeypatch.setattr('time.monotonic',lambda:seconds[0])
    repo=AssistantRepository(create_engine('sqlite:///'+str(tmp_path/'progress.db')))
    def completion(messages,model):
        seconds[0]+=30
        data=json.loads(messages[1]['content'])
        value=dict(claims=[dict(text='有来源的研究意见',sources=['P1'])])
        if data['role']=='research_manager':value.update(forecasts=[forecast()],plans=[plan()])
        return value
    r=ResearchEngine(repo,completion).run_integrated(bundle(),AssistantSettings(mode='free',model='configured',research_enabled=True),'2026-10-17',progress=events.append)
    assert r['calls']==6
    assert r['timing']['elapsed_seconds']==180
    assert all(s['duration_seconds']==30 for s in events[-1]['steps'])
    assert [e['completed'] for e in events if e.get('phase')=='research' and not e.get('current')]==[1,2,3,4,5,6]
    assert any(e.get('phase')=='validating' for e in events)
    assert events[-1]['phase']=='saving'


def test_integrated_billing_failure_is_explicit_and_never_invents_forecasts(tmp_path):
    import subprocess
    from sqlalchemy import create_engine
    from src.repositories.a_share_repository import AssistantRepository
    from src.schemas.a_share import AssistantSettings
    from src.services.a_share_research import ResearchEngine
    repo=AssistantRepository(create_engine('sqlite:///' + str(tmp_path/'billing')))
    def completion(*_):
        raise subprocess.CalledProcessError(1,['python'],stderr='BadRequestError: Arrearage; api_key=sk-test-secret')
    report=ResearchEngine(repo,completion=completion).run_integrated(bundle(),
        AssistantSettings(mode='free',research_enabled=True,model='mock'),'2026-10-17')
    assert report['forecasts']==[] and report['plans']==[]
    assert report['roles'][-1]['status']=='failed'
    assert '欠费' in report['roles'][-1]['message']
    assert 'sk-test-secret' not in str(report)
