"""Validate cited estimates, never infer numeric prices from free text."""
import re
from math import isfinite
from pydantic import ValidationError
from src.schemas.a_share_price_scenarios import PriceContext, AITradeLevels, PriceForecast

UNSAFE = re.compile(r'仓位|股数|加仓|清仓|立即|下单|保证|胜率|必涨|稳赚|\b(?:order|quantity|guarantee|probability)\b',re.I)
FINANCIAL = re.compile(r'估值|市盈率|财报|EPS|\bPE\b',re.I)

def validate_price_scenarios(value, allowed, context):
    result=dict(trade_levels=None,forecasts=[],rejected=0,status='insufficient')
    try: PriceContext.model_validate(context)
    except (ValidationError,TypeError): return result|{'rejected':1}
    if not isinstance(value,dict) or set(value)-{'trade_levels','forecasts'}:
        return result|{'rejected':1}
    def accept(item, cls):
        try:
            parsed=cls.model_validate(item)
            refs=parsed.sources
            text=' '.join(parsed.conditions+getattr(parsed,'invalidation',[]))
            if 'P1' not in allowed or 'P1' not in refs or any(s not in allowed for s in refs): raise ValueError('uncited price facts')
            if any(not t.strip() or len(t)>600 for t in parsed.conditions+getattr(parsed,'invalidation',[])) or UNSAFE.search(text): raise ValueError('action text')
            if FINANCIAL.search(text) and not any(s.startswith('F') for s in refs): raise ValueError('missing financial evidence')
            return parsed.model_dump()
        except (ValidationError,ValueError,TypeError):
            result['rejected']+=1
            return None
    if value.get('trade_levels') is not None:
        result['trade_levels']=accept(value['trade_levels'],AITradeLevels)
    forecasts=value.get('forecasts',[])
    if not isinstance(forecasts,list): forecasts=[];result['rejected']+=1
    seen=set()
    for item in forecasts[:9]:
        parsed=accept(item,PriceForecast)
        if parsed:
            key=(parsed['horizon_sessions'],parsed['scenario'])
            if key in seen: result['rejected']+=1;continue
            seen.add(key);result['forecasts'].append(parsed)
    result['rejected']+=max(0,len(forecasts)-9)
    for horizon in (5,10,20):
        group=sorted((f for f in result['forecasts'] if f['horizon_sessions']==horizon),key=lambda f:['bear','base','bull'].index(f['scenario']))
        centers=[(f['low']+f['high'])/2 for f in group]
        if centers!=sorted(centers):
            result['forecasts']=[f for f in result['forecasts'] if f['horizon_sessions']!=horizon]
            result['rejected']+=len(group)
    if result['trade_levels'] or result['forecasts']:
        result['status']='partial' if result['rejected'] else 'ready'
    return result

def map_level_to_chart(price,raw_anchor,qfq_anchor,adjust):
    valid=lambda v:isinstance(v,(int,float)) and not isinstance(v,bool) and isfinite(v) and v>0
    if not valid(price): return None
    if adjust=='raw': return price
    if adjust!='qfq' or not valid(raw_anchor) or not valid(qfq_anchor): return None
    return price*qfq_anchor/raw_anchor
