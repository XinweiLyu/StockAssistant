from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import create_engine
from src.repositories.a_share_repository import AssistantRepository
from src.schemas.a_share import AssistantSettings
from data_provider.a_share import normalize_spot, permitted_sources


def test_snapshots_immutable_modes_isolated_and_events_revisioned(tmp_path):
    repo = AssistantRepository(create_engine('sqlite:///' + str(tmp_path / 'state.db')))
    first = repo.append('demo','report','day',{'price':10})
    repo.append('free','report','day',{'price':20})
    assert repo.records('demo','report')[0]['payload'] == {'price':10}
    assert repo.add_event('free',{'source':'公告','url':'https://example.org/a','title':'公告','code':'600001','content':'v1'})
    assert not repo.add_event('free',{'source':'公告','url':'https://example.org/a','title':'公告','code':'600001','content':'v1'})
    assert repo.add_event('free',{'source':'公告','url':'https://example.org/a','title':'公告','code':'600001','content':'v2'})
    assert len(repo.records('free','event')) == 2
    repo.append('demo','report','day',{'price':30})
    assert any(r['id'] == first and r['payload']['price'] == 10 for r in repo.records('demo','report'))


def test_daily_budget_is_atomic_and_failed_calls_cannot_refund(tmp_path):
    repo = AssistantRepository(create_engine('sqlite:///' + str(tmp_path / 'state.db'), connect_args={'timeout':20}))
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _:repo.reserve_call('free','2026-10-09',20), range(40)))
    assert sum(results) == 20
    assert repo.usage('free','2026-10-09') == 20


def test_free_quote_volume_is_hands_and_does_not_invent_source_time():
    out = normalize_spot({'代码':'600001','最新价':10,'成交量':123,'成交额':456000}, '2026-10-09T10:00:00+08:00')
    assert out['volume'] == 12300
    assert out['source_time'] is None
    assert out['trade_date'] is None


def test_tier_alone_never_grants_paid_realtime_or_news():
    settings = AssistantSettings(mode='tushare5000')
    assert permitted_sources(settings)['snapshot'] == 'akshare'
    assert permitted_sources(settings)['news'] == 'akshare'
    assert permitted_sources(settings)['daily'] == 'tushare'


def test_daily_volume_units_differ_from_realtime_tushare():
    from data_provider.a_share import daily_rows, normalize_tushare_quote
    assert daily_rows([{'日期':'2026-10-08','收盘':10,'最高':11,'最低':9,'成交量':123,'成交额':1e8}], [{'日期':'2026-10-08','收盘':10}])[0]['volume']==12300
    q=normalize_tushare_quote({'ts_code':'600001.SH','close':10,'vol':123,'amount':456,'trade_time':'2026-10-09 10:00:00'},'2026-10-09T10:01:00+08:00')
    assert q['volume']==123
    assert q['source_time']=='2026-10-09T10:00:00+08:00'


def test_runtime_enable_flag_reaches_existing_config(monkeypatch):
    from src.config import Config
    monkeypatch.setenv('A_SHARE_ASSISTANT_ENABLED','true')
    assert Config._load_from_env().a_share_assistant_enabled


def test_sina_or_tencent_history_uses_share_units_and_matches_adjusted_dates():
    from data_provider.a_share import daily_rows
    raw=[dict(date='2026-10-08',close=10,high=11,low=9,volume=123,amount=1e8)]
    adjusted=[dict(date='2026-10-08',close=20)]
    row=daily_rows(raw,adjusted)[0]
    assert row['volume']==123
    assert row['adjusted_close']==20


def test_tencent_native_quote_price_used_without_guessing_monetary_units():
    from data_provider.a_share import normalize_alternate_spot
    q=normalize_alternate_spot(dict(code='sh600000',name='浦发银行',zxj='12.5',turnover='4567',volume='1234'), '2026-10-09T10:00:00+08:00','akshare/tencent')
    assert q['code']=='600000' and q['price']==12.5
    assert q['amount'] is None and q['volume'] is None
    assert q['download_sort_value']==4567


def test_budget_cannot_be_doubled_by_switching_demo_and_live(tmp_path):
    repo=AssistantRepository(create_engine('sqlite:///' + str(tmp_path/'db')))
    assert repo.reserve_call('demo','2026-10-09',1)
    assert not repo.reserve_call('free','2026-10-09',1)
