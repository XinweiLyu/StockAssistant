from datetime import datetime,timezone
from types import SimpleNamespace
import threading
import pandas as pd
import pytest
from sqlalchemy import create_engine
from src.repositories.a_share_repository import AssistantRepository
from src.schemas.a_share import AssistantSettings
from src.schemas.a_share_market import CatalogQuery


class Source:
    calls=0
    def catalog(self,market):return [{'symbol':'AAPL','name':'Apple','aliases':['苹果']}] if market=='us' else [{'symbol':'00700','name':'腾讯'}]
    def identity(self,identity):
        return dict(name='Apple',exchange='NMS',asset_type='stock',currency='USD',financial_currency='USD',industry='Consumer Electronics',sector='Technology',verified=True)
    def history(self,identity,start,end):
        self.calls+=1
        return dict(raw=[dict(date='2026-11-13',open=100.,high=110.,low=99.,close=105.,volume=1000.)],
            adjusted=[dict(date='2026-11-13',open=50.,high=55.,low=49.5,close=52.5,volume=1000.)],actions=[],source='yfinance',basis='fixture-pair',fetched_at='2026-11-16T08:00:00+00:00')
    def quote(self,identity):return dict(price=105.,trade_date='2026-11-13',source_time='2026-11-13T21:00:00+00:00',currency='USD',source='yfinance')


@pytest.fixture
def workspace(tmp_path):
    from src.services.market_workspace_service import MarketWorkspaceService
    repo=AssistantRepository(create_engine('sqlite:///'+str(tmp_path/'workspace.db')))
    parent=SimpleNamespace(repo=repo,settings=AssistantSettings(mode='free'),_settings_lock=threading.RLock())
    return MarketWorkspaceService(parent,'us',provider=Source(),clock=lambda:datetime(2026,11,16,8,tzinfo=timezone.utc))


def test_catalog_is_qualified_and_does_not_verify_old_index(workspace):
    page=workspace.catalog(CatalogQuery())
    assert page['items'][0]['code']=='us:AAPL'
    assert not page['items'][0]['identity_verified']
    assert page['coverage']['catalog_total']==1
    assert workspace.repo.stock('free','us:AAPL')
    from src.repositories.a_share_market_repository import MarketRepository
    assert MarketRepository(workspace.repo.engine).stock('free','us:AAPL') is None


def test_chinese_alias_search_uses_existing_index_aliases(workspace):
    assert workspace.catalog(CatalogQuery(q='苹果'))['items'][0]['code']=='us:AAPL'


def test_one_paired_job_populates_both_bases_and_reuses_cache(workspace):
    workspace.catalog(CatalogQuery())
    raw=workspace.history('AAPL','2026-11-12','2026-11-16','raw')
    adj=workspace.history('us:AAPL','2026-11-12','2026-11-16','qfq')
    assert raw.state==adj.state=='pending' and raw.task_id==adj.task_id
    while workspace.jobs.run_one():pass
    raw=workspace.history('AAPL','2026-11-12','2026-11-16','raw')
    adj=workspace.history('AAPL','2026-11-12','2026-11-16','qfq')
    assert raw.items[0].close==105. and adj.items[0].close==52.5
    assert raw.adjustment_basis==adj.adjustment_basis
    assert raw.actual_end==adj.actual_end=='2026-11-13'
    assert workspace.provider.calls==1


def test_stock_history_accepts_a_listing_lifetime_request(workspace):
    start, end = '1900-01-01', '2026-11-13'
    raw = workspace.history('AAPL', start, end, 'raw')
    assert raw.state == 'pending'
    while workspace.jobs.run_one():
        pass
    adjusted = workspace.history('AAPL', start, end, 'qfq')
    assert adjusted.state == 'ready'
    assert adjusted.actual_start == '2026-11-13'
    assert adjusted.requested_start == start


def test_history_refresh_keeps_cached_pair_and_reuses_pending_work(workspace):
    start, end = '2026-11-12', '2026-11-13'
    workspace.history('AAPL', start, end, 'raw')
    while workspace.jobs.run_one():
        pass
    assert workspace.history('AAPL', start, end, 'qfq').state == 'ready'

    refreshing = workspace.history('AAPL', start, end, 'qfq', refresh=True)
    duplicate = workspace.history('AAPL', start, end, 'raw', refresh=True)
    polled = workspace.history('AAPL', start, end, 'qfq')
    assert refreshing.state == duplicate.state == polled.state == 'pending'
    assert refreshing.task_id == duplicate.task_id == polled.task_id
    assert refreshing.items[0].close == 52.5
    assert duplicate.items[0].close == 105.

    while workspace.jobs.run_one():
        pass
    assert workspace.history('AAPL', start, end, 'qfq').state == 'ready'
    assert workspace.provider.calls == 2


def test_history_respects_retry_backoff_after_provider_rate_limit(workspace, monkeypatch):
    from yfinance.exceptions import YFRateLimitError

    def rate_limited(*args):
        raise YFRateLimitError()

    monkeypatch.setattr(workspace.provider, 'history', rate_limited)
    start, end = '2026-11-12', '2026-11-13'
    initial = workspace.history('AAPL', start, end, 'qfq')
    while workspace.jobs.run_one():
        pass

    retry = workspace.history('AAPL', start, end, 'qfq', refresh=True)
    assert retry.state == 'pending'
    assert retry.task_id == initial.task_id
    assert not retry.items
    assert any('Yahoo 暂时限制行情请求' in line for line in retry.limitations)
    assert not workspace.jobs.run_one()


def test_manual_refresh_schedules_only_market_data(workspace):
    workspace.catalog(CatalogQuery())
    result=workspace.refresh_price('AAPL')
    assert result['code']=='us:AAPL' and result['state']=='pending'
    while workspace.jobs.run_one():pass
    live=workspace.live_price('AAPL')
    assert live['quote']['price']==105.
    assert not workspace.assistant.repo.records('free','value_review')
    assert not workspace.assistant.repo.records('free','integrated_report')


def test_verified_quote_currency_reaches_forecast_and_chart_without_identity(workspace, monkeypatch):
    from src.services.a_share_outlook_service import OutlookService

    def no_profile(identity):
        raise ValueError('Provider profile unavailable')

    monkeypatch.setattr(workspace.provider, 'identity', no_profile)
    stock = workspace.stock('AAPL')
    assert stock['currency'] is None
    workspace.refresh_price('AAPL')
    while workspace.jobs.run_one():
        pass

    stock = workspace.stock('AAPL')
    assert not stock['identity_verified']
    assert stock['financial_currency'] is None
    assert stock['quote']['currency'] == stock['currency'] == 'USD'
    for adjust in ('raw', 'qfq'):
        pane = workspace.history('AAPL', '2026-11-12', '2026-11-13', adjust)
        assert pane.currency == 'USD'
    assert OutlookService(workspace.assistant).get('us:AAPL')['currency'] == 'USD'


def test_yahoo_raw_adjusted_pair_is_not_auto_adjusted():
    from data_provider.market_workspace import yahoo_price_pair
    data=pd.DataFrame({'Open':[100.],'High':[110.],'Low':[90.],'Close':[105.],
        'Adj Close':[52.5],'Volume':[1000],'Stock Splits':[0.],'Dividends':[0.]},index=pd.to_datetime(['2026-11-13']))
    pair=yahoo_price_pair(data,'2026-11-16T00:00:00+00:00')
    assert pair['raw'][0]['close']==105 and pair['adjusted'][0]['close']==52.5
    assert pair['raw'][0]['amount'] is None


def test_calendar_unknown_does_not_certify_prices(workspace,monkeypatch):
    import src.core.trading_calendar as calendar
    monkeypatch.setattr(calendar,'get_trading_dates',lambda *a,**k:None)
    with pytest.raises(ValueError,match='日历'):workspace.completed_day()


def test_quote_source_time_is_provider_time_not_retrieval_time():
    from data_provider.market_workspace import yahoo_quote
    from src.services.market_workspace_symbols import resolve_instrument
    identity=resolve_instrument('us','AAPL')
    quote=yahoo_quote(identity,dict(regularMarketPrice=105.,regularMarketTime=1794603600,currency='USD'))
    assert quote['source_time']=='2026-11-13T21:00:00+00:00'
    assert quote['trade_date']=='2026-11-13'
    assert yahoo_quote(identity,dict(regularMarketPrice=105.,currency='USD'))['source_time'] is None


def test_incomplete_adjustment_cannot_replace_one_side_of_a_saved_pair(workspace):
    workspace.catalog(CatalogQuery());workspace.history('AAPL','2026-11-12','2026-11-16','raw')
    while workspace.jobs.run_one():pass
    original=workspace.repo.get_history('free','stock:us:AAPL','raw','2026-11-12','2026-11-13')
    base=workspace.provider.history
    workspace.provider.history=lambda *args:base(*args)|dict(adjusted=[],basis='bad-pair')
    workspace.history('AAPL','2026-11-12','2026-11-16','raw',True)
    workspace.jobs.run_one()
    saved=workspace.repo.get_history('free','stock:us:AAPL','raw','2026-11-12','2026-11-13')
    assert saved['adjustment_basis']==original['adjustment_basis']


def test_intraday_refresh_returns_bound_temporary_candle(workspace):
    workspace.clock=lambda:datetime(2026,11,16,18,tzinfo=timezone.utc)
    workspace.provider.quote=lambda identity:dict(price=108.,trade_date='2026-11-16',source_time='2026-11-16T18:00:00+00:00',currency='USD',source='yfinance',open=106.,high=110.,low=104.,volume=1200.)
    workspace.catalog(CatalogQuery());workspace.history('AAPL','2026-11-12','2026-11-16','raw')
    while workspace.jobs.run_one():pass
    workspace.refresh_price('AAPL')
    while workspace.jobs.run_one():pass
    result=workspace.live_price('AAPL')
    assert result['provisional'] and result['history_updated']
    assert result['bars']['raw']['date']=='2026-11-16' and result['bars']['qfq']['close']==54.
    assert result['history_binding']['raw']['anchor_date']=='2026-11-13'


def test_hk_calendar_excludes_official_full_day_weather_closures():
    from datetime import date
    from src.core.trading_calendar import get_trading_dates, is_market_open, get_next_trading_date, get_effective_trading_date, infer_market_phase, MarketPhase
    days = get_trading_dates('hk', date(2023,8,31), date(2023,9,11))
    assert '2023-09-01' not in days.strftime('%Y-%m-%d')
    assert '2023-09-08' not in days.strftime('%Y-%m-%d')
    assert not is_market_open('hk', date(2023,9,1))
    assert get_next_trading_date('hk', date(2023,8,31)) == date(2023,9,4)
    assert get_effective_trading_date('hk', datetime(2023,9,8,17)) == date(2023,9,7)
    assert infer_market_phase('hk', datetime(2023,9,8,10)) == MarketPhase.NON_TRADING


def test_hk_completed_anchor_skips_exceptional_closure(workspace):
    from src.services.market_workspace_service import MarketWorkspaceService
    hk=MarketWorkspaceService(workspace.parent,'hk',provider=Source(),clock=lambda:datetime(2023,9,8,10,tzinfo=timezone.utc))
    assert hk.completed_day()=='2023-09-07'


def test_queued_work_cannot_publish_into_a_new_parent_mode(workspace):
    workspace.catalog(CatalogQuery());workspace.stock('AAPL')
    workspace.parent.settings=AssistantSettings(mode='demo')
    workspace.catalog(CatalogQuery())
    workspace.jobs.run_one()
    assert not workspace.repo.stock('demo','us:AAPL')['identity_verified']
    assert not workspace.repo.stock('free','us:AAPL')['identity_verified']


def test_mode_change_during_external_fetch_discards_publication(workspace):
    workspace.catalog(CatalogQuery());workspace.stock('AAPL')
    original=workspace.provider.identity
    def changed(identity):
        workspace.parent.settings=AssistantSettings(mode='demo')
        workspace.catalog(CatalogQuery())
        return original(identity)
    workspace.provider.identity=changed
    workspace.jobs.run_one()
    assert not workspace.repo.stock('demo','us:AAPL')['identity_verified']
    assert not workspace.repo.stock('free','us:AAPL')['identity_verified']


def test_workspace_lifecycle_starts_and_stops_all_queues(workspace,monkeypatch):
    workspace.initialize_research()
    seen=[]
    for label,queue in [('market',workspace.jobs),('data',workspace.assistant.integrated.jobs),('value',workspace.assistant.value.jobs)]:
        monkeypatch.setattr(queue,'start',lambda label=label:seen.append('start:'+label))
        monkeypatch.setattr(queue,'stop',lambda label=label:seen.append('stop:'+label))
    workspace.start();workspace.stop()
    assert seen==['start:market','start:data','start:value','stop:market','stop:data','stop:value']


def test_history_reuses_same_generation_earlier_bars_for_indicator_warmup(workspace):
    workspace.catalog(CatalogQuery())
    original=workspace.provider.history
    def history(*args):
        pair=original(*args)
        pair['raw']=[pair['raw'][0]|dict(date='2026-11-12')]+pair['raw']
        pair['adjusted']=[pair['adjusted'][0]|dict(date='2026-11-12')]+pair['adjusted']
        return pair
    workspace.provider.history=history
    workspace.history('AAPL','2026-11-12','2026-11-13','qfq')
    while workspace.jobs.run_one():pass
    page=workspace.history('AAPL','2026-11-13','2026-11-13','qfq')
    assert [b.date for b in page.items]==['2026-11-13']
    assert [b.date for b in page.warmup_items]==['2026-11-12']
    assert page.warmup_items[0].close==52.5


def test_hk_complete_daily_bar_waits_for_closing_auction(workspace):
    from src.services.market_workspace_service import MarketWorkspaceService
    hk=MarketWorkspaceService(workspace.parent,'hk',provider=Source(),clock=lambda:datetime(2026,11,13,8,5,tzinfo=timezone.utc))
    assert hk.completed_day()=='2026-11-12'
    hk.clock=lambda:datetime(2026,11,13,8,10,tzinfo=timezone.utc)
    assert hk.completed_day()=='2026-11-13'


def test_hk_half_day_complete_bar_also_waits_until_1210(workspace):
    from src.services.market_workspace_service import MarketWorkspaceService
    hk=MarketWorkspaceService(workspace.parent,'hk',provider=Source(),clock=lambda:datetime(2025,12,24,4,5,tzinfo=timezone.utc))
    assert hk.completed_day()=='2025-12-23'
    hk.clock=lambda:datetime(2025,12,24,4,10,tzinfo=timezone.utc)
    assert hk.completed_day()=='2025-12-24'
