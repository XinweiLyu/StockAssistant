from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine


def test_quote_runs_between_history_requests_and_pause_keeps_it_running(tmp_path):
    from src.repositories.a_share_market_repository import MarketRepository
    from src.services.a_share_market_jobs import MarketJobs
    repo=MarketRepository(create_engine('sqlite:///' + str(tmp_path/'jobs.db')))
    seen=[]
    jobs=MarketJobs(repo,lambda t:seen.append(t['kind']),lambda:datetime(2026,10,12,tzinfo=timezone.utc),'free')
    jobs.submit('free','h1','stock_history',{},100)
    jobs.submit('free','q1','snapshot',{},0)
    jobs.set_paused('free',True)
    assert jobs.run_one() and seen==['snapshot']
    assert not jobs.run_one()
    jobs.set_paused('free',False)
    assert jobs.run_one() and seen==['snapshot','stock_history']


def test_three_failed_attempts_end_in_a_persistent_failure(tmp_path):
    from src.repositories.a_share_market_repository import MarketRepository
    from src.services.a_share_market_jobs import MarketJobs
    repo=MarketRepository(create_engine('sqlite:///' + str(tmp_path/'jobs.db')))
    clock=[datetime(2026,10,12,tzinfo=timezone.utc)]
    def failed(task):
        raise RuntimeError('upstream failed')
    jobs=MarketJobs(repo,failed,lambda:clock[0],'free')
    key=jobs.submit('free','failure','stock_history',{},100)
    for _ in range(3):
        assert jobs.run_one()
        clock[0]+=timedelta(minutes=16)
    assert repo.task(key)['state']=='failed'
    assert not jobs.run_one()


def test_switching_profile_does_not_claim_previous_profile(tmp_path):
    from src.repositories.a_share_market_repository import MarketRepository
    from src.services.a_share_market_jobs import MarketJobs
    repo=MarketRepository(create_engine('sqlite:///' + str(tmp_path/'jobs.db')))
    seen=[]
    jobs=MarketJobs(repo,lambda t:seen.append(t['profile']),lambda:datetime(2026,10,12,tzinfo=timezone.utc),'free')
    jobs.submit('free','a','snapshot',{},0)
    jobs.submit('tushare5000','a','snapshot',{},0)
    jobs.set_profile('tushare5000')
    assert jobs.run_one() and seen==['tushare5000']


def test_deferred_parent_does_not_use_up_retry_budget(tmp_path):
    from src.repositories.a_share_market_repository import MarketRepository
    from src.services.a_share_market_jobs import MarketJobs, Deferred
    repo=MarketRepository(create_engine('sqlite:///' + str(tmp_path/'jobs.db')))
    clock=[datetime(2026,10,12,tzinfo=timezone.utc)]
    def waiting(task):
        raise Deferred(30)
    jobs=MarketJobs(repo,waiting,lambda:clock[0],'free')
    key=jobs.submit('free','parent','report',{},110)
    for _ in range(5):
        assert jobs.run_one()
        clock[0]+=timedelta(minutes=1)
    assert repo.task(key)['state']=='pending' and repo.task(key)['attempts']==0


def test_shared_source_calls_cannot_overlap_across_provider_instances(monkeypatch):
    import time
    import threading
    from types import SimpleNamespace
    from concurrent.futures import ThreadPoolExecutor
    from data_provider.a_share import CapabilityProvider
    import data_provider.a_share as module
    lock=threading.Lock()
    counts=[0,0]
    def process(*args,**kwargs):
        with lock:
            counts[0]+=1
            counts[1]=max(counts)
        time.sleep(.04)
        with lock:
            counts[0]-=1
        return SimpleNamespace(stdout='[]')
    monkeypatch.setattr(module.subprocess,'run',process)
    with ThreadPoolExecutor(2) as executor:
        list(executor.map(lambda _:CapabilityProvider().call('stock_info_a_code_name'),range(2)))
    assert counts[1]==1

def test_bad_symbol_schema_does_not_cool_down_other_symbols(monkeypatch):
    import json,subprocess
    from types import SimpleNamespace
    from data_provider.a_share import CapabilityProvider
    def process(*args,**kwargs):
        params=json.loads(kwargs['input'])['params']
        if params['symbol']=='bj920002':
            raise subprocess.CalledProcessError(1,args[0],output=json.dumps({'error':"'day'",'error_type':'KeyError'}))
        return SimpleNamespace(stdout='[{"date":"2026-10-09","close":10}]')
    monkeypatch.setattr(subprocess,'run',process)
    p=CapabilityProvider()
    import pytest
    with pytest.raises(RuntimeError):p.call('stock_zh_a_hist_tx',{'symbol':'bj920002'})
    assert p.call('stock_zh_a_hist_tx',{'symbol':'sh600000'})[0]['close']==10
