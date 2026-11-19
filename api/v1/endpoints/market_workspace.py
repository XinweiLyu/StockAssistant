"""Unified market workspace under the application's existing auth middleware."""
from datetime import date,timedelta
from threading import RLock
from typing import Literal
from urllib.parse import urlsplit
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,field_validator
from src.schemas.a_share_market import CatalogQuery,SectorQuery,HistoryPage
from src.schemas.a_share_value import PrepareValueRequest,GenerateValueRequest,SaveValueRequest,EvaluateValueRequest,SupplementValueRequest,ValueFact
from src.services.a_share_value_service import ValueConflict
from src.schemas.a_share_integrated import digest

Market=Literal['cn','hk','us']
router=APIRouter(prefix='/market-workspace')
_services={};_lock=RLock()


def service(market):
    from api.v1.endpoints.a_share import get_assistant_service
    from src.services.market_workspace_service import MarketWorkspaceService
    parent=get_assistant_service()
    if market=='cn':return parent.market
    key=(id(parent),market,parent.settings.mode)
    with _lock:
        for old in list(_services):
            if old[:2]==key[:2] and old!=key:_services.pop(old).stop()
        if key not in _services:
            svc=MarketWorkspaceService(parent,market);svc.initialize_research();svc.start();_services[key]=svc
        svc=_services[key]
        return svc


def stop_workspace_services():
    with _lock:
        for svc in _services.values():svc.stop()
        _services.clear()


def invoke(market,action):
    svc=service(market)
    with svc.assistant._settings_lock:
        try:return action(svc)
        except ValueConflict as exc:raise HTTPException(409,str(exc)) from exc
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc


def canonical(svc,code):
    if hasattr(svc,'identity'):return svc.identity(code).instrument_id
    import re
    if not re.fullmatch(r'\d{6}|DEMO\d{3}',code):raise ValueError('原A股工作区只接受A股证券代码')
    return code


def interval(svc,start,end):
    end=end or svc.completed_day()
    return start or (date.fromisoformat(end)-timedelta(days=365)).isoformat(),end


@router.get('/{market}/stocks')
def stocks(market:Market,query:CatalogQuery=Depends(),scope:Literal['all','candidates','watchlist']='all'):
    def read(s):
        if scope=='watchlist':codes=s.repo.get_state(s.profile,'watchlist',[]) if market!='cn' else s.assistant.settings.watchlist
        elif scope=='candidates':codes=[] if market!='cn' else [c['code'] for c in s.assistant.repo.latest(s.profile,'report',default={}).get('candidates',[])]
        else:codes=None
        return s.catalog(query,codes)
    return invoke(market,read)


@router.get('/{market}/stocks/{code}')
def stock(market:Market,code:str):return invoke(market,lambda s:s.stock(canonical(s,code)))


@router.get('/{market}/stocks/{code}/history')
def history(market:Market,code:str,start:str|None=None,end:str|None=None,adjust:Literal['raw','qfq']='qfq',refresh:bool=False):
    return invoke(market,lambda s:s.history(canonical(s,code),*interval(s,start,end),adjust,refresh))


@router.get('/{market}/stocks/{code}/live')
def live(market:Market,code:str):return invoke(market,lambda s:s.live_price(canonical(s,code)))


@router.post('/{market}/stocks/{code}/refresh')
def refresh(market:Market,code:str):return invoke(market,lambda s:s.refresh_price(canonical(s,code)))


@router.get('/{market}/stocks/{code}/outlook')
def outlook(market:Market,code:str,min_reward_risk:float=Query(2.,ge=1,le=5,allow_inf_nan=False),refresh:bool=False):
    return invoke(market,lambda s:s.assistant.quant_outlook(canonical(s,code),min_reward_risk,refresh))


@router.get('/{market}/stocks/{code}/scenarios')
def scenarios(market:Market,code:str):
    return invoke(market,lambda s:s.assistant.price_scenarios(canonical(s,code)) if market=='cn' else dict(status='insufficient',context=None,trade_levels=None,forecasts=[],message='港美股使用统一综合研究；旧版A股价位入口不适用'))


@router.get('/{market}/stocks/{code}/integrated-research')
def integrated(market:Market,code:str):return invoke(market,lambda s:s.assistant.integrated.get(canonical(s,code)))


@router.post('/{market}/stocks/{code}/research-data')
def prepare(market:Market,code:str,peer_offset:int=Query(0,ge=0,le=500)):
    return invoke(market,lambda s:s.assistant.integrated.prepare(canonical(s,code),peer_offset))


@router.post('/{market}/stocks/{code}/integrated-research')
def generate(market:Market,code:str,force:bool=False):return invoke(market,lambda s:s.assistant.integrated.generate(canonical(s,code),force))


@router.get('/{market}/stocks/{code}/research-validation')
def validation(market:Market,code:str):return invoke(market,lambda s:s.assistant.integrated.validation(canonical(s,code)))


@router.get('/{market}/stocks/{code}/value-research')
def value(market:Market,code:str):return invoke(market,lambda s:s.assistant.value.get(canonical(s,code)))


@router.post('/{market}/stocks/{code}/value-data')
def prepare_value(market:Market,code:str,body:PrepareValueRequest):
    return invoke(market,lambda s:s.assistant.value.prepare(canonical(s,code),body.peer_offset,body.refresh))


@router.post('/{market}/stocks/{code}/value-research')
def generate_value(market:Market,code:str,body:GenerateValueRequest):
    return invoke(market,lambda s:s.assistant.value.generate(canonical(s,code),body))


@router.put('/{market}/stocks/{code}/value-assumptions')
def assumptions(market:Market,code:str,body:SaveValueRequest):
    return invoke(market,lambda s:s.assistant.value.save_assumptions(canonical(s,code),body))


@router.post('/{market}/stocks/{code}/value-evaluate')
def evaluate(market:Market,code:str,body:EvaluateValueRequest):
    return invoke(market,lambda s:s.assistant.value.evaluate(canonical(s,code),body))


@router.post('/{market}/stocks/{code}/value-supplement')
def supplement(market:Market,code:str,body:SupplementValueRequest):
    return invoke(market,lambda s:s.assistant.value.supplement(canonical(s,code),body))


@router.get('/{market}/sectors')
def sectors(market:Market,kind:Literal['industry','concept']='industry',period:int=Query(0,ge=0,le=60),classification:str|None=None):
    return invoke(market,lambda s:s.sectors(SectorQuery(kind=kind,period=period,classification=classification)))


@router.get('/{market}/sectors/{sector_id}/members')
def members(market:Market,sector_id:str,query:CatalogQuery=Depends(),refresh:bool=False):
    return invoke(market,lambda s:s.members(sector_id,query,refresh))


@router.get('/{market}/sectors/{sector_id}/history')
def sector_history(market:Market,sector_id:str,start:str|None=None,end:str|None=None):
    def read(s):
        a,b=interval(s,start,end)
        if market=='cn':return s.sector_history(sector_id,a,b)
        return HistoryPage(code=sector_id,requested_start=a,requested_end=b,adjust='raw',state='partial',limitations=['此分类未取得独立行业指数历史，不以成分股均值冒充指数'])
    return invoke(market,read)


@router.get('/{market}/benchmark/history')
def benchmark(market:Market,start:str|None=None,end:str|None=None):return invoke(market,lambda s:s.benchmark_history(*interval(s,start,end)))


@router.get('/{market}/jobs')
def jobs(market:Market):return invoke(market,lambda s:s.repo.progress(s.profile)|dict(coverage=s.coverage(),health=s.repo.states_with_prefix(s.profile,'health:')))


@router.post('/{market}/warmup')
def warmup(market:Market):return invoke(market,lambda s:s.warmup() if market=='cn' else (s.bootstrap() or dict(accepted=True,message='目录已准备；按需获取选中证券，避免全市场抓取成本')))


@router.post('/{market}/jobs/{action}')
def pause(market:Market,action:Literal['pause','resume']):
    def run(s):s.repo.pause(s.profile,action=='pause');return s.repo.progress(s.profile)
    return invoke(market,run)


@router.get('/{market}/watchlist')
def watchlist(market:Market):return invoke(market,lambda s:dict(codes=s.repo.get_state(s.profile,'watchlist',[]) if market!='cn' else s.assistant.settings.watchlist))


def change_watchlist(s,market,code,add):
    code=canonical(s,code)
    current=s.repo.get_state(s.profile,'watchlist',[]) if market!='cn' else list(s.assistant.settings.watchlist)
    result=list(dict.fromkeys(current+[code])) if add else [c for c in current if c!=code]
    if len(result)>50:raise ValueError('每个市场最多保存50只自选')
    if market=='cn':s.assistant.save_settings(s.assistant.settings.model_copy(update={'watchlist':result}))
    else:s.repo.set_state(s.profile,'watchlist',result)
    return dict(codes=result)


@router.post('/{market}/watchlist/{code}')
def add_watchlist(market:Market,code:str):return invoke(market,lambda s:change_watchlist(s,market,code,True))


@router.delete('/{market}/watchlist/{code}')
def remove_watchlist(market:Market,code:str):return invoke(market,lambda s:change_watchlist(s,market,code,False))


class ListingSupplement(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    confirmed:Literal[True]
    underlying_per_listed:float=Field(gt=0,le=1000000)
    effective_date:str
    verified_through:str
    issued_shares:float|None=Field(None,gt=0)
    url:str=Field(max_length=2000)
    quote:str=Field(min_length=3,max_length=2000)
    reason:str=Field(min_length=3,max_length=1000)
    @field_validator('effective_date','verified_through')
    @classmethod
    def day(cls,value):return date.fromisoformat(value).isoformat()
    @field_validator('url')
    @classmethod
    def public_url(cls,value):
        url=urlsplit(value)
        if url.scheme not in ('http','https') or not url.hostname or url.username:raise ValueError('需要公开原文网址')
        return value


@router.put('/{market}/stocks/{code}/listing-binding')
def save_binding(market:Market,code:str,body:ListingSupplement):
    def write(s):
        if market=='cn':raise ValueError('A股沿用原股本补录流程')
        code_key=canonical(s,code);stock=s.stock(code_key);now=s.clock().isoformat();anchor=(stock.get('quote') or {}).get('trade_date') or s.completed_day()
        if not body.effective_date<=body.verified_through<=now[:10]:raise ValueError('股权生效、核实覆盖日期须先后有序且不在未来')
        evidence_id='LISTING'+digest([code_key,body.model_dump()])[:20]
        from src.services.market_workspace_financials import fetch_fx
        native=s.value_metadata(code_key)['currency']
        if native=='XXX':raise ValueError('财报原币种尚未核实，请先准备研究资料')
        fx=fetch_fx(native,stock.get('currency'),anchor) if native and stock.get('currency') else None
        capital=dict(underlying_per_listed=body.underlying_per_listed,effective_date=body.effective_date,
            verified_through=body.verified_through,sources=[evidence_id],confirmed=True,url=body.url,quote=body.quote,reason=body.reason)
        s.repo.set_state(s.profile,'listing-binding:'+code_key,dict(capital=capital,fx=fx,observed_at=now))
        s.assistant.repo.append(s.profile,'listing_attestation',s.profile+':'+code_key,body.model_dump()|dict(id=evidence_id,observed_at=now))
        if body.issued_shares is not None:
            current=ValueFact(code=code_key,market=market,currency=native,metric='current_shares',value=body.issued_shares,unit='shares',
                period_basis='instant',report_period=body.effective_date,period_end=body.effective_date,scope='consolidated',attribution='parent_common',
                published_at=None,observed_at=now,available_at=now,source='user/listing_attestation',raw_field='issued_shares',content_hash=digest(body.model_dump()),
                fact_id=evidence_id,url=body.url,quote=body.quote,vintage_quality='user_attested').model_dump()
            key=s.profile+':'+code_key;existing=s.assistant.repo.latest(s.profile,'value_supplements',key=key,default=[])
            s.assistant.repo.append(s.profile,'value_supplements',key,[f for f in existing if f.get('source')!='user/listing_attestation']+[current])
        return dict(saved=True,message='股权/汇率核实已留痕；更新价值资料后按新版本计算，不调用AI')
    return invoke(market,write)
