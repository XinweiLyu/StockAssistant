"""Independent review counterexamples, exercised against production boundaries."""
from copy import deepcopy
import json
from sqlalchemy import create_engine
from data_provider.a_share_fundamentals import normalize_news, normalize_financials, financial_coverage
from src.schemas.a_share import AssistantSettings
from src.repositories.a_share_repository import AssistantRepository
from src.services.a_share_research import ResearchEngine
from src.services.a_share_integrated_research import _evidence
from src.services.a_share_integrated_prediction import strategy_candidates, validate_integrated_prediction
from tests.test_a_share_integrated_prediction import bundle, plan, forecast, isolated_model_config
from tests.test_a_share_integrated_service import facts
from tests.test_a_share_outlook_api import long_market
from tests.test_a_share_integrated_validation import data
from src.services.a_share_integrated_validation import evaluate_integrated_snapshots


def test_revocation_supersedes_old_positive_catalyst_for_every_strategy():
    b=bundle()
    b['events']=[dict(id='old',family_id='same',published_at='2026-10-10',public_verified=True,
        active_catalyst=True,direction='positive'),dict(id='withdrawn',family_id='same',published_at='2026-10-15',
        public_verified=True,active_catalyst=True,direction='unknown',extraction_status='withdrawn')]
    assert not next(s for s in strategy_candidates(b,2.) if s['strategy_kind']=='event_followthrough')['eligible']


def test_all_expert_claims_reject_probability_and_guaranteed_profit(tmp_path):
    repo=AssistantRepository(create_engine('sqlite:///'+str(tmp_path/'r.db')))
    received=[]
    def completion(messages,model):
        received.append(json.loads(messages[1]['content']))
        return dict(claims=[dict(text='本次上涨概率99%，保证收益。',sources=['P1'])])
    result=ResearchEngine(repo,completion).run_integrated(bundle(),AssistantSettings(mode='free',model='configured',research_enabled=True),'2026-10-16')
    assert all(not r['claims'] for r in result['roles'])
    assert all(not c for data in received for r in data['prior_roles'] for c in r['claims'])
    f=forecast();f['conditions']=['上涨概率99%']
    assert not validate_integrated_prediction(dict(forecasts=[f]),bundle(),{'P1','F1','B20'})['forecasts']


def test_news_version_changes_when_body_or_original_source_changes():
    row=dict(title='云铝股份业绩预告',content='000807预计增长80%',url='https://example.com/a',published_at='2026-10-15T16:00:00+08:00')
    a=normalize_news('000807','云铝股份',[row],'2026-10-16T10:00:00+08:00')['facts'][0]
    b=normalize_news('000807','云铝股份',[row|dict(content='000807更正：预计下降80%')],'2026-10-16T10:00:00+08:00')['facts'][0]
    assert a['fact_id']!=b['fact_id'] and a['content_hash']!=b['content_hash']
    assert a['family_id']==b['family_id']


def test_financial_report_types_survive_routing_and_cannot_merge_cumulative_and_quarterly():
    fs=normalize_financials('000807',[dict(end_date='20260630',n_income_attr_p=100.,report_type='1'),
        dict(end_date='20260630',n_income_attr_p=30.,report_type='2')],'tushare/income','2026-10-16T10:00:00+08:00')
    b=bundle();b['facts']=fs;b['context']['financial_coverage']=financial_coverage(fs)
    routed=[e for e in _evidence(b) if e['id'] in {f['fact_id'] for f in fs}]
    assert {e['report_type'] for e in routed}=={'1','2'}
    coverage=b['context']['financial_coverage']['fields']['net_profit']
    assert coverage['status']=='mixed_types' and not coverage.get('values')
    assert {o['report_type'] for o in coverage['observations']}=={'1','2'}


def test_news_publication_time_survives_routing_separately_from_observation():
    b=bundle();b['facts'][1].update(published_at='2026-07-01T16:00:00+08:00',available_at='2026-10-16T10:00:00+08:00')
    news=next(e for e in _evidence(b) if e['id']=='N1')
    assert news['published_at']=='2026-07-01T16:00:00+08:00'
    assert news['available_at']!=news['published_at']


def test_preparing_cannot_clear_configuration_staleness(tmp_path):
    svc,_=long_market(tmp_path)
    b=svc.integrated.freeze('600000',facts())
    svc.repo.append('free','integrated_report','free:600000',dict(data_hash=b['data_hash'],plans=[],status='complete'))
    svc.settings=svc.settings.model_copy(update={'free_fallback':False})
    svc.integrated.prepare('600000')
    result=svc.integrated.get('600000')
    assert result['status']=='preparing' and result['report']['stale'] is True


def test_generate_cannot_recertify_old_configuration_evidence(tmp_path):
    from src.services.a_share_market_service import source_signature
    svc,_=long_market(tmp_path)
    b=svc.integrated.freeze('600000',facts())
    svc.repo.append('free','research_data','free:600000',dict(facts=facts(),events=[],coverage=[],
        source_signature=list(source_signature(svc.settings))))
    svc.settings=svc.settings.model_copy(update={'free_fallback':False})
    result=svc.integrated.generate('600000')
    assert result['accepted'] is False
    assert svc.integrated.get('600000')['bundle']['data_hash']==b['data_hash']
    assert svc.integrated.get('600000')['status']=='stale'


def test_strategy_rounds_to_tick_and_downgrades_inadequate_cost_space():
    p=plan();p.update(entry_low=20.001,entry_high=20.002,stop_reference=20.,targets=[20.007],second_entry=None)
    result=validate_integrated_prediction(dict(plans=[p]),bundle(),{'P1','F1','B20'})
    assert not result['plans'] or result['plans'][0]['status']=='observe'
    p=plan();p.update(entry_low=20.02,entry_high=20.03,stop_reference=20.,targets=[20.11],second_entry=None)
    result=validate_integrated_prediction(dict(plans=[p]),bundle(),{'P1','F1','B20'})
    assert result['plans'][0]['status']=='observe'
    assert any('成本' in reason for reason in result['plans'][0]['rejection_reasons'])


def test_late_issuance_cannot_score_preexisting_price_window_and_intraday_path_is_unknown():
    calendar,bars,records=data()
    late=deepcopy(records);late[0]['payload']['generated_at']='2026-01-05T16:00:00+08:00'
    assert evaluate_integrated_snapshots(late,bars,calendar,'2026-02-01',source='fixture')['horizons']['5']['matured']==0
    intraday=deepcopy(records);intraday[0]['payload']['generated_at']='2026-01-02T10:00:00+08:00'
    result=evaluate_integrated_snapshots(intraday,bars,calendar,'2026-02-01',source='fixture')
    assert result['horizons']['5']['matured']==1
    assert result['horizons']['5']['mean_adverse'] is None
