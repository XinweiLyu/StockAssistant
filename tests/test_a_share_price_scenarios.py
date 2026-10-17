import copy
import json
import pytest
from sqlalchemy import create_engine
from src.repositories.a_share_repository import AssistantRepository
from src.schemas.a_share import AssistantSettings
from src.services.a_share_research import ResearchEngine
from src.services.a_share_price_scenarios import validate_price_scenarios, map_level_to_chart

CTX=dict(code='600000',anchor_date='2026-10-09',reference_price=10,currency='CNY',price_basis='raw',data_hash='h1',adjustment_basis='b1',features={'ma20':9.8})
PLAN=dict(horizon_sessions=20,entry_low=10,entry_high=10.2,stop_reference=9,sell_low=12,sell_high=13,conditions=['趋势维持'],invalidation=['趋势破坏'],sources=['P1'])

def test_complete_prices_are_separate_from_claims_and_actions():
    r=validate_price_scenarios({'trade_levels':PLAN,'forecasts':[]},{'P1'},CTX)
    assert r['trade_levels']['entry_low']==10 and r['status']=='ready'

@pytest.mark.parametrize('field,value',[('entry_low',float('nan')),('entry_high',float('inf')),('stop_reference',0),('entry_low',True),('entry_high','11'),('entry_low',15),('sources',['P999']),('quantity',1000),('conditions',['保证收益，立即下单'])])
def test_invalid_or_executable_price_entries_are_rejected(field,value):
    bad=copy.deepcopy(PLAN);bad[field]=value
    r=validate_price_scenarios({'trade_levels':bad,'forecasts':[]},{'P1'},CTX)
    assert r['trade_levels'] is None and r['rejected']>0

def test_unprovided_price_evidence_and_wrong_currency_are_rejected():
    assert validate_price_scenarios({'trade_levels':PLAN},{'D1'},CTX)['trade_levels'] is None
    assert validate_price_scenarios({'trade_levels':PLAN},{'P1'},CTX|{'currency':'USD'})['trade_levels'] is None

def test_forecast_ordering_and_missing_periods_are_not_fabricated():
    f=lambda scenario,low,high:dict(scenario=scenario,horizon_sessions=5,low=low,high=high,conditions=['观察条件'],sources=['P1'])
    assert not validate_price_scenarios({'forecasts':[f('bear',12,13),f('bull',10,11)]},{'P1'},CTX)['forecasts']
    assert len(validate_price_scenarios({'forecasts':[f('base',10,11)]},{'P1'},CTX)['forecasts'])==1

def test_chart_prices_require_a_known_positive_same_date_basis():
    assert map_level_to_chart(10,10,8,'qfq')==8
    assert map_level_to_chart(10,None,8,'raw')==10
    assert map_level_to_chart(10,None,8,'qfq') is None
    assert map_level_to_chart(True,10,8,'raw') is None

def test_price_request_uses_whole_p1_and_existing_manager_call_budget(tmp_path):
    repo=AssistantRepository(create_engine('sqlite:///'+str(tmp_path/'prices.db')))
    calls=[]
    def complete(messages,model):
        calls.append(messages)
        return {'claims':[{'text':'趋势需要持续核实','sources':['P1']}],'price_scenarios':{'trade_levels':PLAN,'forecasts':[]}}
    settings=AssistantSettings(mode='free',research_enabled=True,model='mock',daily_model_calls=6)
    engine=ResearchEngine(repo,complete)
    result=engine.run('600000',[dict(id='D1',content='资料'*3000)],'h1',settings,'2026-10-09',price_context=CTX)
    assert result['price_scenarios']['trade_levels']['sell_high']==13
    assert len(calls)==3 and repo.usage('free','2026-10-09')==3
    for messages in calls:
        sent=json.loads(messages[1]['content'])['evidence']
        assert json.loads(next(e['content'] for e in sent if e['id']=='P1'))==CTX
        assert len(json.dumps(sent,ensure_ascii=False).encode())<=2200
    assert engine.run('600000',[],'h1',settings,'2026-10-09')['engine']!=result['engine'] or len(calls)==6

def test_reading_scenarios_detects_changed_history_without_a_model_call(tmp_path):
    from tests.test_a_share_market_integration import setup_market
    svc,warmup=setup_market(tmp_path)
    context=svc.price_context('600000')
    assert context['price_basis']=='raw' and context['reference_price']==13.18
    svc.repo.append('free','research','test',dict(code='600000',price_scenarios=dict(context=context,trade_levels=PLAN,forecasts=[],status='ready',model='mock',generated_at='2026-10-09')))
    svc.settings=svc.settings.model_copy(update={'model':'mock'})
    assert svc.price_scenarios('600000')['status']=='ready'
    assert svc.price_scenarios('600001')['status']=='insufficient'
    cache=svc.market.repo.get_history('free','stock:600000','raw','1900-01-01',warmup['as_of'])
    changed=cache['items'];changed[-1]=changed[-1]|{'close':13.2,'high':13.3}
    svc.market.repo.replace_history('free','stock:600000','raw','fixture','b1',changed,warmup['as_of'])
    assert svc.price_scenarios('600000')['status']=='stale'
    assert svc.repo.usage('free','2026-10-09')==0
