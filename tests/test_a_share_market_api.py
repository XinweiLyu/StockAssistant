from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.v1.endpoints import a_share
from tests.test_a_share_market_integration import setup_market


def client_for(svc,monkeypatch):
    monkeypatch.setattr(a_share,'get_assistant_service',lambda:svc)
    app=FastAPI();app.include_router(a_share.router,prefix='/assistant')
    return TestClient(app)

def test_market_pages_non_candidate_history_and_validation(tmp_path,monkeypatch):
    svc,warmup=setup_market(tmp_path)
    client=client_for(svc,monkeypatch)
    r=client.get('/assistant/market/stocks?page_size=10&page=2')
    assert r.status_code==200 and len(r.json()['items'])==10 and r.json()['total']==35
    assert client.get('/assistant/market/stocks/600034').json()['code']=='600034'
    assert client.get('/assistant/stocks/600034').status_code==200
    for query in ('page_size=101','sort=DROP','board=bad'):
        assert client.get('/assistant/market/stocks?'+query).status_code==422
    for start,end in [('2020-01-01','2026-01-01'),('2025-99-01','2025-10-01'),('2026-01-01','2025-01-01')]:
        assert client.get('/assistant/market/stocks/600034/history',params=dict(start=start,end=end)).status_code==422
    assert client.get('/assistant/market/stocks/600034/history',params=dict(start='2023-01-01',end=warmup['as_of'])).json()['state']=='pending'
    assert client.get('/assistant/market/sectors?classification=unregistered').status_code==422
    assert client.get('/assistant/market/stocks/123456').status_code==404
    assert client.get('/assistant/market/stocks/600034/scenarios').json()['status']=='insufficient'

def test_duplicate_warmup_and_pause_do_not_disable_read_only_history(tmp_path,monkeypatch):
    svc,warmup=setup_market(tmp_path)
    client=client_for(svc,monkeypatch)
    a=client.post('/assistant/market/warmup').json()
    b=client.post('/assistant/market/warmup').json()
    assert a['task_id']==b['task_id']
    assert client.post('/assistant/market/jobs/pause').json()['paused']
    assert client.get('/assistant/market/stocks/600034/history',params=dict(start=warmup['start'],end=warmup['as_of'])).status_code==200
    assert not client.post('/assistant/market/jobs/resume').json()['paused']
    assert client.get('/assistant/market/jobs').json()['coverage']['catalog_total']==35
    assert svc.repo.usage('free',warmup['as_of'])==0

def test_watchlist_and_candidate_scopes_are_filtered_before_paging(tmp_path,monkeypatch):
    svc,warmup=setup_market(tmp_path)
    svc.settings=svc.settings.model_copy(update={'watchlist':['600034']})
    c=client_for(svc,monkeypatch)
    assert [s['code'] for s in c.get('/assistant/market/stocks?scope=watchlist&page_size=1').json()['items']]==['600034']
    assert c.get('/assistant/market/stocks?scope=candidates').json()['total']==0

def test_sector_period_query_strings_are_coerced_and_validated(tmp_path,monkeypatch):
    svc,warmup=setup_market(tmp_path)
    c=client_for(svc,monkeypatch)
    for period in ['0','5','20','60']:
        response=c.get('/assistant/market/sectors',params={'period':period})
        assert response.status_code==200
    assert c.get('/assistant/market/sectors?period=7').status_code==422
