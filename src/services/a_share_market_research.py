"""Bridge the market cache into the existing rules and immutable research journal."""
from datetime import date, timedelta
import hashlib
import json
from src.services.a_share_rules import rank_universe, validate_daily
from src.schemas.a_share_market import SectorQuery
from src.services.a_share_market_service import price_family
from src.services.a_share_market_jobs import Deferred


class MarketResearch:
    def __init__(self,assistant):
        self.assistant=assistant

    def stock(self,profile,code,as_of=None):
        market=self.assistant.market
        as_of=as_of or market.completed_day(profile)
        meta=market.repo.stock(profile,code)
        if not meta:
            return None
        raw=market.repo.get_history(profile,'stock:'+code,'raw','1900-01-01',as_of)
        adjusted=market.repo.get_history(profile,'stock:'+code,'qfq','1900-01-01',as_of)
        if not raw or not adjusted or price_family(raw['source'])!=price_family(adjusted['source']):
            return None
        qmap={r['date']:r['close'] for r in adjusted['items']}
        bars=[r|dict(adjusted_close=qmap.get(r['date'])) for r in raw['items']]
        industries=[s for s in market.repo.associations(profile,[code]).get(code,[]) if s['kind']=='industry' and s['classification']=='eastmoney-industry']
        sector=industries[0]['sector_id'] if len(industries)==1 else None
        calendar=market.calendar(profile)
        return meta|dict(sector=sector,sector_name=industries[0]['name'] if len(industries)==1 else None,
            bars=bars,as_of=as_of,profile=profile,source=raw['source'],adjustment=adjusted['adjustment_basis'],
            listed_sessions=sum(meta['listed_date']<=d<=as_of for d in calendar) if meta.get('listed_date') else 0,
            suspended=False if bars and bars[-1]['date']==as_of else None,research_member=True)

    def build(self,profile,warmup):
        svc=self.assistant
        market=svc.market
        if profile!=svc.settings.mode:
            return None  # The old live namespace must never replace a different active tier.
        end=warmup['as_of']
        calendar=market.calendar(profile)
        stocks=[]
        pending=False
        active_tasks=market.repo.tasks(profile,limit=50000)
        waiting={t['payload'].get('code') for t in active_tasks if t['kind']=='stock_history' and
                 t['payload'].get('end')==end and t['state'] in ('pending','running')}
        for code in warmup['codes']:
            meta=market.repo.stock(profile,code)
            stock=self.stock(profile,code,end)
            if stock is None:
                if code in waiting or market.repair_pair(profile,code,end):
                    pending=True
                    continue
                state,reason='failed','同源日线与复权资料未取得'
            elif not meta.get('identity_verified'):
                state,reason='unverified','证券身份/市场或上市资料待核实'
            elif meta.get('board')!='main':
                state,reason='excluded','当前新增买入规则仅适用于沪深主板'
            elif stock.get('st') is True:
                state,reason='excluded','ST或退市风险标记'
            elif not meta.get('listed_date'):
                state,reason='unverified','上市日期尚未核实'
            elif stock.get('listed_sessions',0)<120:
                state,reason='excluded','已核实上市时间不足120交易日'
            else:
                try:
                    stock=stock|dict(bars=stock['bars'][-120:])
                    metrics=validate_daily(stock['bars'],calendar,end)
                    if metrics['avg_amount']<50_000_000:
                        state,reason='excluded','已核实流动性不足'
                    else:
                        state,reason='valid','完整规则输入'
                        stocks.append(stock)
                except (ValueError,KeyError,TypeError):
                    state,reason='failed','历史完整性、价格或成交额缺失'
            market.repo.set_state(profile,'research:'+end+':'+code,dict(state=state,reason=reason))
        sectors=[]
        for s in market.repo.list_sectors(profile,SectorQuery(kind='industry',classification='eastmoney-industry')):
            hist=market.repo.get_history(profile,s['sector_id'],'raw','1900-01-01',end)
            if hist:
                sectors.append(dict(code=s['sector_id'],name=s['name'],classification=s['classification'],source=hist['source'],
                    bars=[r|dict(adjusted_close=r['close']) for r in hist['items']]))
        bm=market.repo.get_history(profile,'benchmark:000300','raw','1900-01-01',end)
        benchmark=[r|dict(adjusted_close=r['close']) for r in bm['items']] if bm else []
        result=rank_universe(stocks,sectors,benchmark,end,False,calendar)
        market.repo.set_state(profile,'market-baseline:'+end,result['market_ok'] is not None)
        coverage=market.coverage()
        if result['market_ok'] is None:
            coverage['state']='complete_with_gaps' if not coverage['pending'] else 'preparing'
            result['limitations'].append('沪深300完整历史或交易日历缺失，不能核实新增买入条件')
        if coverage['state']!='complete':
            result['limitations'].append('全目录覆盖未完整；候选排名基于当前已覆盖样本')
        for c in result['candidates']:
            c['valid_date']=next((d for d in calendar if d>end),None)
            c['holding_horizon']='5–20交易日'
        states=market.repo.states_with_prefix(profile,'research:'+end+':')
        result['exclusions']+= [dict(code=k.rsplit(':',1)[-1],reason=v['reason'],coverage_state=v['state']) for k,v in states.items() if v['state']!='valid']
        # Preserve the features that drove ranks without returning thousands of bars every refresh.
        inputs=[{k:v for k,v in s.items() if k!='bars'}|validate_daily(s['bars'],calendar,end) for s in stocks]
        fingerprint=hashlib.sha256(json.dumps(dict(as_of=end,stocks=inputs,sectors=result['sectors'],
            catalog_version=warmup['catalog_version']),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        previous=svc.repo.latest(profile,'report')
        if not previous or previous.get('input_hash')!=fingerprint or previous.get('config')!=warmup['settings'] or previous.get('coverage')!=coverage:
            evidence=svc.repo.records(profile,'event',limit=100)
            input_id=svc.repo.append(profile,'rule_inputs',fingerprint,dict(stocks=inputs,catalog_version=warmup['catalog_version'],as_of=end))
            result.update(as_of=end,generated_at=market.clock().isoformat(),demo=False,input_hash=fingerprint,input_evidence_id=input_id,
                          config=warmup['settings'],strategy_versions=['trend_v1','sector_trend_v1'],source='market-capability-adapters',
                          evidence=evidence,evidence_as_of=market.clock().isoformat(),coverage=coverage)
            result['limitations']+=['趋势基线尚未证明盈利优势；排名得分不是上涨概率','资讯覆盖可能不完整；未发现资讯不表示没有风险']
            svc.repo.append(profile,'dataset','current',dict(as_of=end,calendar=calendar,stocks=[],sectors=[],benchmark=[],
                    daily_complete=coverage['state']=='complete',research_scope='all',catalog_version=warmup['catalog_version'],coverage=coverage,
                    demo=False,source='indexed-market-cache'))
            identity=svc.repo.append(profile,'report',end,result)
            svc.repo.append(profile,'alert','report',dict(message='新的全市场盘后研究已生成',report_id=identity,timestamp=market.clock().isoformat(),demo=False))
            svc.check()
        if pending:
            raise Deferred(60)
        return result
