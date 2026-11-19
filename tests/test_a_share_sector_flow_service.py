from datetime import datetime,timezone
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from src.schemas.a_share import AssistantSettings
from src.repositories.a_share_market_repository import MarketRepository
from src.services.a_share_market_service import MarketService
from src.services.a_share_market_jobs import MarketJobs
from data_provider.a_share_sector_flow import normalize_history

BOARD=dict(sector_id='em:industry:BK0478',kind='industry',classification='eastmoney-industry',code='BK0478',name='有色金属',source='fixture',fetched_at='2026-11-17')
@pytest.fixture
def flow(tmp_path,monkeypatch):
 from src.services.a_share_sector_flow_service import SectorFlowService
 repo=MarketRepository(create_engine('sqlite:///'+str(tmp_path/'flow.db')))
 repo.put_sectors('free',[BOARD])
 assistant=SimpleNamespace(settings=AssistantSettings(mode='free'))
 now=lambda:datetime(2026,11,17,2,tzinfo=timezone.utc)
 jobs=MarketJobs(repo,lambda t:None,now,'free')
 market=MarketService(assistant,repo,jobs,clock=now)
 service=SectorFlowService(market)
 service.sessions=lambda:['2026-11-10','2026-11-11','2026-11-12','2026-11-13','2026-11-16','2026-11-17']
 return service

def history(flow,days):
 rows=normalize_history([d+','+','.join(['0']*10+['100','1']) for d in days],BOARD,'2026-11-17T02:00:00+00:00')
 flow.repo.save_daily('free',rows)

def test_completed_window_keeps_missing_not_zero(flow):
 history(flow,['2026-11-10','2026-11-11','2026-11-13','2026-11-16'])
 value=flow.get(BOARD['sector_id'],5)
 assert len(value['points'])==5
 assert value['points'][2]['values']['main'] is None
 assert value['points'][0]['values']['main']==0
 assert value['summary']['main_net'] is None and not value['complete']
 history(flow,['2026-11-12'])
 assert flow.get(BOARD['sector_id'],5)['summary']['main_net']==0

def test_global_rank_shared_bucket_and_nontrading_gate(flow):
 first=flow.rankings('industry');second=flow.rankings('industry')
 assert first['task_id']==second['task_id']
 flow.market.clock=lambda:datetime(2026,11,17,4,tzinfo=timezone.utc) # lunch
 flow.market.repo.set_state('free','sector-flow:rank:concept',dict(items=[],observed_at='2026-11-17T03:29:00+00:00'))
 assert flow.rankings('concept')['task_id'] is None

def test_invalid_board_and_period_rejected(flow):
 with pytest.raises(ValueError):flow.get('yahoo:technology',5)
 with pytest.raises(ValueError):flow.get(BOARD['sector_id'],7)

def test_failed_source_keeps_cache_and_profile_captured(flow):
 from src.services.a_share_market_service import configuration_stamp
 settings=flow.market.assistant.settings.model_dump()
 task=dict(profile='free',kind='sector_flow_history',payload=dict(settings=settings,sector=BOARD),id='fake',claim_version=0)
 class Provider:
  def call(self,*args):
   flow.market.assistant.settings=AssistantSettings(mode='tushare5000')
   return ['2026-11-16,'+','.join(['10']*10+['100','1'])]
 flow.market.provider_for=lambda settings:SimpleNamespace(provider=Provider())
 flow.handle_task(task)
 assert flow.repo.read_daily('free',BOARD['sector_id'],'2026-11-16','2026-11-16')
 assert not flow.repo.read_daily('tushare5000',BOARD['sector_id'],'2026-11-16','2026-11-16')
 flow.market.assistant.settings=AssistantSettings(mode='free')
 class Failed:
  def call(self,*args):raise RuntimeError('upstream unavailable')
 flow.market.provider_for=lambda settings:SimpleNamespace(provider=Failed())
 with pytest.raises(RuntimeError):flow.handle_task(task)
 assert flow.get(BOARD['sector_id'],5)['health']['history']['status']=='failed'
 assert flow.repo.read_daily('free',BOARD['sector_id'],'2026-11-16','2026-11-16')

def test_research_only_cached_complete_observed_before_cutoff(flow):
 history(flow,['2026-11-10','2026-11-11','2026-11-12','2026-11-13','2026-11-16'])
 assert flow.research_fact('000807',BOARD,'2026-11-16T20:00:00+00:00','2026-11-16') is None
 fact=flow.research_fact('000807',BOARD,'2026-11-17T03:00:00+00:00','2026-11-16')
 assert fact['category']=='market' and fact['values']['main_net_5d']==0
 assert fact['values']['not_institutional_holdings']
 assert flow.market.repo.progress('free')['counts']=={} # no source or model queue

def test_no_cross_profile_publication_on_same_profile_config_change(flow):
 task=dict(profile='free',kind='sector_flow_history',payload=dict(settings=flow.market.assistant.settings.model_dump(),sector=BOARD),id='fake',claim_version=0)
 class Provider:
  def call(self,*args):
   flow.market.assistant.settings.free_fallback=False
   return ['2026-11-16,'+','.join(['10']*10+['100','1'])]
 flow.market.provider_for=lambda settings:SimpleNamespace(provider=Provider())
 with pytest.raises(RuntimeError):flow.handle_task(task)
 assert not flow.repo.read_daily('free',BOARD['sector_id'],'2026-11-16','2026-11-16')

def test_weekend_and_lunch_cached_rank_do_not_fetch_but_manual_can(flow):
 flow.market.clock=lambda:datetime(2026,11,21,2,tzinfo=timezone.utc)
 flow.market.repo.set_state('free','sector-flow:rank:industry',dict(items=[],observed_at='2026-11-20T07:00:00Z'))
 assert flow.rankings('industry')['task_id'] is None
 assert flow.rankings('industry',True)['task_id']

def test_closed_day_history_is_shared_across_refresh_buckets_and_trends_need_contiguous_days(flow):
 history(flow,['2026-11-10','2026-11-11','2026-11-12','2026-11-13','2026-11-16'])
 first=flow.get(BOARD['sector_id'],5)
 assert first['summary']['net_5d']==0 and first['summary']['net_20d'] is None
 assert first['summary']['consecutive_positive']==0
 task_id=next(i for i in first['task_ids'] if flow.market.repo.task(i)['kind']=='sector_flow_history')
 from sqlalchemy import update
 from src.repositories.a_share_market_repository import TASKS
 with flow.market.repo.engine.begin() as c:c.execute(update(TASKS).where(TASKS.c.id==task_id).values(state='complete'))
 flow.market.clock=lambda:datetime(2026,11,17,2,10,tzinfo=timezone.utc)
 value=flow.get(BOARD['sector_id'],20)
 assert not [i for i in value['task_ids'] if flow.market.repo.task(i)['kind']=='sector_flow_history']

def test_failed_closing_refresh_does_not_promote_morning_data_or_research(flow):
 history(flow,['2026-11-11','2026-11-12','2026-11-13','2026-11-16','2026-11-17'])
 flow.market.clock=lambda:datetime(2026,11,17,7,20,tzinfo=timezone.utc)
 task=dict(profile='free',kind='sector_flow_history',payload=dict(settings=flow.market.assistant.settings.model_dump(),sector=BOARD),id='fake',claim_version=0)
 class Failed:
  def call(self,*args):raise RuntimeError('unavailable')
 flow.market.provider_for=lambda settings:SimpleNamespace(provider=Failed())
 with pytest.raises(RuntimeError):flow.handle_task(task)
 assert not flow.get(BOARD['sector_id'],5)['complete']
 assert flow.research_fact('000807',BOARD,'2026-11-17T07:20:00Z','2026-11-17') is None
 rows=normalize_history(['2026-11-17,'+','.join(['10']*10+['100','1'])],BOARD,'2026-11-17T07:11:00Z')
 flow.repo.save_daily('free',rows)
 assert flow.get(BOARD['sector_id'],5)['complete']
 assert flow.research_fact('000807',BOARD,'2026-11-17T07:20:00Z','2026-11-17')

def test_partial_source_failure_does_not_stop_polling_other_pending_data(flow):
 flow.market.repo.set_state('free','sector-flow:health:rank:industry',dict(status='failed',error='offline'))
 assert flow.get(BOARD['sector_id'],20)['poll_pending']

def test_selected_history_is_ahead_of_background_warmup(flow):
 v=flow.get(BOARD['sector_id'],20)
 t=next(flow.market.repo.task(i) for i in v['task_ids'] if flow.market.repo.task(i)['kind']=='sector_flow_history')
 assert t['priority']==1
