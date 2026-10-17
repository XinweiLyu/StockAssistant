from datetime import date, datetime, timedelta, timezone
from sqlalchemy import create_engine
from src.repositories.a_share_repository import AssistantRepository
from src.services.a_share_service import AssistantService
from src.schemas.a_share import AssistantSettings
from tests.test_a_share_rules import bars


def setup_market(tmp_path,count=35,unverified=False):
    svc=AssistantService(AssistantRepository(create_engine('sqlite:///' + str(tmp_path/'assistant.db'))))
    svc.settings=AssistantSettings(mode='free',research_scope='all',pool_size=30)
    svc.market_jobs.set_profile('free')
    history=bars()
    end=history[-1]['date']
    future=(date.fromisoformat(end)+timedelta(days=1)).isoformat()
    svc.market.clock=lambda:datetime.fromisoformat(future).replace(hour=2,tzinfo=timezone.utc)
    svc.market.repo.set_state('free','calendar',dict(dates=[r['date'] for r in history]+[future]))
    stocks=[dict(code=f'{600000+i}',name='离线样本'+str(i),exchange='SSE',board='main',st=False,
                 identity_verified=not(unverified and i==count-1),listed_date='2020-01-01',source='fixture',fetched_at=end) for i in range(count)]
    svc.market.repo.replace_catalog('free','v1',stocks)
    prices=[dict(r,open=r['close']) for r in history]
    prices=[{k:v for k,v in r.items() if k!='adjusted_close'} for r in prices]
    for s in stocks:
        for adjust in ('raw','qfq'):
            svc.market.repo.replace_history('free','stock:'+s['code'],adjust,'fixture','b1',prices,end)
    svc.market.repo.replace_history('free','benchmark:000300','raw','fixture','index',prices,end)
    warmup=dict(codes=[s['code'] for s in stocks],as_of=end,start=history[0]['date'],catalog_version='v1',settings=svc.settings.model_dump())
    svc.market.repo.set_state('free','warmup',warmup)
    return svc,warmup


def test_all_market_report_has_more_than_the_old_pool_and_no_duplicate_full_history(tmp_path):
    svc,warmup=setup_market(tmp_path)
    svc.build_market_report('free',warmup)
    report=svc.repo.latest('free','report')
    assert report['sample_size']==35 and report['coverage']['catalog_total']==35
    assert report['coverage']['state']=='complete'
    dataset=svc.repo.latest('free','dataset')
    assert not dataset.get('stocks')
    assert len(svc.repo.records('free','stock_data'))==0
    assert svc.stock_data('600034')['bars'][-1]['close']==13.18


def test_unknown_identity_is_missing_coverage_not_a_normal_exclusion(tmp_path):
    svc,warmup=setup_market(tmp_path,unverified=True)
    svc.build_market_report('free',warmup)
    value=svc.repo.latest('free','report')['coverage']
    assert value['unverified']==1 and value['excluded']==0 and value['valid']==34
    assert value['state']=='complete_with_gaps'


def test_reading_demo_market_keeps_original_candidates_and_history(tmp_path):
    svc=AssistantService(AssistantRepository(create_engine('sqlite:///' + str(tmp_path/'demo.db'))))
    svc.sync('daily')
    old=svc.repo.latest('demo','report')['input_hash']
    svc.market.ensure_demo()
    assert svc.repo.latest('demo','report')['input_hash']==old
    assert svc.dashboard()['portfolio']['demo']
    assert len(svc.market.repo.catalog_codes('demo'))==40


def test_full_market_snapshot_does_not_mix_a_previous_mode_into_active_journal(tmp_path):
    svc,warmup=setup_market(tmp_path)
    svc.market_quotes_updated('demo',{'DEMO001':dict(price=10)})
    assert svc.repo.latest('free','quotes') is None


def test_percentile_does_not_do_quadratic_comparisons():
    from src.services.a_share_rules import percentile
    class Counted:
        comparisons=0
        def __init__(self,value): self.value=value
        def __lt__(self,other):
            type(self).comparisons+=1
            return self.value<other.value
        def __eq__(self,other):
            type(self).comparisons+=1
            return self.value==other.value
    value=percentile([Counted(i%23) for i in range(1000)])
    assert len(value)==1000 and Counted.comparisons<50000


def test_ties_keep_the_old_rank_meaning():
    from src.services.a_share_rules import percentile
    assert percentile([3,1,3,2])==[5/6,0,5/6,1/3]


def test_non_candidate_can_request_manual_research_without_becoming_a_candidate(tmp_path,monkeypatch):
    from src.services.a_share_research import ResearchEngine
    import src.services.a_share_service as module
    svc,warmup=setup_market(tmp_path)
    svc.settings=svc.settings.model_copy(update={'research_enabled':True,'model':'mock'})
    output=[]
    monkeypatch.setattr(ResearchEngine,'run',lambda self,code,evidence,*args,**kwargs:output.append((code,evidence)))
    class Immediate:
        def __init__(self,target,**kwargs):self.target=target
        def start(self):self.target()
    monkeypatch.setattr(module.threading,'Thread',Immediate)
    svc.research_async('600034')
    assert output[0][0]=='600034' and '手动选择' in output[0][1][0]['content']
    assert svc.repo.latest('free','report') is None


def test_warmup_cannot_shrink_a_user_cached_longer_history(tmp_path):
    from src.schemas.a_share_market import HistoryPage
    svc,warmup=setup_market(tmp_path)
    requests=[]
    class Source:
        def history(self,code,start,end,adjust,source=None):
            requests.append(start)
            return HistoryPage(code=code,requested_start=start,requested_end=end,adjust=adjust,source='fixture',adjustment_basis='b1',
                fetched_at=end,state='ready',items=[dict(date='2025-01-01',open=10,high=11,low=9,close=10)])
    svc.market.provider_for=lambda settings:Source()
    svc.market.repo.replace_history('free','stock:600000','raw','fixture','b1',[
        dict(date='2025-01-01',open=10,high=11,low=9,close=10)],warmup['as_of'],requested_start='2023-01-01',requested_end=warmup['as_of'])
    svc.market.handle_task(dict(id='manual',key='test',kind='stock_history',priority=100,profile='free',payload=dict(
        settings=svc.settings.model_dump(),entity='stock:600000',code='600000',start='2025-01-01',end=warmup['as_of'],adjust='raw')))
    assert requests==['2023-01-01']


def test_old_quote_job_after_same_profile_permission_change_is_discarded(tmp_path):
    from src.schemas.a_share_market import MarketQuote
    svc,warmup=setup_market(tmp_path)
    old=svc.settings.model_dump()
    class Source:
        def quotes(self):
            return [MarketQuote(code='600000',price=10,source='fixture',fetched_at='2025-06-20')]
    svc.market.provider_for=lambda settings:Source()
    svc.settings=svc.settings.model_copy(update={'snapshot_provider':'tushare','realtime_entitled':True})
    svc.market.handle_task(dict(kind='snapshot',profile='free',payload={'settings':old}))
    assert not svc.market.repo.quotes('free')

def test_old_negative_adjusted_prices_do_not_exclude_a_complete_recent_rule_window(tmp_path):
    svc,warmup=setup_market(tmp_path)
    q=svc.market.repo.get_history('free','stock:600000','qfq','1900-01-01',warmup['as_of'])
    q['items'][0].update(open=-1,close=-1,high=-.8,low=-1.2)
    svc.market.repo.replace_history('free','stock:600000','qfq','fixture','b1',q['items'],warmup['as_of'])
    svc.build_market_report('free',warmup)
    assert svc.repo.latest('free','report')['sample_size']==35

def test_missing_listing_date_and_market_baseline_remain_visible_gaps(tmp_path):
    svc,warmup=setup_market(tmp_path)
    values=[svc.market.repo.stock('free',c) for c in warmup['codes']]
    values[0]['listed_date']=None
    svc.market.repo.replace_catalog('free','v2',values)
    from src.repositories.a_share_market_repository import BARS,RANGES
    from sqlalchemy import delete
    with svc.market.repo.engine.begin() as conn:
        conn.execute(delete(BARS).where(BARS.c.entity=='benchmark:000300'))
        conn.execute(delete(RANGES).where(RANGES.c.entity=='benchmark:000300'))
    svc.build_market_report('free',warmup)
    c=svc.market.coverage()
    assert c['unverified']==1 and c['state']=='complete_with_gaps'
    assert c['market_baseline_ready'] is False

def test_mismatched_history_sources_queue_one_consistent_pair_before_research(tmp_path):
    svc,warmup=setup_market(tmp_path)
    raw=svc.market.repo.get_history('free','stock:600000','raw','1900-01-01',warmup['as_of'])
    svc.market.repo.replace_history('free','stock:600000','raw','akshare/tencent','b1',raw['items'],warmup['as_of'])
    svc.market.repo.replace_history('free','stock:600000','qfq','akshare/eastmoney','b1',raw['items'],warmup['as_of'])
    r=svc.research_async('600000',include_price_scenarios=True)
    tasks=svc.market.repo.tasks('free')
    assert r['state']=='preparing'
    assert any(t['payload'].get('forced_source')=='akshare/tencent' for t in tasks)
    assert svc.repo.usage('free',warmup['as_of'])==0

def test_demo_history_and_benchmark_cannot_enqueue_real_market_sources(tmp_path):
    from sqlalchemy import delete
    from src.repositories.a_share_market_repository import BARS,RANGES
    svc=AssistantService(AssistantRepository(create_engine('sqlite:///'+str(tmp_path/'demo-only.db'))))
    svc.sync('daily');svc.market.ensure_demo()
    with svc.market.repo.engine.begin() as conn:
        conn.execute(delete(BARS).where(BARS.c.entity=='benchmark:000300'))
        conn.execute(delete(RANGES).where(RANGES.c.entity=='benchmark:000300'))
    result=svc.market.benchmark_history('2025-10-01','2026-10-12')
    assert result.demo and result.source in (None,'synthetic')
    assert not svc.market.repo.tasks('demo')
