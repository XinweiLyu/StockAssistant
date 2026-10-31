"""Paged, cached market API under the original assistant authentication boundary."""
from datetime import date, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from src.schemas.a_share_market import CatalogQuery, SectorQuery

router=APIRouter(prefix='/market')

def service():
    from api.v1.endpoints.a_share import get_assistant_service
    return get_assistant_service()

def invoke(fn,missing=False):
    svc=service()
    with svc._settings_lock:
        try: return fn(svc)
        except ValueError as exc: raise HTTPException(404 if missing else 422,str(exc)) from exc

def dates(svc,start,end):
    end=end or svc.market.completed_day()
    start=start or (date.fromisoformat(end)-timedelta(days=365)).isoformat()
    return start,end

@router.get('/stocks')
def stocks(query:CatalogQuery=Depends(),scope:Literal['all','candidates','watchlist']='all'):
    def read(s):
        codes=s.settings.watchlist if scope=='watchlist' else [c['code'] for c in s.repo.latest(s.settings.mode,'report',default={}).get('candidates',[])] if scope=='candidates' else None
        return s.market.catalog(query,codes)
    return invoke(read)

@router.get('/stocks/{code}')
def stock(code:str):
    return invoke(lambda s:s.market.stock(code),True)

@router.get('/stocks/{code}/history')
def history(code:str,start:str|None=None,end:str|None=None,adjust:Literal['raw','qfq']='qfq',refresh:bool=False):
    return invoke(lambda s:s.market.history(code,*dates(s,start,end),adjust,refresh))

@router.get('/stocks/{code}/live')
def live(code:str):
    return invoke(lambda s:s.market.live_price(code),True)

@router.post('/stocks/{code}/refresh')
def refresh_stock_price(code:str):
    return invoke(lambda s:s.market.refresh_price(code),True)

@router.get('/stocks/{code}/scenarios')
def scenarios(code:str):
    def read(s):
        s.market.stock(code)
        return s.price_scenarios(code)
    return invoke(read,True)

@router.get('/stocks/{code}/outlook')
def outlook(code:str,min_reward_risk:float=Query(2.0,ge=1,le=5,allow_inf_nan=False),refresh:bool=False):
    return invoke(lambda s:s.quant_outlook(code,min_reward_risk,refresh),True)


@router.get('/stocks/{code}/integrated-research')
def integrated_research(code:str):
    return invoke(lambda s:s.integrated.get(code),True)


@router.post('/stocks/{code}/research-data')
def prepare_research_data(code:str,peer_offset:int=Query(0,ge=0,le=500)):
    return invoke(lambda s:s.integrated.prepare(code,peer_offset),True)


@router.post('/stocks/{code}/integrated-research')
def generate_integrated_research(code:str,force:bool=False):
    return invoke(lambda s:s.integrated.generate(code,force),True)


@router.get('/stocks/{code}/research-validation')
def integrated_validation(code:str):
    return invoke(lambda s:s.integrated.validation(code),True)

@router.get('/sectors')
def sectors(kind:Literal['industry','concept']='industry',classification:str|None=None,period:int=0):
    if period not in (0,5,20,60): raise HTTPException(422,'期间仅支持0/5/20/60交易日')
    return invoke(lambda s:s.market.sectors(SectorQuery(kind=kind,classification=classification,period=period)))

@router.get('/sectors/{sector_id}/members')
def members(sector_id:str,query:CatalogQuery=Depends(),refresh:bool=False):
    return invoke(lambda s:s.market.members(sector_id,query,refresh=refresh),True)

@router.get('/sectors/{sector_id}/history')
def sector_history(sector_id:str,start:str|None=None,end:str|None=None,refresh:bool=False):
    return invoke(lambda s:s.market.sector_history(sector_id,*dates(s,start,end),refresh))

@router.get('/benchmark/history')
def benchmark(start:str|None=None,end:str|None=None,refresh:bool=False):
    return invoke(lambda s:s.market.benchmark_history(*dates(s,start,end),refresh))

@router.get('/jobs')
def jobs():
    return invoke(lambda s:s.market.repo.progress(s.settings.mode)|dict(coverage=s.market.coverage(),health=s.market.repo.states_with_prefix(s.settings.mode,'health:')))

@router.post('/warmup')
def warmup():
    return invoke(lambda s:s.market.warmup())

@router.post('/jobs/pause')
def pause():
    return invoke(lambda s:paused(s,True))

@router.post('/jobs/resume')
def resume():
    return invoke(lambda s:paused(s,False))

def paused(s,value):
    s.market.repo.pause(s.settings.mode,value)
    return s.market.repo.progress(s.settings.mode)


from api.v1.endpoints.a_share_value import router as value_router
router.include_router(value_router)
