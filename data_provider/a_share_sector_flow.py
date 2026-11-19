"""Bounded Eastmoney adapters using the field semantics of AKShare stock_fund_em.

Public board identifiers are used directly: a concept and an industry with the
same name must never share history. Source timestamps absent from the response
stay absent; sampling time is not a trade timestamp.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import re
import time
from math import isfinite
import requests
from src.schemas.a_share_sector_flow import FlowPoint,CATEGORIES,utc_time

SOURCE='eastmoney/sector-flow'
RANK_FIELDS='f12,f14,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87'
NET=dict(main='f62',super='f66',large='f72',medium='f78',small='f84')
RATE=dict(main='f184',super='f69',large='f75',medium='f81',small='f87')


def number(value):
    if isinstance(value,bool):return None
    try:
        n=float(value)
        return n if isfinite(n) else None
    except (ValueError,TypeError):return None


def board_identity(sector):
    kind=sector['kind'];code=sector['code']
    if (kind not in ('industry','concept') or not re.fullmatch(r'BK\d{4}',code)
        or sector['sector_id']!='em:'+kind+':'+code or sector['classification']!='eastmoney-'+kind):
        raise ValueError('只支持同一东财代码的A股行业或概念资金流')
    return dict(sector_id=sector['sector_id'],kind=kind,classification=sector['classification'],name=sector['name'])


def snapshot(row,kind,observed_at):
    code=str(row.get('f12',''));name=str(row.get('f14') or '').strip()
    if not name or not re.fullmatch(r'BK\d{4}',code):raise ValueError('来源板块身份缺失')
    values={k:number(row.get(v)) for k,v in NET.items()}
    day=datetime.fromisoformat(observed_at.replace('Z','+00:00')).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
    return FlowPoint(sector_id='em:'+kind+':'+code,kind=kind,classification='eastmoney-'+kind,name=name,
        measure='cumulative_snapshot',observed_at=observed_at,session_day=day,values=values,
        ratios={k:(number(row.get(v))/100 if number(row.get(v)) is not None else None) for k,v in RATE.items()},
        change=number(row.get('f3'))/100 if number(row.get('f3')) is not None else None).model_dump()


def normalize_rank(rows,kind,observed_at):
    output=[];seen=set()
    for raw in rows:
        value=snapshot(raw,kind,observed_at)
        if value['sector_id'] in seen:raise ValueError('资金排行板块重复')
        seen.add(value['sector_id'])
        if any(n is not None for n in value['values'].values()):output.append(value)
    if not output:raise ValueError('未取得有效板块资金快照，保留原缓存')
    return output


def normalize_history(rows,sector,observed_at):
    identity=board_identity(sector);output=[];seen=set()
    keys=['main','small','medium','large','super']
    for row in rows:
        fields=row.split(',') if isinstance(row,str) else row
        if len(fields)<11:raise ValueError('资金历史字段不足')
        day=str(fields[0])[:10]
        if day in seen:raise ValueError('资金历史日期重复')
        seen.add(day)
        value=FlowPoint(**identity,measure='daily_net',observed_at=observed_at,session_day=day,source_date=day,
            date_quality='source_date',values={k:number(fields[i+1]) for i,k in enumerate(keys)},
            ratios={k:(number(fields[i+6])/100 if number(fields[i+6]) is not None else None) for i,k in enumerate(keys)},
            close=number(fields[11]) if len(fields)>11 else None,
            change=number(fields[12])/100 if len(fields)>12 and number(fields[12]) is not None else None).model_dump()
        output.append(value)
    if not output:raise ValueError('未取得日资金历史，保留原缓存')
    return sorted(output,key=lambda r:r['source_date'])


def normalize_members(rows,sector,observed_at):
    identity=board_identity(sector);output=[];seen=set()
    for raw in rows:
        code=str(raw.get('f12',''))
        if not re.fullmatch(r'\d{6}',code) or code in seen:raise ValueError('成分股资金身份无效或重复')
        seen.add(code)
        output.append(identity|dict(code=code,name=str(raw.get('f14') or code),board_name=identity['name'],source=SOURCE,unit='CNY',
            observed_at=utc_time(observed_at),source_time=None,source_date=None,
            values={k:number(raw.get(v)) for k,v in NET.items()},
            ratios={k:number(raw.get(v))/100 if number(raw.get(v)) is not None else None for k,v in RATE.items()}))
    if not output:raise ValueError('未取得成员资金快照，保留原缓存')
    return output


def _get(path,params,history=False,deadline=None):
    """One total 22-second budget, fixed hosts, no redirect or global proxy edits."""
    hosts=['push2his.eastmoney.com'] if history else ['push2.eastmoney.com','push2delay.eastmoney.com','push2his.eastmoney.com']
    deadline=deadline or time.monotonic()+22
    for host in hosts:
        for direct in (False,True):
            remaining=deadline-time.monotonic()
            if remaining<=0:raise ValueError('资金源调用超时')
            try:
                with requests.Session() as session:
                    session.trust_env=not direct
                    response=session.get('https://'+host+path,params=params,timeout=min(7,remaining),allow_redirects=False,
                        headers={'Referer':'https://data.eastmoney.com/','User-Agent':'Mozilla/5.0'})
                    response.raise_for_status();payload=response.json()
                if payload.get('rc')!=0 or not isinstance(payload.get('data'),dict):raise ValueError('资金源未返回有效数据')
                return payload['data']
            except requests.exceptions.ProxyError:
                if not direct:continue
            except (requests.RequestException,ValueError):
                # Do not retry a successful route without its environment proxy.
                break
    raise ValueError('资金源连接失败或无数据，保留缓存；没有生成替代资金值')


def _pages(scope):
    deadline=time.monotonic()+22;rows=[];seen=set();total=None
    for page in range(1,101):
        data=_get('/api/qt/clist/get',dict(pn=page,pz=100,po=1,np=1,fltt=2,invt=2,fid='f12',fs=scope,
            ut='b2884a393a59ad64002292a3e90d46a5',fields=RANK_FIELDS),deadline=deadline)
        count=data.get('total');batch=data.get('diff')
        if isinstance(batch,dict):batch=list(batch.values())
        if (not isinstance(count,int) or isinstance(count,bool) or not 0<count<=10000 or
            total is not None and count!=total or not isinstance(batch,list) or not batch):
            raise ValueError('资金分页覆盖缺失或变化，保留原缓存')
        total=count
        for row in batch:
            code=row.get('f12')
            if not code or code in seen:raise ValueError('资金分页代码重复')
            seen.add(code);rows.append(row)
        if len(rows)==total:return rows
        if len(rows)>total:break
    raise ValueError('资金分页覆盖不完整，保留原缓存')


def fetch_rank(kind):
    if kind not in ('industry','concept'):raise ValueError('板块类型无效')
    return _pages('m:90 t:'+('2' if kind=='industry' else '3'))


def fetch_history(symbol):
    if not re.fullmatch(r'BK\d{4}',symbol):raise ValueError('板块代码无效')
    data=_get('/api/qt/stock/fflow/daykline/get',dict(lmt=0,klt=101,secid='90.'+symbol,
        fields1='f1,f2,f3,f7',fields2='f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65'),history=True)
    if str(data.get('code'))!=symbol:raise ValueError('历史资金返回板块与请求不一致')
    return data.get('klines') or []


def fetch_members(symbol):
    if not re.fullmatch(r'BK\d{4}',symbol):raise ValueError('板块代码无效')
    return _pages('b:'+symbol)
