from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from tests.test_a_share_market_service import market_service
from src.schemas.a_share_market import HistoryPage
from tests.test_a_share_market_api import client_for


def at(svc,hour,minute=0):
    svc.clock=lambda:datetime(2026,10,12,hour-8,minute,tzinfo=timezone.utc)
    svc.jobs.clock=svc.clock


def provider(svc,missing=False,invalid=False,truncated=False):
    calls=[]
    class Fixed:
        def history(self,code,start,end,adjust,source=None):
            calls.append((code,start,end,adjust,source))
            dates=['2026-10-08','2026-10-09']+([] if missing else ['2026-10-12'])
            if truncated: dates=dates[-1:]
            items=[dict(date=d,open=10,high=12,low=9,close=11,volume=100) for d in dates]
            if invalid and adjust=='qfq': items[-1]['close']=15
            return HistoryPage(code=code,adjust=adjust,items=items,source='akshare/eastmoney',
                               adjustment_basis='akshare:2026-10-12',requested_start=start,requested_end=end,
                               state='ready',fetched_at='2026-10-12T14:30:00+08:00')
    svc.provider_for=lambda _:Fixed()
    return calls


def cached(svc):
    for adjust in ('raw','qfq'):
        svc.repo.replace_history('free','stock:000001',adjust,'akshare/eastmoney','old',
            [dict(date=d,open=10,high=12,low=9,close=10) for d in ['2026-10-08','2026-10-09']],
            '2026-10-09',requested_start='2026-10-08',requested_end='2026-10-09')


def run(svc,job):
    task=svc.repo.claim('free',svc.clock())
    assert task['id']==job['task_id']
    svc.handle_task(task)
    svc.repo.finish(task['id'],task['claim_version'],'complete')
    return svc.live_price('000001')


def test_live_reads_do_not_fetch_and_unknown_symbol_cannot_queue(market_service):
    svc=market_service
    assert svc.live_price('000001')['state']=='unavailable'
    assert svc.repo.progress('free')['counts']=={}
    with pytest.raises(ValueError): svc.refresh_price('999999')
    assert svc.repo.progress('free')['counts']=={}


def test_selected_refresh_deduplicates_pending_and_does_not_request_research(market_service):
    svc=market_service;at(svc,14)
    a=svc.refresh_price('000001');b=svc.refresh_price('000001')
    assert a['state']=='pending' and a['task_id']==b['task_id']
    task=svc.repo.task(a['task_id'])
    assert task['kind']=='stock_live' and task['payload']['code']=='000001'
    assert len(svc.repo.tasks('free'))==1


def test_intraday_preview_keeps_unfinished_day_out_of_completed_history(market_service):
    svc=market_service;at(svc,14);cached(svc);calls=provider(svc)
    svc.repo.put_quotes('free','whole-market',[dict(code='600001',price=9)])
    value=run(svc,svc.refresh_price('000001'))
    assert value['state']=='ready' and value['provisional']
    assert value['bars']['raw']['date']=='2026-10-12'
    assert value['quote']['price']==11 and value['quote']['trade_date']=='2026-10-12'
    assert value['quote']['source_time'] is None
    assert value['history_updated']
    assert svc.repo.get_history('free','stock:000001','raw','1900-01-01','2026-10-12')['items'][-1]['date']=='2026-10-09'
    assert svc.repo.get_state('free','quote_batch')['batch']=='whole-market'
    assert {c[0] for c in calls}=={'000001'}


def test_after_close_refresh_publishes_real_today_and_earlier_cutoff(market_service):
    svc=market_service;at(svc,15,9)
    assert svc.completed_day()=='2026-10-09'
    at(svc,15,10)
    assert svc.completed_day()=='2026-10-12'
    cached(svc);provider(svc)
    value=run(svc,svc.refresh_price('000001'))
    assert not value['provisional'] and value['history_updated']
    assert svc.history('000001','2026-10-08','2026-10-12','raw').items[-1].date=='2026-10-12'


@pytest.mark.parametrize('failure',['missing','invalid'])
def test_failed_or_lagging_source_preserves_history_and_reports_retry(market_service,failure):
    svc=market_service;at(svc,16);cached(svc)
    svc.assistant.settings=svc.assistant.settings.model_copy(update={'free_fallback':False})
    provider(svc,**{failure:True})
    value=run(svc,svc.refresh_price('000001'))
    assert value['state']=='failed' and not value['history_updated']
    assert '重试' in value['message']
    assert svc.repo.get_history('free','stock:000001','qfq','1900-01-01','2026-10-12')['adjustment_basis']=='old'


def test_short_refresh_can_update_quote_but_cannot_destroy_long_history(market_service):
    svc=market_service;at(svc,16);cached(svc);provider(svc,truncated=True)
    value=run(svc,svc.refresh_price('000001'))
    assert value['state']=='ready' and not value['history_updated']
    assert len(svc.repo.get_history('free','stock:000001','raw','1900-01-01','2026-10-12')['items'])==2


def test_closed_market_fetch_does_not_label_previous_session_as_today(market_service):
    svc=market_service;at(svc,16)
    svc.clock=lambda:datetime(2026,10,11,8,tzinfo=timezone.utc)
    assert svc.refresh_price('000001')['state']=='unavailable'
    assert svc.repo.progress('free')['counts']=={}


def test_api_refresh_and_read_are_additive_and_model_free(market_service,monkeypatch):
    svc=SimpleNamespace(market=market_service,_settings_lock=__import__('threading').RLock())
    c=client_for(svc,monkeypatch)
    assert c.get('/assistant/market/stocks/000001/live').json()['state']=='unavailable'
    assert c.post('/assistant/market/stocks/000001/refresh').json()['state']=='pending'
    assert c.post('/assistant/market/stocks/999999/refresh').status_code==404


def test_older_queued_history_cannot_erase_manually_refreshed_today(market_service):
    svc=market_service;at(svc,16);cached(svc);provider(svc)
    run(svc,svc.refresh_price('000001'))
    class Older:
        def history(self,code,start,end,adjust,source=None):
            return HistoryPage(code=code,adjust=adjust,source='akshare/eastmoney',adjustment_basis='old',
                requested_start=start,requested_end=end,state='ready',fetched_at='2026-10-12',
                items=[dict(date=d,open=10,high=12,low=9,close=10) for d in ['2026-10-08','2026-10-09']])
    svc.provider_for=lambda _:Older()
    page=svc.history('000001','2026-10-08','2026-10-09','raw',refresh=True)
    task=svc.repo.claim('free',svc.clock());assert task['id']==page.task_id
    svc.handle_task(task)
    assert svc.repo.get_history('free','stock:000001','raw','1900-01-01','2026-10-12')['items'][-1]['date']=='2026-10-12'


def test_refresh_does_not_invent_day_change_from_unadjusted_ex_rights_gap(market_service):
    svc=market_service;at(svc,16)
    class Action:
        def history(self,code,start,end,adjust,source=None):
            values=[10,9] if adjust=='raw' else [9,9]
            return HistoryPage(code=code,adjust=adjust,source='akshare/eastmoney',adjustment_basis='new',
                requested_start=start,requested_end=end,state='ready',fetched_at='2026-10-12',
                items=[dict(date=d,open=v,high=v,low=v,close=v) for d,v in zip(['2026-10-09','2026-10-12'],values)])
    svc.provider_for=lambda _:Action()
    value=run(svc,svc.refresh_price('000001'))
    assert value['quote']['change'] is None
    assert svc.repo.quotes('free',['000001'])['000001']['change'] is None


def test_queue_retry_error_is_visible_and_user_can_retry_without_waiting(market_service):
    from datetime import timedelta
    svc=market_service;at(svc,16)
    first=svc.refresh_price('000001')
    task=svc.repo.claim('free',svc.clock())
    svc.repo.finish(task['id'],task['claim_version'],'pending',error='来源调用失败',
                    next_attempt=(svc.clock()+timedelta(minutes=15)).isoformat())
    assert svc.live_price('000001')['state']=='failed'
    second=svc.refresh_price('000001')
    assert second['state']=='pending' and second['task_id']!=first['task_id']
    calls=provider(svc)
    task=svc.repo.task(first['task_id']);task['claim_version']=0
    svc.handle_task(task)
    assert calls==[]


def test_pair_publication_failure_rolls_back_both_histories_and_quote(market_service):
    svc=market_service;at(svc,16);cached(svc);provider(svc)
    svc.repo.put_quotes('free','old-batch',[dict(code='000001',price=10)])
    original=svc.repo.replace_history
    def fail_second(profile,entity,adjust,*args,**kwargs):
        if adjust=='qfq': raise RuntimeError('database write failed')
        return original(profile,entity,adjust,*args,**kwargs)
    svc.repo.replace_history=fail_second
    svc.refresh_price('000001');svc.jobs.run_one()
    assert svc.live_price('000001')['state']=='failed'
    for adjust in ('raw','qfq'):
        value=svc.repo.get_history('free','stock:000001',adjust,'1900-01-01','2026-10-12')
        assert value['actual_end']=='2026-10-09' and value['adjustment_basis']=='old'
    assert svc.repo.quotes('free',['000001'])['000001']['price']==10


def test_daily_refresh_keeps_cache_start_when_five_year_floor_moves(market_service):
    svc=market_service;at(svc,16)
    rows=[dict(date=d,open=10,high=12,low=9,close=10) for d in ['2021-10-11','2026-10-09']]
    for adjust in ('raw','qfq'):
        svc.repo.replace_history('free','stock:000001',adjust,'akshare/eastmoney','old',rows,'2026-10-09',
                                 requested_start='2021-10-11',requested_end='2026-10-09')
    queued=svc.refresh_price('000001')
    assert svc.repo.task(queued['task_id'])['payload']['start']=='2021-10-11'


def test_intraday_bar_binds_to_each_committed_history_publication(market_service):
    svc=market_service;at(svc,14);cached(svc);provider(svc)
    value=run(svc,svc.refresh_price('000001'))
    for adjust in ('raw','qfq'):
        history=svc.history('000001','2026-10-08','2026-10-12',adjust)
        binding=value['history_binding'][adjust]
        assert binding==dict(source=history.source,adjustment_basis=history.adjustment_basis,
                            fetched_at=history.fetched_at,anchor_date=history.items[-1].date,
                            anchor_close=history.items[-1].close)


def test_truncated_intraday_history_cannot_claim_an_adjustment_binding(market_service):
    svc=market_service;at(svc,14);cached(svc);provider(svc,truncated=True)
    value=run(svc,svc.refresh_price('000001'))
    assert value['provisional'] and not value['history_updated']
    assert value['history_binding']=={'raw':None,'qfq':None}
