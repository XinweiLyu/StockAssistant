from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from src.schemas.a_share import AssistantSettings
from src.schemas.a_share_market import MarketStock, CatalogQuery, SectorQuery, HistoryPage
from src.repositories.a_share_market_repository import MarketRepository
from src.services.a_share_market_jobs import MarketJobs


@pytest.fixture
def market_service(tmp_path):
    from src.services.a_share_market_service import MarketService
    repo=MarketRepository(create_engine('sqlite:///' + str(tmp_path/'market.db')))
    stamp='2026-10-12T10:00:00+08:00'
    repo.replace_catalog('free','v1',[MarketStock(code=c,name=c,exchange=e,board=b,st=False,
        listed_date='2020-01-01',identity_verified=True,source='fixture',fetched_at=stamp)
        for c,e,b in [('000001','SZSE','main'),('600001','SSE','main'),('300001','SZSE','growth')]])
    repo.put_sectors('free',[dict(sector_id='em:'+k+':'+code,kind=k,classification='eastmoney-'+k,name=code,code=code,source='akshare/eastmoney',fetched_at=stamp,change=.025)
        for k,code in [('industry','BK1'),('concept','BK2')]])
    repo.replace_members('free','em:industry:BK1','v1',['000001','600001'])
    repo.replace_members('free','em:concept:BK2','v1',['000001','300001'])
    repo.set_state('free','calendar',dict(dates=['2026-10-08','2026-10-09','2026-10-12']))
    assistant=SimpleNamespace(settings=AssistantSettings(mode='free'),portfolio=lambda:{'positions':[]})
    jobs=MarketJobs(repo,lambda t:None,lambda:datetime(2026,10,12,2,tzinfo=timezone.utc),'free')
    svc=MarketService(assistant,repo,jobs,clock=jobs.clock)
    jobs.handler=svc.handle_task
    return svc


def test_industry_and_concept_filters_intersect(market_service):
    result=market_service.catalog(CatalogQuery(industry_id='em:industry:BK1',concept_id='em:concept:BK2'))
    assert [s['code'] for s in result['items']]==['000001']


def test_non_candidate_history_is_queued_and_cache_can_be_short(market_service):
    svc=market_service
    page=svc.history('300001','2025-10-09','2026-10-09','raw')
    assert page.state=='pending' and page.task_id
    svc.repo.replace_history('free','stock:300001','raw','fixture','basis',[
        dict(date='2026-10-09',open=10,high=11,low=9,close=10)],'2026-10-12',
        requested_start='2025-10-09',requested_end='2026-10-09')
    assert svc.history('300001','2025-10-09','2026-10-09','raw').items[0].close==10


def test_unknown_stock_cannot_schedule_a_fetch(market_service):
    with pytest.raises(ValueError):
        market_service.history('999999','2025-10-09','2026-10-09','raw')
    assert market_service.repo.progress('free')['counts']=={}


def test_intraday_date_is_not_appended_as_a_completed_candle(market_service):
    value=market_service.history('000001','2025-10-12','2026-10-12','raw')
    assert value.requested_end=='2026-10-09'
    assert any('完整日线' in s for s in value.limitations)


def test_current_sector_change_and_sample_breadth_are_separate(market_service):
    svc=market_service
    svc.repo.put_quotes('free','batch1',[dict(code='000001',change=-.01),dict(code='600001',change=None)])
    value=svc.sectors(SectorQuery())['items'][0]
    assert value['change']==.025
    assert value['member_breadth']['down']==1 and value['member_breadth']['unknown']==1
    assert value['member_breadth']['total']==2


def test_missing_history_return_is_unknown_not_zero(market_service):
    result=market_service.sectors(SectorQuery(period=20))
    assert result['items'][0]['change'] is None


def test_cached_history_does_not_issue_model_or_upstream_calls(market_service):
    svc=market_service
    svc.repo.replace_history('free','stock:000001','raw','fixture','basis',[
        dict(date='2026-10-09',open=10,high=11,low=9,close=10)],'2026-10-12',requested_start='2025-10-09',requested_end='2026-10-09')
    assert svc.history('000001','2026-10-09','2026-10-09','raw').state=='ready'
    assert svc.repo.progress('free')['counts']=={}


def test_history_handler_uses_task_profile_even_after_mode_switch(market_service):
    svc=market_service
    page=svc.history('000001','2025-10-09','2026-10-09','raw')
    class Fixed:
        def history(self,code,start,end,adjust,source=None):
            return HistoryPage(code=code,requested_start=start,requested_end=end,adjust=adjust,
                source='fixture',adjustment_basis='basis',state='ready',fetched_at='2026-10-12',
                items=[dict(date='2026-10-09',open=10,high=11,low=9,close=10)])
    svc.provider_for=lambda settings:Fixed()
    svc.assistant.settings=AssistantSettings(mode='tushare5000')
    svc.handle_task(svc.repo.task(page.task_id))
    assert svc.repo.get_history('free','stock:000001','raw','2025-10-09','2026-10-09')
    assert svc.repo.get_history('tushare5000','stock:000001','raw','2025-10-09','2026-10-09') is None


def test_truncated_year_of_history_cannot_be_marked_complete(market_service):
    svc=market_service
    svc.repo.replace_history('free','stock:000001','raw','fixture','basis',[
        dict(date='2026-10-09',open=10,high=11,low=9,close=10)],'2026-10-12',requested_start='2025-10-09',requested_end='2026-10-09')
    assert svc.history('000001','2025-10-09','2026-10-09','raw').state=='partial'

def test_explicit_refresh_stays_pending_even_when_old_cache_covers(market_service):
    svc=market_service
    svc.repo.replace_history('free','stock:000001','raw','fixture','basis',[dict(date='2026-10-09',open=10,high=11,low=9,close=10)],'2026-10-09')
    refreshed=svc.history('000001','2026-10-09','2026-10-09','raw',refresh=True)
    assert refreshed.state=='pending'
    assert svc.history('000001','2026-10-09','2026-10-09','raw').state=='pending'

def test_fallback_keeps_pointer_for_original_request_when_fetching_wider_cache(market_service):
    svc=market_service
    svc.repo.replace_history('free','stock:000001','raw','fixture','basis',[dict(date='2026-10-08',open=10,high=11,low=9,close=10)],'2026-10-08',requested_start='2025-01-01',requested_end='2026-10-08')
    page=svc.history('000001','2026-10-09','2026-10-09','raw')
    class Fails:
        def history(self,*args,**kwargs): raise RuntimeError('offline')
    svc.provider_for=lambda settings:Fails()
    task=svc.repo.task(page.task_id);svc.handle_task(task)
    pointer=svc.repo.get_state('free','history:stock:000001:raw:2026-10-09:2026-10-09')
    assert pointer['id']!=page.task_id


def test_chart_history_carries_only_prior_same_generation_indicator_warmup(market_service):
    from datetime import date, timedelta
    svc=market_service
    rows=[dict(date=(date(2025,10,12)+timedelta(days=i)).isoformat(),
               open=10,high=11,low=9,close=10) for i in range(363)]
    svc.repo.replace_history('free','stock:000001','qfq','fixture','basis',rows,'2026-10-12',
                             requested_start=rows[0]['date'],requested_end='2026-10-09')
    page=svc.history('000001','2026-10-08','2026-10-09','qfq')
    assert [b.date for b in page.items]==['2026-10-08','2026-10-09']
    assert len(page.warmup_items)==249
    assert all(b.date<'2026-10-08' for b in page.warmup_items)
    assert svc.repo.progress('free')['counts']=={}
    original=svc.repo.get_history
    def changed(profile,entity,adjust,start,end):
        value=original(profile,entity,adjust,start,end)
        return value | {'adjustment_basis':'different-basis'} if end<'2026-10-08' else value
    svc.repo.get_history=changed
    assert svc.history('000001','2026-10-08','2026-10-09','qfq').warmup_items==[]
    def invalid(profile,entity,adjust,start,end):
        value=original(profile,entity,adjust,start,end)
        if end<'2026-10-08':
            value['items'][-1]['close']=float('inf')
        return value
    svc.repo.get_history=invalid
    rejected=svc.history('000001','2026-10-08','2026-10-09','qfq')
    assert rejected.warmup_items==[] and len(rejected.items)==2
    assert any('指标预热' in s for s in rejected.limitations)


def test_member_failure_is_visible_and_manual_retry_requeues_real_work(market_service):
    svc = market_service
    svc.repo.put_sectors('free', [dict(sector_id='em:industry:BK1586', kind='industry',
        classification='eastmoney-industry', name='软饮料', code='BK1586',
        source='akshare/eastmoney', fetched_at='2026-10-12')])
    first = svc.members('em:industry:BK1586', CatalogQuery())
    assert first['membership']['state'] == 'pending'
    task = svc.repo.claim('free', svc.clock())
    svc.repo.finish(task['id'], task['claim_version'], 'failed', error='source unavailable')
    failed = svc.members('em:industry:BK1586', CatalogQuery())
    assert failed['membership']['state'] == 'failed'
    assert failed['membership']['error']
    retried = svc.members('em:industry:BK1586', CatalogQuery(), refresh=True)
    assert retried['membership']['state'] == 'pending'
    new_task = svc.repo.claim('free', svc.clock())
    assert new_task and new_task['id'] != task['id']
    # Clicking again during an active fetch cannot duplicate the network work.
    svc.members('em:industry:BK1586', CatalogQuery(), refresh=True)
    assert svc.repo.claim('free', svc.clock()) is None
    class Public:
        members_source = 'eastmoney/F10'
        def members(self, sector): return ['000001', '300001']
    svc.provider_for = lambda settings: Public()
    svc.handle_task(new_task)
    svc.repo.finish(new_task['id'], new_task['claim_version'], 'complete')
    ready = svc.members('em:industry:BK1586', CatalogQuery(concept_id='em:concept:BK2'))
    assert ready['membership']['state'] == 'ready'
    assert ready['membership']['source'] == 'eastmoney/F10'
    assert {s['code'] for s in ready['items']} == {'000001', '300001'}


def test_refresh_failure_preserves_usable_members_and_provenance(market_service):
    svc = market_service
    svc.members('em:industry:BK1', CatalogQuery(), refresh=True)
    task = svc.repo.claim('free', svc.clock())
    svc.repo.finish(task['id'], task['claim_version'], 'pending', error='offline', next_attempt='2026-10-12T02:15:00+00:00')
    page = svc.members('em:industry:BK1', CatalogQuery())
    assert page['membership']['state'] == 'ready'
    assert page['membership']['error']
    assert page['membership']['retry_at'] == '2026-10-12T02:15:00+00:00'
    assert len(page['items']) == 2
    svc.members('em:industry:BK1', CatalogQuery(), refresh=True)
    resumed = svc.repo.claim('free', svc.clock())
    assert resumed and resumed['id'] == task['id']


def test_stale_members_refresh_in_background_without_emptying_filter(market_service):
    svc=market_service
    svc.repo.set_state('free','members:em:industry:BK1',dict(version='v1',fetched_at='2026-10-01T00:00:00+00:00',source='akshare/eastmoney'))
    page=svc.members('em:industry:BK1',CatalogQuery())
    assert page['membership']['state']=='ready' and page['membership']['refreshing']
    assert len(page['items'])==2
    assert svc.members('em:industry:BK1',CatalogQuery())['membership']['task_id']==page['membership']['task_id']
