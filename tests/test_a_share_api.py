from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from api.v1.endpoints import a_share
from src.repositories.a_share_repository import AssistantRepository
from src.services.a_share_service import AssistantService


def test_demo_roundtrip_config_validation_exports_and_live_switch(tmp_path,monkeypatch):
    svc=AssistantService(AssistantRepository(create_engine('sqlite:///' + str(tmp_path/'db'))))
    monkeypatch.setattr(a_share,'get_assistant_service',lambda:svc)
    app=FastAPI()
    app.include_router(a_share.router,prefix='/assistant')
    client=TestClient(app)
    assert client.get('/assistant/dashboard').status_code==200
    svc.sync('daily')
    board=client.get('/assistant/dashboard').json()
    assert board['report']['demo'] is True
    response=client.get('/assistant/export?format=csv')
    assert response.status_code==200 and 'text/csv' in response.headers['content-type']
    assert 'DEMO' in response.text
    assert client.put('/assistant/settings',json={'mode':'free','watchlist':['BAD']}).status_code==422
    assert client.post('/assistant/holdings/constraints',json={'code':'600001','stop':-1,'note':'bad'}).status_code==422
    assert client.put('/assistant/settings',json={'mode':'free'}).status_code==200
    assert client.get('/assistant/dashboard').json()['report'] is None
    assert client.get('/assistant/export').status_code==409
