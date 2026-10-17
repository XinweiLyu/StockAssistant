"""Operational regressions reproduced by the independent final review."""
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from src.schemas.a_share import AssistantSettings
from src.schemas.a_share_market import HistoryPage,MarketStock
from src.services.a_share_service import AssistantService
from src.repositories.a_share_repository import AssistantRepository
from sqlalchemy import create_engine


def service(tmp_path,mode='free'):
    s=AssistantService(AssistantRepository(create_engine('sqlite:///'+str(tmp_path/'review.db'))))
    s.settings=AssistantSettings(mode=mode,research_scope='all');s.market_jobs.set_profile(mode)
    return s

@pytest.mark.parametrize('hour,minute,expected',[(10,0,'snapshot'),(18,40,'daily')])
def test_first_full_market_calendar_drives_scheduled_sync_before_any_report(tmp_path,monkeypatch,hour,minute,expected):
    import src.services.a_share_service as module
    s=service(tmp_path);s.market.repo.set_state('free','calendar',{'dates':['2026-10-09','2026-10-12']})
    monkeypatch.setattr(module,'now_local',lambda:datetime(2026,10,12,hour,minute,tzinfo=ZoneInfo('Asia/Shanghai')))
    dispatched=[]
    s.sync_async=lambda kind:dispatched.append(kind) or True
    s.tick()
    assert dispatched==[expected]

def test_identity_conflict_is_persistent_and_keeps_original_evidence(tmp_path):
    s=service(tmp_path)
    value=dict(code='600000',name='验证样本',board='main',st=False,listed_date='2020-01-01',identity_verified=True,fetched_at='2026-10-09')
    original=MarketStock(**value,exchange='SSE',source='official-sh')
    conflicting=MarketStock(**value,exchange='SZSE',source='conflicting-feed')
    s.market._merge_catalog('free',[original],'v1')
    s.market._merge_catalog('free',[conflicting],'v2')
    s.market._merge_catalog('free',[conflicting],'v3')
    assert s.market.repo.stock('free','600000')['identity_verified'] is False
    evidence=s.market.repo.get_state('free','identity-conflict:600000')
    assert {e['source'] for e in evidence['observations']}=={'official-sh','conflicting-feed'}


def test_same_day_new_configuration_gets_new_history_tasks(tmp_path):
    s=service(tmp_path)
    s.market.repo.replace_catalog('free','v1',[dict(code='600000',name='样本',source='fixture',fetched_at='2026-10-09')])
    s.market.repo.set_state('free','calendar',dict(dates=['2026-10-09']))
    old=s.settings.model_dump()
    class NoIO: pass
    s.market.provider_for=lambda settings:NoIO()
    s.market.handle_task(dict(id='first',kind='warmup',profile='free',payload={'settings':old}))
    oldtasks=[t for t in s.market.repo.tasks('free') if t['kind']=='stock_history']
    s.settings=s.settings.model_copy(update={'free_fallback':False})
    for task in oldtasks:
        claimed=s.market.repo.claim('free',s.market.clock());s.market_jobs.handler(claimed);s.market.repo.finish(claimed['id'],claimed['claim_version'],'complete')
    s.market.handle_task(dict(id='second',kind='warmup',profile='free',payload={'settings':s.settings.model_dump()}))
    pending=[t for t in s.market.repo.tasks('free') if t['kind']=='stock_history' and t['state']=='pending']
    assert len(pending)==2
    assert not {t['id'] for t in pending}&{t['id'] for t in oldtasks}


def test_inflight_result_and_fallback_are_discarded_after_configuration_change(tmp_path):
    s=service(tmp_path)
    old=s.settings.model_dump()
    class ChangesConfiguration:
        def history(self,code,start,end,adjust,source=None):
            s.settings=s.settings.model_copy(update={'free_fallback':False})
            return HistoryPage(code=code,requested_start=start,requested_end=end,adjust=adjust,source='akshare/eastmoney',adjustment_basis='old',fetched_at=end,state='ready',items=[dict(date=end,open=10,high=11,low=9,close=10)])
    s.market.provider_for=lambda settings:ChangesConfiguration()
    s.market.handle_task(dict(id='old',key='old',priority=10,kind='stock_history',profile='free',payload=dict(settings=old,entity='stock:600000',code='600000',start='2026-10-09',end='2026-10-09',adjust='raw')))
    assert s.market.repo.get_history('free','stock:600000','raw','2026-10-09','2026-10-09') is None
    assert s.market.repo.get_state('free','health:stock_history')['status']=='discarded_configuration'


def test_recovered_claim_cannot_publish_its_old_history(tmp_path):
    s=service(tmp_path)
    payload=dict(settings=s.settings.model_dump(),entity='stock:600000',code='600000',start='2026-10-09',end='2026-10-09',adjust='raw')
    s.market_jobs.submit('free','claimed','stock_history',payload,10);task=s.market.repo.claim('free',s.market.clock())
    class Recovered:
        def history(self,code,start,end,adjust,source=None):
            s.market.repo.recover_running('free')
            return HistoryPage(code=code,requested_start=start,requested_end=end,adjust=adjust,source='fixture',adjustment_basis='old',fetched_at=end,state='ready',items=[dict(date=end,open=10,high=11,low=9,close=10)])
    s.market.provider_for=lambda settings:Recovered()
    s.market.handle_task(task)
    assert s.market.repo.get_history('free','stock:600000','raw','2026-10-09','2026-10-09') is None


def test_configured_paid_quotes_work_when_public_whole_market_source_fails(tmp_path):
    s=service(tmp_path,'tushare5000')
    s.settings=s.settings.model_copy(update={'snapshot_provider':'tushare','realtime_entitled':True,'free_fallback':False})
    class UnavailablePublic:
        def quotes(self):raise RuntimeError('public unavailable')
    s.market.provider_for=lambda settings:UnavailablePublic()
    def paid():
        s.repo.append('tushare5000','quotes','current',dict(quotes={'600000':dict(code='600000',price=10,source='tushare/rt_k',fetched_at='2026-10-12T10:00:00+08:00')}))
    s._quotes=paid
    s.market.handle_task(dict(kind='snapshot',profile='tushare5000',payload={'settings':s.settings.model_dump()}))
    assert s.market.repo.quotes('tushare5000')['600000']['price']==10
    assert s.market.repo.quotes('tushare5000')['600000']['source']=='tushare/rt_k'
