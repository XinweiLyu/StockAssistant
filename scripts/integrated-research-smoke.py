#!/usr/bin/env python3
"""Inspect live integrated research; paid generation requires an explicit flag."""
import argparse
import json
import os
import sys
import time
from urllib.parse import urlsplit
import requests


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--code',default='000807')
    parser.add_argument('--base-url',default='http://127.0.0.1:8000')
    parser.add_argument('--prepare',action='store_true',help='Explicitly prepare source data without AI')
    parser.add_argument('--generate',action='store_true',help='Explicitly start at most one paid research run')
    parser.add_argument('--force',action='store_true',help='Regenerate even if a matching complete cache exists')
    parser.add_argument('--timeout',type=int,default=1200)
    args=parser.parse_args()
    parsed=urlsplit(args.base_url)
    if not args.code.isdigit() or len(args.code)!=6 or parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
        parser.error('Use a six-digit stock code and an HTTP(S) service URL without credentials')
    if args.force and not args.generate:
        parser.error('--force requires --generate')
    if not 15<=args.timeout<=3600:
        parser.error('--timeout must be 15..3600 seconds')
    session=requests.Session()
    # Optional existing local login; never printed or written by this script.
    if os.environ.get('DSA_SMOKE_COOKIE'):
        session.headers['Cookie']=os.environ['DSA_SMOKE_COOKIE']
    endpoint=args.base_url.rstrip('/')+'/api/v1/a-share/market/stocks/'+args.code
    deadline=time.monotonic()+args.timeout
    def request(method,path):
        response=session.request(method,endpoint+path,timeout=20)
        response.raise_for_status()
        return response.json()
    def wait(states):
        previous=None
        read_failures=0
        while True:
            try:
                result=request('GET','/integrated-research')
                read_failures=0
            except requests.ConnectionError:
                read_failures+=1
                if read_failures>=3 or time.monotonic()>deadline:
                    raise
                print(json.dumps(dict(status='read_retry',attempt=read_failures)),flush=True)
                time.sleep(5)
                continue
            progress=result.get('progress') or {}
            marker=(result['status'],progress.get('completed'),progress.get('current'))
            if marker!=previous:
                print(json.dumps(dict(status=result['status'],progress=progress),ensure_ascii=False),flush=True)
                previous=marker
            if result['status'] not in states:
                return result
            if time.monotonic()>deadline:
                raise TimeoutError('Research is still running; no second request was started')
            time.sleep(5)
    if args.prepare:
        action=request('POST','/research-data')
        print(json.dumps({k:action.get(k) for k in ('accepted','status','task_id')},ensure_ascii=False),flush=True)
        state=wait({'preparing'})
        if state['status'] in ('failed','waiting_history','missing'):
            print(json.dumps(dict(status=state['status'],message=state.get('message')),ensure_ascii=False))
            return 2
    if args.generate:
        action=request('POST','/integrated-research?force='+str(args.force).lower())
        print(json.dumps({k:action.get(k) for k in ('accepted','status','expected_calls','cached')},ensure_ascii=False),flush=True)
        if action['status'] not in ('ready','running'):
            return 2
    result=wait({'running','preparing'} if args.prepare or args.generate else set())
    bundle,report=result.get('bundle') or {},result.get('report') or {}
    summary=dict(code=args.code,status=result['status'],data_hash=bundle.get('data_hash'),
        anchor_date=bundle.get('anchor_date'),cutoff=bundle.get('cutoff'),coverage=bundle.get('coverage'),
        missing=bundle.get('missing'),report_status=report.get('status'),stale=report.get('stale',False),
        calls=report.get('calls'),roles=[dict(role=r['role'],status=r['status']) for r in report.get('roles',[])],
        forecasts=len(report.get('forecasts',[])),plans=len(report.get('plans',[])),
        rejections=report.get('rejections',[]),validation=result.get('validation'))
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
    if args.generate and (report.get('stale') or not report.get('forecasts') or any(r['status']=='failed' for r in report.get('roles',[]))):
        return 2
    return 0


if __name__=='__main__':
    try:
        sys.exit(main())
    except (requests.RequestException,ValueError,KeyError,TimeoutError) as exc:
        print(json.dumps(dict(status='failed',error=type(exc).__name__)),file=sys.stderr)
        sys.exit(2)
