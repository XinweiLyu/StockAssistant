import pytest
from tests.test_a_share_sector_flow_service import flow,BOARD
from data_provider.a_share_sector_flow import normalize_rank
from tests.test_a_share_market_api import client_for
from tests.test_a_share_market_integration import setup_market
SECOND=BOARD|dict(code='BK0438',sector_id='em:industry:BK0438',name='食品饮料')

def test_compare_reads_current_day_same_profile_and_queues_only_one_shared_rank(flow):
 flow.market.repo.put_sectors('free',[SECOND])
 today=normalize_rank([dict(f12='BK0478',f14='有色金属',f62=1e8),dict(f12='BK0438',f14='食品饮料',f62=-2e8)],'industry','2026-11-17T02:00:00Z')
 flow.repo.save_observations('free',today)
 flow.repo.save_observations('tushare5000',normalize_rank([dict(f12='BK0478',f14='有色金属',f62=999)],'industry','2026-11-17T02:00:00Z'))
 flow.repo.save_observations('free',normalize_rank([dict(f12='BK0478',f14='有色金属',f62=555)],'industry','2026-11-16T02:00:00Z'))
 result=flow.comparison('industry',[BOARD['sector_id'],SECOND['sector_id']])
 assert len(result['series'])==2 and len(result['series'][0]['points'])==1
 assert result['series'][0]['points'][0]['values']['main']==1e8
 assert result['day']=='2026-11-17' and result['source_date_verified'] is False
 again=flow.comparison('industry',[SECOND['sector_id']])
 assert again['task_id']==result['task_id']
 assert {t['kind'] for t in flow.market.repo.tasks('free')}=={'sector_flow_rank'}

def test_validate_all_ids_before_queue_and_never_fake_missing_board_data(flow):
 for kind,ids in [('industry',[BOARD['sector_id']]*2),('concept',[BOARD['sector_id']]),('us',[BOARD['sector_id']]),('industry',['hk:industry:test']),('industry',['a']*9)]:
  with pytest.raises(ValueError):flow.comparison(kind,ids)
 assert not flow.market.repo.tasks('free')
 flow.market.repo.set_state('free','sector-flow:health:rank:industry',dict(status='failed',error='offline'))
 value=flow.comparison('industry',[BOARD['sector_id']])
 assert value['series'][0]['points']==[] and value['series'][0]['latest'] is None
 assert value['health']['status']=='failed'

def test_empty_selection_does_not_queue(flow):
 assert flow.comparison('industry',[])['series']==[]
 assert not flow.market.repo.tasks('free')

def test_compare_api_csv_query_and_limits(tmp_path,monkeypatch):
 svc,_=setup_market(tmp_path);svc.market.repo.put_sectors('free',[BOARD,SECOND])
 client=client_for(svc,monkeypatch);url='/assistant/market/sectors/fund-flow-comparison'
 r=client.get(url,params=dict(kind='industry',ids=BOARD['sector_id']+','+SECOND['sector_id']))
 assert r.status_code==200 and len(r.json()['series'])==2
 assert client.get(url,params=dict(kind='concept',ids=BOARD['sector_id'])).status_code==422
 assert client.get(url,params=dict(ids=','.join([BOARD['sector_id']]*9))).status_code==422
