from datetime import datetime,timezone
from types import SimpleNamespace
import threading
from sqlalchemy import create_engine
from src.repositories.a_share_repository import AssistantRepository
from src.schemas.a_share import AssistantSettings
from src.schemas.a_share_market import CatalogQuery
from tests.test_market_workspace_service import Source
from tests.test_market_workspace_financials import fact,NOW


class ResearchSources:
    def fetch(self,identity,metadata,cutoff):
        facts=[fact('revenue',120,'2025-10-01','2026-09-30'),fact('operating_cashflow',40,'2025-10-01','2026-09-30'),fact('capex',10,'2025-10-01','2026-09-30')]
        return dict(value_facts=facts,facts=[dict(fact_id=f['fact_id'],code=identity.instrument_id,category='financial',values={f['metric']:f['value']},
            source=f['source'],available_at=f['available_at'],published_at=f['published_at'],report_period=f['report_period'],vintage_quality='latest_reconstructed') for f in facts],
            events=[],coverage=[dict(category='financial',status='partial',count=len(facts))],distributions=[],valuation_history=[],missing=['长期债务未取得'])


def make_workspace(tmp_path):
    from src.services.market_workspace_service import MarketWorkspaceService
    parent=SimpleNamespace(repo=AssistantRepository(create_engine('sqlite:///'+str(tmp_path/'r.db'))),
        settings=AssistantSettings(mode='free'),_settings_lock=threading.RLock())
    workspace=MarketWorkspaceService(parent,'us',provider=Source(),clock=lambda:datetime(2026,11,16,8,tzinfo=timezone.utc))
    workspace.initialize_research(ResearchSources())
    workspace.catalog(CatalogQuery());workspace.stock('AAPL')
    while workspace.jobs.run_one():pass
    return workspace


def test_preparing_value_uses_shared_snapshot_and_preserves_native_currency(tmp_path):
    workspace=make_workspace(tmp_path)
    value=workspace.assistant.value
    assert value.get('us:AAPL')['snapshot'] is None
    action=value.prepare('us:AAPL')
    assert action['accepted']
    assert workspace.assistant.integrated.jobs.run_one()
    result=value.get('us:AAPL')
    assert result['snapshot']['market']=='us' and result['snapshot']['currency']=='USD'
    assert result['snapshot']['financial_view']['annual'][0]['period']=='2026-09-30'
    assert not workspace.assistant.repo.records('free','value_review')
    assert result['snapshot']['binding']['listing']['ready'] is False


def test_old_a_share_api_cannot_read_market_qualified_catalog(tmp_path):
    workspace=make_workspace(tmp_path)
    from src.repositories.a_share_market_repository import MarketRepository
    assert MarketRepository(workspace.repo.engine).stock('free','us:AAPL') is None


def test_unknown_original_publication_is_usable_only_as_current_observation():
    from data_provider.offshore_research import normalize_yahoo_statements
    import pandas as pd
    frame=pd.DataFrame({'2026-09-30':{'Total Revenue':120.,'Operating Income':20.}})
    rows=normalize_yahoo_statements('us:AAPL',frame,'income','annual','USD',NOW)
    assert rows and all(r['published_at'] is None and r['available_at']==NOW for r in rows)
    from src.services.a_share_value_financials import build_financial_view
    assert build_financial_view(rows,NOW)['ttm']['revenue']['value']==120.
    assert not build_financial_view(rows,'2026-10-01T00:00:00+00:00')['latest']


def test_offshore_plans_do_not_apply_a_share_lot_and_tax_costs():
    from tests.test_a_share_integrated_prediction import bundle,plan
    from src.services.a_share_integrated_prediction import validate_integrated_prediction
    data=bundle();data.update(code='us:AAPL');data['context'].update(market='us',currency='USD',board='unknown',st=None,asset_type='stock')
    result=validate_integrated_prediction(dict(plans=[plan()]),data,{'P1','F1','B20'},2.)
    assert result['plans'][0]['reward_risk']==2.5
    assert result['plans'][0]['net_reward_risk'] is None
    assert not any('100股' in r for r in result['plans'][0]['rejection_reasons'])
    assert any('本市场' in r for r in result['plans'][0]['rejection_reasons'])


def test_real_expert_pipeline_validates_offshore_forecasts_with_only_external_response_substituted(tmp_path,monkeypatch):
    import json
    from tests.test_a_share_integrated_prediction import bundle,forecast,plan
    from src.services.a_share_research import ResearchEngine
    monkeypatch.setattr('src.config.get_config',lambda:SimpleNamespace(llm_model_list=[],litellm_model='configured'))
    data=bundle();data['code']='us:AAPL';data['context'].update(market='us',currency='USD',asset_type='stock',board='unknown',st=None)
    contexts=[]
    def completion(messages,model):
        context=json.loads(messages[-1]['content']);contexts.append(context)
        assert '人民币' not in messages[0]['content']
        result={'claims':[{'text':'按来源判断趋势和事件，风险需复核','sources':['P1']}]}
        if context['role']=='research_manager':result.update(forecasts=[forecast()],plans=[plan()])
        return result
    repo=AssistantRepository(create_engine('sqlite:///'+str(tmp_path/'expert.db')))
    result=ResearchEngine(repo,completion=completion).run_integrated(data,AssistantSettings(mode='free',model='configured',research_enabled=True),'2026-10-16',manual=True)
    assert len(contexts)==6 and result['forecasts']
    assert result['plans'][0]['net_reward_risk'] is None
    assert any(e['values'].get('currency')=='USD' for e in contexts[-1]['evidence'] if e['id']=='P1')


def test_source_fetch_cannot_publish_research_into_a_changed_mode(tmp_path):
    workspace=make_workspace(tmp_path)
    integrated=workspace.assistant.integrated
    original=integrated.sources.fetch
    def changed(*args):
        result=original(*args)
        workspace.parent.settings=AssistantSettings(mode='demo')
        workspace.catalog(CatalogQuery())
        return result
    integrated.sources.fetch=changed
    integrated.prepare('us:AAPL')
    integrated.jobs.run_one()
    assert not workspace.assistant.repo.records('demo','research_data')
    assert not workspace.assistant.repo.records('free','research_data')


def test_value_capture_preserves_source_specific_missing_diagnostics(tmp_path):
    workspace=make_workspace(tmp_path)
    workspace.assistant.value.prepare('us:AAPL')
    workspace.assistant.integrated.jobs.run_one()
    result=workspace.assistant.value.get('us:AAPL')
    assert '长期债务未取得' in result['snapshot']['missing']
