from sqlalchemy import create_engine
from tests.test_a_share_sector_flow_data import NOW,SECTOR


def test_same_bucket_replaces_observation_without_summing_and_isolates_profiles(tmp_path):
    from src.repositories.a_share_sector_flow_repository import SectorFlowRepository
    from data_provider.a_share_sector_flow import normalize_rank
    repo=SectorFlowRepository(create_engine('sqlite:///'+str(tmp_path/'f.db')))
    first=normalize_rank([dict(f12='BK0478',f14='有色金属',f62=100)],'industry',NOW)[0]
    repo.save_observations('free',[first])
    repo.save_observations('free',[first|dict(observed_at='2026-11-17T02:06:00+00:00',values=first['values']|dict(main=110.))])
    values=repo.read_observations('free',SECTOR['sector_id'],'2026-11-17')
    assert len(values)==1 and values[0]['values']['main']==110
    assert repo.read_observations('demo',SECTOR['sector_id'],'2026-11-17')==[]
    repo.save_observations('free',[first|dict(session_day='2026-11-18',observed_at='2026-11-18T02:05:00+00:00')])
    assert len(repo.read_observations('free',SECTOR['sector_id'],'2026-11-17'))==1


def test_daily_revisions_are_known_only_from_their_observation_cutoff(tmp_path):
    from src.repositories.a_share_sector_flow_repository import SectorFlowRepository
    from data_provider.a_share_sector_flow import normalize_history
    repo=SectorFlowRepository(create_engine('sqlite:///'+str(tmp_path/'f.db')))
    row=normalize_history(['2026-11-16,100,-20,-80,0,100,1,-.2,-.8,0,1,4000,2'],SECTOR,NOW)[0]
    repo.save_daily('free',[row])
    repo.save_daily('free',[row|dict(observed_at='2026-11-17T03:00:00+00:00',values=row['values']|dict(main=120.))])
    assert repo.read_daily('free',SECTOR['sector_id'],'2026-11-01','2026-11-16',as_of='2026-11-17T02:30:00+00:00')[0]['values']['main']==100
    assert repo.read_daily('free',SECTOR['sector_id'],'2026-11-01','2026-11-16')[0]['values']['main']==120
    assert repo.read_daily('free',SECTOR['sector_id'],'2026-11-01','2026-11-16',as_of='2026-11-17T02:00:00+00:00')==[]

def test_provisional_daily_observation_cannot_become_closed_by_waiting(tmp_path):
 from sqlalchemy import create_engine
 from src.repositories.a_share_sector_flow_repository import SectorFlowRepository
 from data_provider.a_share_sector_flow import normalize_history
 from tests.test_a_share_sector_flow_service import BOARD
 repo=SectorFlowRepository(create_engine('sqlite:///'+str(tmp_path/'provisional.db')))
 raw=['2026-11-17,'+','.join(['100']*10+['100','1'])]
 repo.save_daily('free',normalize_history(raw,BOARD,'2026-11-17T02:00:00+00:00'))
 # Merely moving the query clock beyond the close does not finalize the morning value.
 assert repo.read_daily('free',BOARD['sector_id'],'2026-11-17','2026-11-17',as_of='2026-11-17T09:00:00+00:00')==[]
 repo.save_daily('free',normalize_history(raw,BOARD,'2026-11-17T07:11:00+00:00'))
 assert len(repo.read_daily('free',BOARD['sector_id'],'2026-11-17','2026-11-17'))==1
 assert repo.read_daily('free',BOARD['sector_id'],'2026-11-17','2026-11-17',as_of='2026-11-17T07:00:00+00:00')==[]
