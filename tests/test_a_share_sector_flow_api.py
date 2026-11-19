from tests.test_a_share_market_integration import setup_market
from tests.test_a_share_market_api import client_for

def test_flow_routes_accept_query_period_and_validate(tmp_path,monkeypatch):
 from tests.test_a_share_sector_flow_service import BOARD
 svc,_=setup_market(tmp_path)
 svc.market.repo.put_sectors('free',[BOARD])
 c=client_for(svc,monkeypatch);url='/assistant/market/sectors/'+BOARD['sector_id']+'/fund-flow'
 for period in (0,5,20,60):assert c.get(url,params={'period':str(period)}).status_code==200
 assert c.get(url,params={'period':7}).status_code==422
 assert c.get(url.replace(BOARD['sector_id'],'yahoo:technology')).status_code==422
 assert c.post(url+'/refresh').status_code==200
 assert c.get('/assistant/market/sectors/fund-flow-rankings?kind=concept').status_code==200
 assert c.get('/assistant/market/sectors/fund-flow-rankings?kind=US').status_code==422
