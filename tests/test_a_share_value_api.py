from tests.test_a_share_market_api import client_for
from tests.test_a_share_value_service import value_service


def test_value_routes_validate_and_keep_get_free(tmp_path, monkeypatch):
    svc = value_service(tmp_path)
    c = client_for(svc, monkeypatch)
    base = '/assistant/market/stocks/600034'
    assert c.get(base+'/value-research').json()['status'] == 'missing'
    assert c.get('/assistant/market/stocks/123456/value-research').status_code == 404
    assert c.post(base+'/value-data', json={'peer_offset': 501}).status_code == 422
    assert c.post(base+'/value-data', json={}).status_code == 200
    assert c.post(base+'/value-research', json={'snapshot_id': 'old'}).status_code == 409
    assert c.put(base+'/value-assumptions', json={}).status_code == 422
    assert c.post(base+'/value-evaluate', json={}).status_code == 422
    assert c.post(base+'/value-supplement', json={}).status_code == 422
    assert svc.repo.manual_usage('free', '2026-10-30') == 0


def test_real_error_handler_returns_422_for_model_validator_context(tmp_path, monkeypatch):
    from api.middlewares.error_handler import add_error_handlers
    from fastapi.testclient import TestClient
    svc=value_service(tmp_path)
    c=client_for(svc,monkeypatch)
    add_error_handlers(c.app)
    c=TestClient(c.app,raise_server_exceptions=False)
    body=dict(snapshot_id='unused',attested=True,facts=[dict(metric='current_shares',value=10,unit='CNY',
        report_period='2026-10-30',period_basis='annual',scope='consolidated',attribution='minority',
        url='https://example.com/report',title='校验',published_at='2026-10-30',quote='总股本',reason='单位合同检查')])
    response=c.post('/assistant/market/stocks/600034/value-supplement',json=body)
    assert response.status_code==422
    detail=response.json()['detail']
    assert '当前总股本' in detail[0]['msg']


def test_real_error_handler_serializes_nonfinite_input(tmp_path, monkeypatch):
    from api.middlewares.error_handler import add_error_handlers
    svc=value_service(tmp_path);c=client_for(svc,monkeypatch);add_error_handlers(c.app)
    response=c.post('/assistant/market/stocks/600034/value-supplement',content='{"snapshot_id":"unused","attested":true,"facts":[{"value":NaN}]}',headers={'Content-Type':'application/json'})
    assert response.status_code==422
    assert response.json()['error']=='validation_error'
