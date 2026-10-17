"""Append-only A-share assistant API; protected by DSA's existing auth middleware."""
import csv
import io
import re
import time
from threading import Lock
from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from src.schemas.a_share import AssistantSettings, VerifyEvent, HoldingConstraint
from src.services.a_share_service import get_assistant_service
from data_provider.base import DataFetcherManager

router=APIRouter()


_chip_cache = {}
_chip_cache_lock = Lock()


@router.get('/chip/{code}')
def current_chip(code: str):
    """Read current chip data without launching a model run or changing reports."""
    if not re.fullmatch(r"[036]\d{5}", code):
        raise HTTPException(422, "仅支持沪深 A 股六位股票代码")
    now = time.monotonic()
    with _chip_cache_lock:
        cached = _chip_cache.get(code)
        if cached is not None and cached[0] > now:
            return cached[1]
    chip = DataFetcherManager().get_chip_distribution(code)
    payload = {"status": "available", "chip": chip.to_dict()} if chip else {"status": "missing", "chip": None}
    with _chip_cache_lock:
        if len(_chip_cache) >= 512:
            _chip_cache.clear()
        _chip_cache[code] = (time.monotonic() + (300 if chip else 30), payload)
    return payload


@router.get('/dashboard')
def dashboard():
    return get_assistant_service().dashboard()


@router.put('/settings')
def settings(value:AssistantSettings):
    try:
        return get_assistant_service().save_settings(value)
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from exc


@router.post('/sync')
def sync(kind:Literal['daily','snapshot','news']='daily'):
    accepted=get_assistant_service().sync_async(kind)
    return dict(accepted=accepted,job=get_assistant_service().job)


@router.post('/check')
def check():
    return get_assistant_service().check()


@router.post('/events/{event_id}/verify')
def verify(event_id:int,value:VerifyEvent):
    try:
        get_assistant_service().verify_event(event_id,value.model_dump())
        get_assistant_service().check()
        return dict(saved=True)
    except ValueError as exc:
        raise HTTPException(404,str(exc)) from exc


@router.post('/holdings/constraints')
def constraint(value:HoldingConstraint):
    try:
        get_assistant_service().confirm_holding(value.model_dump())
        get_assistant_service().check()
        return dict(saved=True)
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from exc


@router.get('/observations')
def observations():
    return dict(items=get_assistant_service().observations(),kind='候选价格观察，非组合收益')


@router.get('/stocks/{code}')
def stock(code:str):
    svc=get_assistant_service()
    data=svc.repo.latest(svc.settings.mode,'dataset',default={})
    value=next((s for s in data.get('stocks',[]) if s['code']==code),None) or svc.stock_data(code)
    if value is None:
        raise HTTPException(404,'当前数据集没有该股票')
    return value


@router.post('/research/{code}')
def research(code:str,include_price_scenarios:bool=False):
    try:
        return get_assistant_service().research_async(code,include_price_scenarios=include_price_scenarios)
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from exc


def spreadsheet_cell(value):
    value=str(value if value is not None else '')
    return "'"+value if value.lstrip().startswith(('=','+','-','@')) or value.startswith(('\t','\r')) else value


@router.get('/export')
def export(format:Literal['markdown','csv']='markdown',report_id:int|None=Query(None,gt=0)):
    svc=get_assistant_service()
    board=svc.dashboard()
    report=board['report']
    if report_id:
        row=next((r for r in svc.repo.records(svc.settings.mode,'report',limit=10000) if r['id']==report_id),None)
        report=row['payload'] if row else None
    if not report:
        raise HTTPException(409,'请先同步并生成研究报告')
    if format=='csv':
        buffer=io.StringIO()
        writer=csv.writer(buffer)
        writer.writerow(['代码','名称','规则','得分','数据日期','有效日期','突破价','本次计划参考价','计划股数','止损参考','检查状态','演示'])
        for c in report['candidates']:
            writer.writerow([spreadsheet_cell(v) for v in [c['code'],c['name'],c['strategy'],c['score'],
                             report['as_of'],c.get('valid_date'),c['high'],c.get('plan',{}).get('entry'),c.get('plan',{}).get('quantity'),
                             c.get('plan',{}).get('stop'),c.get('check',{}).get('status','observe'),report['demo']]])
        content='\ufeff'+buffer.getvalue()
        suffix='csv'
        media='text/csv; charset=utf-8'
    else:
        lines=['# A股交易助手研究报告',f"模式：{'虚构演示' if report['demo'] else '真实资料研究'}",
               f"数据截止：{report['as_of']}；生成：{report['generated_at']}",
               f"来源：{report['source']}；输入校验：{report['input_hash']}",
               f"市场条件：{report['market_ok']}；同日样本：{report['sample_size']}",
               '\n## 候选条件（不是成交）','|股票|规则|得分|突破观察价|本次计划参考价|计划股数|止损参考|有效日期|状态|','|---|---|---|---|---|---|---|---|---|']
        lines += [f"|{c['code']} {c['name']}|{c['strategy']}|{c['score']}|{c['high']:.2f}|{c.get('plan',{}).get('entry','待检查')}|{c.get('plan',{}).get('quantity','资料不足')}|{c.get('plan',{}).get('stop','待检查')}|{c.get('valid_date')}|{c.get('check',{}).get('status','observe')}|" for c in report['candidates']]
        lines += ['\n## 行业观察']+[f"- {s['name']}：强度 {s.get('strength','不足行业样本')}" for s in report['sectors']]
        lines += ['\n## 当时已获取的资讯证据']+[f"- {e['payload']['title']}；{e['payload']['source']}；首次发现 {e['payload']['first_seen']}；事件版本ID {e['id']}" for e in report.get('evidence',[])]
        lines += ['\n## 配置与局限','```json',__import__('json').dumps(report['config'],ensure_ascii=False,indent=2),'```']
        lines += ['- '+s for s in report['limitations']]
        if not report_id:
            lines += ['\n## 当前持仓检查']+[f"- {h['code']}：{h['action']}；{'；'.join(h['reasons'])}" for h in board['holdings']]
            lines += ['\n## 当前资讯证据（不属于旧报告的历史证据）']+[f"- [{e['payload']['title']}]({e['payload'].get('url') or ''})；{e['payload']['source']}；首次发现 {e['payload']['first_seen']}；修订 {e['payload']['revision']}" for e in board['events'][:30]]
            lines += ['\n## 当前数据状态']+[f"- {h['kind']}：{h['status']}；{h['fetched_at']}；{h.get('error','')}" for h in board['health']]
        content='\n'.join(lines)+'\n'
        suffix='md'
        media='text/markdown; charset=utf-8'
    return Response(content,media_type=media,headers={'Content-Disposition':f'attachment; filename="a-share-{report["as_of"]}.{suffix}"'})


from api.v1.endpoints.a_share_market import router as market_router
router.include_router(market_router)
