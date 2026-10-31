"""Capability scoped adapters. Bounded subprocesses isolate upstream crawler hangs.

The DSA data providers continue serving its existing features. These adapters add
strict provenance and entitlements for the versioned assistant rules.
"""
from __future__ import annotations
import json
import subprocess
import sys
import time
import threading
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from math import isfinite

ALLOWED = {'stock_zh_a_spot_em','stock_zh_a_hist','stock_individual_info_em',
           'stock_board_industry_name_em','stock_board_industry_hist_em',
           'stock_info_global_em','stock_news_em','stock_notice_report','tool_trade_date_hist_sina',
           'stock_zh_index_daily_em','stock_zh_a_spot_tx','stock_zh_a_spot',
           'stock_zh_a_daily','stock_zh_a_hist_tx','stock_info_sh_name_code','stock_info_sz_name_code'}
ALLOWED |= {'stock_info_a_code_name','stock_info_bj_name_code','stock_board_industry_cons_em',
            'stock_board_concept_name_em','stock_board_concept_cons_em','stock_board_concept_hist_em',
            'stock_board_industry_name_ths','stock_board_industry_index_ths',
            'stock_board_concept_name_ths','stock_board_concept_index_ths'}
TS_ALLOWED = {'daily','adj_factor','stock_basic','trade_cal','daily_basic','rt_k','news','anns_d','stk_limit','suspend_d'}
ALLOWED |= {'stock_financial_analysis_indicator_em', 'stock_profit_sheet_by_report_em',
            'stock_balance_sheet_by_report_em', 'stock_cash_flow_sheet_by_report_em',
            'stock_zh_a_disclosure_report_cninfo', 'stock_value_em', 'stock_fhps_detail_em'}
TS_ALLOWED |= {'fina_indicator', 'income', 'cashflow', 'balancesheet', 'dividend'}


def permitted_sources(settings):
    return dict(daily='tushare' if settings.mode.startswith('tushare') else 'akshare',
                snapshot='tushare' if settings.snapshot_provider=='tushare' and settings.realtime_entitled else 'akshare',
                news='tushare' if settings.news_entitled else 'akshare',
                announcements='tushare' if settings.announcements_entitled else 'akshare',
                sector='akshare')


def number(value):
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (ValueError,TypeError):
        return None


def normalize_spot(row, fetched_at):
    vol = number(row.get('成交量'))
    return dict(code=str(row['代码']).zfill(6),name=str(row.get('名称','')),
                price=number(row.get('最新价')),volume=vol*100 if vol is not None else None,
                amount=number(row.get('成交额')),source='akshare/eastmoney',raw_volume_unit='手',
                source_time=None,fetched_at=fetched_at,trade_date=None,
                suspended=None,limit_up=None,limit_down=None)


def normalize_alternate_spot(row,fetched_at,source):
    if source=='akshare/sina':
        q=normalize_spot(row,fetched_at)
        q['code']=q['code'].removeprefix('sh').removeprefix('sz').removeprefix('bj')
        q['volume']=number(row.get('成交量'))  # Sina lists shares, not hands.
    else:
        code=str(row.get('code','')).removeprefix('sh').removeprefix('sz').removeprefix('bj')
        q=dict(code=code,name=row.get('name'),price=number(row.get('price',row.get('zxj'))),amount=None,
               download_sort_value=number(row.get('turnover')),raw_amount=row.get('turnover'),raw_amount_unit='unknown',
               volume=None,source_time=None,trade_date=None,suspended=None,limit_up=None,limit_down=None,
               raw_volume=row.get('volume'),raw_volume_unit='unknown',fetched_at=fetched_at)
    q['source']=source
    return q


def normalize_tushare_quote(row, fetched_at):
    timestamp=row.get('trade_time')
    stamp=None
    if timestamp:
        try:
            parsed=datetime.fromisoformat(str(timestamp))
            parsed=parsed.replace(tzinfo=ZoneInfo('Asia/Shanghai')) if parsed.tzinfo is None else parsed.astimezone(ZoneInfo('Asia/Shanghai'))
            stamp=parsed.isoformat()
        except ValueError:
            pass
    return dict(code=row['ts_code'][:6],name=row.get('name'),price=number(row.get('close')),volume=number(row.get('vol')),
                amount=number(row.get('amount')),source_time=stamp,trade_date=stamp[:10] if stamp else None,
                source='tushare/rt_k',fetched_at=fetched_at,suspended=None,limit_up=None,limit_down=None)


def daily_rows(raw, adjusted=None, tushare=False):
    adjusted_map = {str(r.get('日期',r.get('date')))[:10]:number(r.get('收盘',r.get('close'))) for r in adjusted or []}
    result = []
    for r in raw:
        if tushare:
            d = str(r['trade_date'])
            day = f'{d[:4]}-{d[4:6]}-{d[6:8]}'
            factor = number(r.get('adj_factor'))
            result.append(dict(date=day,close=number(r.get('close')),high=number(r.get('high')),
                               low=number(r.get('low')),amount=(number(r.get('amount')) or 0)*1000,
                               volume=(number(r.get('vol')) or 0)*100,
                               adjusted_close=number(r.get('close'))*factor if factor and number(r.get('close')) else None))
        else:
            day = str(r.get('日期',r.get('date','')))[:10]
            close = number(r.get('收盘',r.get('close')))
            result.append(dict(date=day,close=close,high=number(r.get('最高',r.get('high'))),
                               low=number(r.get('最低',r.get('low'))),amount=number(r.get('成交额',r.get('amount'))),
                               volume=number(r.get('成交量'))*100 if number(r.get('成交量')) is not None else number(r.get('volume')),
                               adjusted_close=adjusted_map.get(day) if adjusted is not None else close))
    return sorted(result,key=lambda r:r['date'])


class CapabilityProvider:
    _source_locks={'akshare':threading.RLock(),'tushare':threading.RLock()}
    _source_started={'akshare':0.,'tushare':0.}
    def __init__(self, token='', timeout=40):
        self.token=token
        self.timeout=timeout
        self._last_request=0.
        self.failures={}

    def call(self, name, params=None, tushare=False):
        family='tushare' if tushare else 'akshare'
        with self._source_locks[family]:
            time.sleep(max(0,1.-(time.monotonic()-self._source_started[family])))
            self._source_started[family]=time.monotonic()
            return self._call_locked(name,params,tushare)

    def _call_locked(self, name, params=None, tushare=False):
        key=('tushare:' if tushare else 'akshare:')+name
        request_key=key+':'+hashlib.sha256(json.dumps(params or {},sort_keys=True).encode()).hexdigest()
        blocked = self.failures.get(key) or self.failures.get(request_key)
        if blocked and time.monotonic()<blocked[0]:
            raise RuntimeError('接口冷却中：'+blocked[1])
        if name not in (TS_ALLOWED if tushare else ALLOWED):
            raise ValueError('不允许的接口')
        if tushare and not self.token:
            raise ValueError('Tushare Token未配置')
        time.sleep(max(0,1.-(time.monotonic()-self._last_request)))
        self._last_request=time.monotonic()
        request=dict(name=name,params=params or {},tushare=tushare,token=self.token if tushare else '')
        try:
            result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--request'],
                                  input=json.dumps(request),capture_output=True,text=True,timeout=self.timeout,check=True)
            return json.loads(result.stdout)
        except (subprocess.SubprocessError,ValueError) as exc:
            # Never include subprocess input/token in errors or stdout responses.
            message='上游接口超时或返回结构错误'
            error_type=None
            if isinstance(exc,subprocess.CalledProcessError):
                try:
                    error=json.loads(exc.stdout)
                    message=error.get('error',message)
                    error_type=error.get('error_type')
                except (ValueError,TypeError):
                    pass
            message=message.replace(self.token,'[redacted]') if self.token else message
            cooldown_key=request_key if error_type in ('KeyError','IndexError','TypeError') else key
            self.failures[cooldown_key]=(time.monotonic()+900,message[:300])
            raise RuntimeError(message[:300]) from None


if __name__=='__main__' and '--request' in sys.argv:
    request=json.loads(sys.stdin.read())
    try:
        if request['tushare']:
            import requests
            if request['name'] not in TS_ALLOWED:
                raise ValueError('接口不在允许列表')
            params=dict(request['params'])
            fields=params.pop('fields','')
            response=requests.post('https://api.tushare.pro',json=dict(api_name=request['name'],token=request['token'],params=params,fields=fields),timeout=30,allow_redirects=False)
            response.raise_for_status()
            payload=response.json()
            if payload.get('code')!=0:
                raise ValueError(str(payload.get('msg') or '权限或服务错误'))
            data=payload['data']
            print(json.dumps([dict(zip(data['fields'],r)) for r in data['items']],ensure_ascii=False))
            sys.exit(0)
        else:
            import akshare as ak
            if request['name'] not in ALLOWED:
                raise ValueError('接口不在允许列表')
            df=getattr(ak,request['name'])(**request['params'])
        print(df.to_json(orient='records',date_format='iso',force_ascii=False))
    except Exception as exc:
        message=str(exc).replace(request.get('token') or '\0','[redacted]')
        print(json.dumps({'error':message[:300],'error_type':type(exc).__name__},ensure_ascii=False))
        sys.exit(1)
