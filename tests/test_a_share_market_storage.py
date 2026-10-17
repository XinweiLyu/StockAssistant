from datetime import datetime, timezone
from sqlalchemy import create_engine
import pytest


@pytest.fixture
def repo(tmp_path):
    from src.repositories.a_share_market_repository import MarketRepository
    return MarketRepository(create_engine('sqlite:///' + str(tmp_path/'market.db')))


def stock(code, name=None):
    return dict(code=code,name=name or code,exchange='SZSE',board='main',st=False,
                source='fixture',identity_verified=True,fetched_at='2026-10-09T15:00:00+08:00')


def test_filters_intersect_and_null_prices_sort_last(repo):
    from src.schemas.a_share_market import CatalogQuery
    repo.replace_catalog('free','v1',[stock('000001'),stock('000002'),stock('000003')])
    repo.replace_members('free','em:industry:BK1','v1',['000001','000002'])
    repo.replace_members('free','em:concept:BK2','v1',['000002','000003'])
    repo.put_quotes('free','b1',[dict(code='000002',change=-.05,amount=100)])
    result=repo.list_stocks('free',CatalogQuery(industry_id='em:industry:BK1',concept_id='em:concept:BK2'))
    assert result['total']==1 and result['items'][0]['code']=='000002'
    assert repo.list_stocks('free',CatalogQuery(direction='asc'))['items'][0]['code']=='000002'
    assert repo.list_stocks('demo',CatalogQuery())['total']==0


def test_same_named_classifications_never_merge_and_old_version_survives(repo):
    repo.replace_members('free','em:industry:BK1','v1',['000001'])
    repo.replace_members('free','ths:industry:BK1','v1',['600001'])
    repo.replace_members('free','em:industry:BK1','v2',['000002'])
    assert repo.members('free','em:industry:BK1')['codes']==['000002']
    assert repo.members('free','em:industry:BK1',version='v1')['codes']==['000001']
    assert repo.members('free','ths:industry:BK1')['codes']==['600001']


def test_history_basis_is_replaced_atomically_and_modes_are_separate(repo):
    bars=[dict(date='2026-10-08',open=10,high=11,low=9,close=10,volume=100,amount=1000)]
    repo.replace_history('free','stock:000001','qfq','fixture','v1',bars,'2026-10-09')
    repo.replace_history('free','stock:000001','qfq','fixture','v2',[bars[0]|dict(close=9)],'2026-10-10')
    value=repo.get_history('free','stock:000001','qfq','2026-10-01','2026-10-09')
    assert value['items'][0]['close']==9 and value['adjustment_basis']=='v2'
    assert repo.get_history('free','stock:000001','raw','2026-10-01','2026-10-09') is None
    assert repo.get_history('tushare5000','stock:000001','qfq','2026-10-01','2026-10-09') is None


def test_invalid_history_keeps_last_complete_cache(repo):
    bars=[dict(date='2026-10-08',open=10,high=11,low=9,close=10)]
    repo.replace_history('free','stock:000001','raw','fixture','v1',bars,'2026-10-09')
    with pytest.raises(ValueError):
        repo.replace_history('free','stock:000001','raw','fixture','v2',[bars[0]|dict(high=1)],'2026-10-10')
    assert repo.get_history('free','stock:000001','raw','2026-10-01','2026-10-09')['items'][0]['high']==11


def test_tasks_deduplicate_prioritize_pause_and_recover(repo):
    now=datetime(2026,10,12,tzinfo=timezone.utc)
    low=repo.enqueue('free','low','stock_history',{},100)
    assert low==repo.enqueue('free','low','stock_history',{},100)
    high=repo.enqueue('free','high','snapshot',{},0)
    repo.pause('free',True)
    task=repo.claim('free',now)
    assert task['id']==high
    assert repo.claim('free',now) is None
    repo.recover_running('free')
    newer=repo.claim('free',now)
    assert newer['claim_version']>task['claim_version']
    assert not repo.finish(high,task['claim_version'],'complete')
    assert repo.finish(high,newer['claim_version'],'complete')
    repo.pause('free',False)
    assert repo.claim('free',now)['id']==low


def test_empty_catalog_cannot_erase_a_valid_catalog(repo):
    from src.schemas.a_share_market import CatalogQuery
    repo.replace_catalog('free','v1',[stock('000001')])
    with pytest.raises(ValueError):
        repo.replace_catalog('free','bad',[])
    assert repo.list_stocks('free',CatalogQuery())['total']==1


def test_six_thousand_stocks_have_stable_pagination(repo):
    from src.schemas.a_share_market import CatalogQuery
    repo.replace_catalog('free','v1',[stock(f'{i:06d}') for i in range(6000)])
    value=repo.list_stocks('free',CatalogQuery(sort='code',direction='asc',page=60,page_size=100))
    assert value['total']==6000 and len(value['items'])==100
    assert value['items'][0]['code']=='005900'


def test_unknown_industry_bucket_preserves_unmapped_stocks(repo):
    from src.schemas.a_share_market import CatalogQuery
    repo.replace_catalog('free','v1',[stock('000001'),stock('000002')])
    repo.put_sectors('free',[dict(sector_id='em:industry:BK1',kind='industry',classification='eastmoney-industry',name='样本',code='BK1',source='fixture',fetched_at='2026-10-09')])
    repo.replace_members('free','em:industry:BK1','v1',['000001'])
    result=repo.list_stocks('free',CatalogQuery(industry_id='__unknown__'))
    assert [s['code'] for s in result['items']]==['000002']
    known=repo.list_stocks('free',CatalogQuery(q='000001'))['items'][0]
    assert known['industries'][0]['sector_id']=='em:industry:BK1'


def test_simultaneous_enqueue_cannot_duplicate_a_request(repo):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import event
    import threading
    barrier=threading.Barrier(2)
    def align_reads(conn,cursor,statement,parameters,context,executemany):
        if statement.startswith('SELECT') and 'a_share_market_tasks' in statement and 'state IN' in statement:
            barrier.wait(timeout=3)
    event.listen(repo.engine,'after_cursor_execute',align_reads)
    try:
        with ThreadPoolExecutor(2) as executor:
            ids=list(executor.map(lambda _:repo.enqueue('free','same','snapshot',{},0),range(2)))
        assert len(set(ids))==1
    finally:
        event.remove(repo.engine,'after_cursor_execute',align_reads)
