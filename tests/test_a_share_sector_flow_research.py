from tests.test_a_share_outlook_api import long_market
from tests.test_a_share_sector_flow_service import BOARD
from data_provider.a_share_sector_flow import normalize_history
from src.schemas.a_share_integrated import ResearchFact

def test_freeze_delivers_only_previously_observed_same_industry_data(tmp_path):
 svc,end=long_market(tmp_path);flow=svc.market.fund_flow
 days=svc.market.calendar();days=[d for d in days if d<=end][-20:]
 flow.sessions=lambda:days
 svc.market.repo.put_sectors('free',[BOARD]);svc.market.repo.replace_members('free',BOARD['sector_id'],'v1',['600000'])
 observed=end+'T16:00:00+08:00';cutoff=end+'T17:00:00+08:00'
 svc.integrated._now=lambda:cutoff
 rows=normalize_history([d+','+','.join(['10']*10+['100','1']) for d in days],BOARD,observed)
 flow.repo.save_daily('free',rows)
 fact=flow.research_fact('600000',BOARD,cutoff,end)
 ResearchFact.model_validate(fact)
 bundle=svc.integrated.freeze('600000',[])
 funds=[f for f in bundle['facts'] if f['fact_id'].startswith('sector_flow_')]
 assert len(funds)==1 and funds[0]['values']['main_net_20d']==200
 assert svc.repo.manual_usage('free',end)==0
 assert not [t for t in svc.market.repo.tasks('free') if t['kind'].startswith('sector_flow_') or t['kind']=='integrated_research']
 # A prior cutoff cannot see today's downloaded reconstruction.
 svc.integrated._now=lambda:end+'T15:30:00+08:00'
 assert not svc.integrated.freeze('600000',[])['facts']
