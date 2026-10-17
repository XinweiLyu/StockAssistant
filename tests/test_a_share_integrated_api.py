from tests.test_a_share_market_api import client_for
from tests.test_a_share_outlook_api import long_market


def test_integrated_api_keeps_legacy_and_validates_identity_and_options(tmp_path, monkeypatch):
    svc, _ = long_market(tmp_path)
    c = client_for(svc, monkeypatch)
    base = '/assistant/market/stocks/600000'
    assert c.get(base+'/integrated-research').json()['status'] == 'missing'
    assert c.get('/assistant/market/stocks/123456/integrated-research').status_code == 404
    assert c.post(base+'/research-data?peer_offset=-1').status_code == 422
    assert c.post(base+'/research-data').json()['status'] == 'preparing'
    assert c.get(base+'/scenarios').status_code == 200
    assert c.get(base+'/research-validation').status_code == 200
    assert c.post(base+'/integrated-research').json()['accepted'] is False
