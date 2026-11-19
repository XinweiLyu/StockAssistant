from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.test_market_workspace_research import make_workspace


def test_catalog_stock_value_and_watchlist_are_market_scoped(tmp_path,monkeypatch):
    from api.v1.endpoints import market_workspace as module
    svc=make_workspace(tmp_path)
    monkeypatch.setattr(module,'service',lambda market:svc if market=='us' else None)
    app=FastAPI();app.include_router(module.router,prefix='/api/v1')
    client=TestClient(app)
    assert client.get('/api/v1/market-workspace/us/stocks').json()['items'][0]['code']=='us:AAPL'
    assert client.get('/api/v1/market-workspace/us/stocks/AAPL/value-research').status_code==200
    assert client.post('/api/v1/market-workspace/us/watchlist/AAPL').json()['codes']==['us:AAPL']
    assert client.delete('/api/v1/market-workspace/us/watchlist/us:AAPL').json()['codes']==[]
    assert client.get('/api/v1/market-workspace/xx/stocks').status_code==422
    assert client.get('/api/v1/market-workspace/us/stocks/hk:00700').status_code==422
    assert not svc.assistant.repo.records('free','value_review')


def test_listing_supplement_requires_public_source_and_attestation(tmp_path,monkeypatch):
    from api.v1.endpoints import market_workspace as module
    svc=make_workspace(tmp_path)
    monkeypatch.setattr(module,'service',lambda market:svc)
    app=FastAPI();app.include_router(module.router,prefix='/api/v1');client=TestClient(app)
    endpoint='/api/v1/market-workspace/us/stocks/AAPL/listing-binding'
    assert client.put(endpoint,json={'confirmed':False}).status_code==422
    payload=dict(confirmed=True,underlying_per_listed=1.,effective_date='2026-10-31',verified_through='2026-11-13',
        url='https://investor.apple.com/',quote='Each ordinary share corresponds to one listed share.',reason='核对股权类别与资本行动')
    assert client.put(endpoint,json=payload).status_code==200
    assert svc.repo.get_state('free','listing-binding:us:AAPL')['capital']['sources']


def test_sector_period_query_matches_browser_explicit_zero(tmp_path,monkeypatch):
    from api.v1.endpoints import market_workspace as module
    svc=make_workspace(tmp_path)
    monkeypatch.setattr(module,'service',lambda market:svc)
    app=FastAPI();app.include_router(module.router,prefix='/api/v1');client=TestClient(app)
    url='/api/v1/market-workspace/us/sectors'
    response=client.get(url,params={'kind':'industry','period':0})
    assert response.status_code==200
    assert len(response.json()['items'])==1
    assert client.get(url,params={'kind':'concept','period':0}).status_code==200
    assert client.get(url,params={'kind':'industry','period':7}).status_code==422
