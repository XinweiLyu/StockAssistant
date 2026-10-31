"""Market browser and resumable history queries, with explicit coverage."""
from __future__ import annotations
from datetime import datetime, date, timedelta, time, timezone
from zoneinfo import ZoneInfo
from contextlib import contextmanager, nullcontext
import hashlib
import json
from src.schemas.a_share import AssistantSettings
from src.schemas.a_share_market import CatalogQuery, SectorQuery, HistoryPage, MarketStock, history_dates
from data_provider.a_share_market import MarketProvider
from src.services.a_share_market_jobs import Deferred

TZ=ZoneInfo('Asia/Shanghai')

class StaleMarketTask(RuntimeError):
    pass

def configuration_stamp(settings):
    return hashlib.sha256(repr(source_signature(settings)).encode()).hexdigest()[:12]


def price_family(source):
    return 'tushare' if str(source).startswith('tushare') else source


def source_signature(settings):
    return tuple(getattr(settings,k) for k in ('mode','research_scope','snapshot_provider','realtime_entitled','news_entitled','announcements_entitled','free_fallback'))


def completed_return(rows,end,sessions,calendar=None):
    valid=[r for r in rows if r['date']<=end]
    if len(valid)<=sessions or valid[-1]['date']!=end:
        return None
    if calendar:
        expected=[d for d in calendar if d<=end][-sessions-1:]
        if [r['date'] for r in valid[-sessions-1:]]!=expected:
            return None
    previous=valid[-1-sessions]['close']
    return valid[-1]['close']/previous-1 if previous else None


class MarketService:
    def __init__(self,assistant,repo,jobs,clock=None):
        self.assistant=assistant
        self.repo=repo
        self.jobs=jobs
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    @property
    def profile(self):
        return self.assistant.settings.mode

    def provider_for(self,settings):
        return MarketProvider(self.assistant._provider(),settings)

    def _payload(self,**kwargs):
        return dict(settings=self.assistant.settings.model_dump(),**kwargs)

    def _submit(self,task_kind,key,priority=20,**kwargs):
        return self.jobs.submit(self.profile,key+':'+configuration_stamp(self.assistant.settings),task_kind,self._payload(**kwargs),priority)

    def calendar(self,profile=None):
        profile=profile or self.profile
        value=self.repo.get_state(profile,'calendar',{})
        if not value and hasattr(self.assistant,'repo'):
            value=self.assistant.repo.latest(profile,'calendar',default={})
            if not value:
                value={'dates':self.assistant.repo.latest(profile,'dataset',default={}).get('calendar',[])}
        return sorted(set(value.get('dates') or []))

    def completed_day(self,profile=None):
        profile=profile or self.profile
        if profile=='demo' and hasattr(self.assistant,'repo'):
            value=self.assistant.repo.latest('demo','dataset',default={})
            if value.get('as_of'):
                return value['as_of']
        now=self.clock().astimezone(TZ)
        dates=[d for d in self.calendar(profile) if d<now.date().isoformat() or
               (d==now.date().isoformat() and now.time().replace(tzinfo=None)>=time(15,10))]
        # A calendar-date upper bound is only a query limit, never a claimed trading session.
        return dates[-1] if dates else (now.date()-timedelta(days=1)).isoformat()

    def bootstrap(self):
        if self.profile=='demo':
            self.ensure_demo()
            return
        day=self.clock().astimezone(TZ).date().isoformat()
        signature=hashlib.sha256(repr(source_signature(self.assistant.settings)).encode()).hexdigest()[:12]
        marker=day+':'+signature
        if self.repo.get_state(self.profile,'bootstrap_day')==marker:
            return
        self.repo.set_state(self.profile,'bootstrap_day',marker)
        self._submit('snapshot','snapshot:bootstrap:'+marker,0)
        self._submit('calendar','calendar:'+marker,5)
        self._submit('catalog','catalog:'+marker,15)
        self._submit('benchmark','benchmark:'+marker,30)
        for exchange,board in [('SSE','main'),('SSE','star'),('SZSE','main'),('BSE','beijing')]:
            self._submit('listing','listing:'+marker+':'+exchange+':'+board,25,exchange=exchange,board=board)
        for kind in ('industry','concept'):
            self._submit('sector_catalog','sector_catalog:'+marker+':'+kind,20,kind=kind)

    def catalog(self,query,codes=None):
        if self.profile=='demo':
            self.ensure_demo()
        result=self.repo.list_stocks(self.profile,query,codes)
        if not result['catalog']:
            self.bootstrap()
        result['coverage']=self.coverage()
        result['demo']=self.profile=='demo'
        result['health']=self.repo.states_with_prefix(self.profile,'health:')
        return result

    def stock(self,code):
        if self.profile=='demo':
            self.ensure_demo()
        result=self.repo.stock(self.profile,code)
        if result is None:
            raise ValueError('当前目录中没有该股票')
        groups=self.repo.associations(self.profile,[code]).get(code,[])
        return result|dict(quote=self.repo.quotes(self.profile,[code]).get(code),
                           industries=[g for g in groups if g['kind']=='industry'],concepts=[g for g in groups if g['kind']=='concept'],demo=self.profile=='demo')

    def _history_page(self,entity,code,start,end,adjust,kind,refresh=False,priority=10,extra=None):
        start,end=history_dates(start,end)
        cutoff=self.completed_day()
        limits=[]
        if end>cutoff:
            end=cutoff
            limits.append('历史指标与预测仅使用已完成的完整日线；当日临时行情单独展示')
        if start>end:
            raise ValueError('所选期间尚无已完成日线')
        key='history:'+entity+':'+adjust+':'+start+':'+end
        pointer=self.repo.get_state(self.profile,key,{})
        task=self.repo.task(pointer.get('id')) if pointer.get('id') else None
        if task and source_signature(AssistantSettings.model_validate(task['payload']['settings']))!=source_signature(self.assistant.settings): task=None
        cached=self.repo.get_history(self.profile,entity,adjust,start,end)
        covers=bool(cached and cached['requested_start']<=start and cached['requested_end']>=end)
        if cached and covers and not refresh and (self.profile=='demo' or not (task and task['state'] in ('pending','running','failed'))):
            items=cached['items']
            calendar=[d for d in self.calendar() if start<=d<=end]
            expected_end=calendar[-1] if calendar else end
            available={r['date'] for r in items}
            full_span=bool(items and (date.fromisoformat(items[0]['date'])-date.fromisoformat(start)).days<=10)
            complete=items and items[-1]['date']==expected_end and full_span and all(d in available for d in calendar)
            state='ready' if complete else 'partial'
            return HistoryPage(code=code,items=items,adjust=adjust,source=cached['source'],adjustment_basis=cached['adjustment_basis'],
                requested_start=start,requested_end=end,actual_start=items[0]['date'] if items else None,actual_end=items[-1]['date'] if items else None,
                state=state,fetched_at=cached['fetched_at'],demo=self.profile=='demo',limitations=limits+([] if state=='ready' else ['所选期间的实际有效历史较短或截止日缺失']))
        if self.profile=='demo':
            return HistoryPage(code=code,requested_start=start,requested_end=end,adjust=adjust,state='partial',items=(cached or {}).get('items',[]),source=(cached or {}).get('source'),adjustment_basis=(cached or {}).get('adjustment_basis'),actual_start=(cached or {}).get('actual_start'),actual_end=(cached or {}).get('actual_end'),fetched_at=(cached or {}).get('fetched_at'),demo=True,limitations=limits+['虚构历史只覆盖演示期间，不查询真实行情补齐'])
        key='history:'+entity+':'+adjust+':'+start+':'+end
        pointer=self.repo.get_state(self.profile,key,{})
        task=self.repo.task(pointer.get('id')) if pointer.get('id') else None
        if task and source_signature(AssistantSettings.model_validate(task['payload']['settings']))!=source_signature(self.assistant.settings): task=None
        if refresh or task is None:
            taskkey=key+(':'+self.clock().isoformat() if refresh else '')
            identity=self._submit(kind,taskkey,priority,entity=entity,code=code,start=start,end=end,adjust=adjust,pointer_key=key,**(extra or {}))
            self.repo.set_state(self.profile,key,{'id':identity})
            task=self.repo.task(identity)
        state='failed' if task and task['state']=='failed' else 'pending'
        if cached:
            limits.append('补齐所选历史期间中；原缓存时间保留')
        if state=='failed':
            limits.append(task.get('error') or '历史资料未取得，请重试')
        return HistoryPage(code=code,requested_start=start,requested_end=end,adjust=adjust,state=state,
                 items=(cached or {}).get('items',[]),source=(cached or {}).get('source'),adjustment_basis=(cached or {}).get('adjustment_basis'),
                 actual_start=(cached or {}).get('actual_start'),actual_end=(cached or {}).get('actual_end'),fetched_at=(cached or {}).get('fetched_at'),
                 task_id=task['id'] if task else None,demo=self.profile=='demo',limitations=limits)

    def history(self,code,start,end,adjust,refresh=False):
        self.stock(code)
        page=self._history_page('stock:'+code,code,start,end,adjust,'stock_history',refresh)
        if page.items:
            prior_end=(date.fromisoformat(page.items[0].date)-timedelta(days=1)).isoformat()
            cached=self.repo.get_history(self.profile,'stock:'+code,adjust,'1900-01-01',prior_end)
            # A provider refresh may replace the basis between these reads. Never
            # combine indicator history from a different publication generation.
            if cached and (cached['source'],cached['adjustment_basis'],cached['fetched_at'])==(page.source,page.adjustment_basis,page.fetched_at):
                try:
                    candidate=HistoryPage.model_validate(page.model_dump() | {'warmup_items':cached['items'][-249:]})
                    if any(min(b.open,b.high,b.low,b.close)<=0 for b in candidate.warmup_items):
                        raise ValueError('指标预热价格须为正数')
                    page=candidate
                except (ValueError,TypeError):
                    page.limitations.append('较早的指标预热历史未通过价格校验；保留所选期间，长周期指标可能不足窗口')
        return page

    def sectors(self,query):
        allowed={'demo-'+query.kind} if self.profile=='demo' else {'eastmoney-'+query.kind}
        if query.classification and query.classification not in allowed: raise ValueError('当前分类尚未接入')
        if self.profile=='demo':
            self.ensure_demo()
        items=self.repo.list_sectors(self.profile,query)
        if not items:
            self.bootstrap()
        end=self.completed_day()
        for sector in items:
            members=self.repo.members(self.profile,sector['sector_id'])
            quotes=self.repo.quotes(self.profile,members['codes'])
            latest_batch=self.repo.get_state(self.profile,'quote_batch',{}).get('batch')
            breadth=dict(total=len(members['codes']),up=0,down=0,flat=0,unknown=0)
            for code in members['codes']:
                q=quotes.get(code,{})
                change=q.get('change') if q.get('batch')==latest_batch else None
                key='unknown' if change is None else 'up' if change>0 else 'down' if change<0 else 'flat'
                breadth[key]+=1
            sector['member_breadth']=breadth
            sector['membership_version']=members['version']
            sector['membership_fetched_at']=members['fetched_at']
            sector['period']=query.period
            sector['published_change']=sector.get('change')
            if query.period:
                start=(date.fromisoformat(end)-timedelta(days=500)).isoformat()
                cached=self.repo.get_history(self.profile,sector['sector_id'],'raw',start,end)
                sector['change']=completed_return(cached['items'],end,query.period,self.calendar()) if cached else None
                sector['history_as_of']=end
                if not cached:
                    self._history_page(sector['sector_id'],sector['sector_id'],start,end,'raw','sector_history',priority=70,extra={'sector':sector})
        items.sort(key=lambda s:(s.get('change') is None,-(s.get('change') or 0),s['sector_id']))
        return dict(items=items,classification=query.classification or ('demo-'+query.kind if self.profile=='demo' else 'eastmoney-'+query.kind),
                    period=query.period,coverage=self.coverage(),demo=self.profile=='demo')

    def members(self,sector_id,query,refresh=False):
        sector=self.repo.sector(self.profile,sector_id)
        if not sector:
            raise ValueError('当前分类没有该板块')
        membership=self.repo.members(self.profile,sector_id)
        task=None
        stamp=membership.get('fetched_at')
        try:
            stale=not stamp or (self.clock()-datetime.fromisoformat(stamp)).total_seconds()>=86400
        except (ValueError,TypeError):
            stale=True
        generation=self.clock().astimezone(TZ).date().isoformat()+':'+configuration_stamp(self.assistant.settings)
        if self.profile!='demo' and (not membership['version'] or stale or refresh):
            task=self.repo.ensure_members_task(self.profile,sector_id,generation,self._payload(sector=sector),refresh)
        else:
            pointer=self.repo.get_state(self.profile,'members-task:'+sector_id,{})
            task=self.repo.task(pointer.get('id')) if pointer.get('generation')==generation else None
        if task:
            self.repo.set_state(self.profile,'members-task:'+sector_id,dict(id=task['id'],generation=generation))
            error=task.get('error') or ('成分股获取失败，请重试' if task['state']=='failed' else None)
            membership.update(task_id=task['id'],error=error,retry_at=task.get('next_attempt'),
                refreshing=task['state'] in ('pending','running') and not error)
            if not membership['version']:
                membership['state']='failed' if error else 'pending'
        field='industry_id' if sector['kind']=='industry' else 'concept_id'
        result=self.catalog(query.model_copy(update={field:sector_id}))
        return result|dict(sector=sector,membership=membership)

    def sector_history(self,sector_id,start,end,refresh=False):
        sector=self.repo.sector(self.profile,sector_id)
        if not sector:
            raise ValueError('当前分类没有该板块')
        return self._history_page(sector_id,sector_id,start,end,'raw','sector_history',refresh,extra={'sector':sector})

    def benchmark_history(self,start,end,refresh=False):
        if self.profile=='demo': self.ensure_demo()
        return self._history_page('benchmark:000300','benchmark:000300',start,end,'raw','benchmark',refresh)

    def repair_pair(self,profile,code,end,priority=80):
        raw=self.repo.get_history(profile,'stock:'+code,'raw','1900-01-01',end)
        adjusted=self.repo.get_history(profile,'stock:'+code,'qfq','1900-01-01',end)
        if not raw or not adjusted or price_family(raw['source'])==price_family(adjusted['source']): return False
        available={price_family(raw['source']),price_family(adjusted['source'])}
        source=next((s for s in ('tushare','akshare/tencent','akshare/sina','akshare/eastmoney') if s in available),None)
        if not source: return False
        start=(date.fromisoformat(end)-timedelta(days=500)).isoformat()
        ids=[]
        for adjust,cache in [('raw',raw),('qfq',adjusted)]:
            if price_family(cache['source'])==source: continue
            signature=hashlib.sha256(repr(source_signature(self.assistant.settings)).encode()).hexdigest()[:12]
            identity=self.jobs.submit(profile,'pair:'+code+':'+adjust+':'+source+':'+end+':'+signature,'stock_history',self._payload(entity='stock:'+code,code=code,start=start,end=end,adjust=adjust,forced_source=source),priority)
            ids.append(identity)
        return any(self.repo.task(i)['state'] in ('pending','running') for i in ids)

    def coverage(self):
        catalog=self.repo.get_state(self.profile,'catalog',{})
        warmup=self.repo.get_state(self.profile,'warmup',{})
        status=self.repo.states_with_prefix(self.profile,'research:'+warmup.get('as_of','')+':') if warmup.get('as_of') else {}
        total=len(warmup.get('codes') or []) or catalog.get('count',0)
        counts={k:sum(v.get('state')==k for v in status.values()) for k in ('valid','excluded','unverified','failed')}
        attempted=len(status)
        pending=max(0,total-attempted)
        state='preparing' if pending or not total else 'complete_with_gaps' if counts['failed'] or counts['unverified'] else 'complete'
        baseline=self.repo.get_state(self.profile,'market-baseline:'+warmup.get('as_of',''),None)
        if baseline is False and state=='complete': state='complete_with_gaps'
        if not warmup:
            state='not_started'
        return dict(catalog_total=total,attempted=attempted,**counts,pending=pending,as_of=warmup.get('as_of'),
                    catalog_version=warmup.get('catalog_version',catalog.get('version')),state=state,market_baseline_ready=baseline)

    def snapshot(self,slot):
        self._submit('snapshot','snapshot:'+slot,0)
        for kind in ('industry','concept'):
            self._submit('sector_catalog','sector_snapshot:'+kind+':'+slot,5,kind=kind,refresh_only=True)

    def live_price(self,code):
        from src.services.a_share_live_price import read
        return read(self,code)

    def refresh_price(self,code):
        from src.services.a_share_live_price import request
        return request(self,code)

    def warmup(self):
        if self.profile=='demo':
            self.ensure_demo()
            return dict(accepted=True,demo=True,coverage=self.coverage())
        self.bootstrap()
        marker=self.clock().astimezone(TZ).date().isoformat()+':'+hashlib.sha256(repr(source_signature(self.assistant.settings)).encode()).hexdigest()[:12]
        identity=self._submit('warmup','warmup:'+marker,90)
        return dict(accepted=True,task_id=identity,coverage=self.coverage())

    def _health(self,profile,kind,status,**kwargs):
        self.repo.set_state(profile,'health:'+kind,dict(kind=kind,status=status,fetched_at=self.clock().isoformat(),**kwargs))

    def _merge_catalog(self,profile,rows,version):
        existing={c:self.repo.stock(profile,c) for c in self.repo.catalog_codes(profile)}
        for s in rows:
            value=s.model_dump(mode='json') if hasattr(s,'model_dump') else s
            old=existing.get(value['code'])
            if old and old.get('identity_verified') and not value.get('identity_verified'):
                continue
            conflict=self.repo.get_state(profile,'identity-conflict:'+value['code'],{})
            if conflict or (old and (old.get('identity_conflict') or old.get('source')=='identity-conflict' or (old.get('identity_verified') and value.get('identity_verified') and old['exchange']!=value['exchange']))):
                observations=conflict.get('observations',[])
                for item in (old,value):
                    if item is not None:
                        evidence={k:item.get(k) for k in ('code','exchange','board','name','source','fetched_at')}
                        if not any(all(e.get(k)==evidence.get(k) for k in ('exchange','board','name','source')) for e in observations): observations.append(evidence)
                self.repo.set_state(profile,'identity-conflict:'+value['code'],dict(observations=observations,resolved=False))
                value=value|dict(identity_verified=False,identity_conflict=True)
            existing[value['code']]=value
        if existing:
            self.repo.replace_catalog(profile,version,list(existing.values()))

    @contextmanager
    def _publication(self,task):
        lock=getattr(self.assistant,'_settings_lock',None)
        with lock if lock is not None else nullcontext():
            profile=task['profile']
            settings=AssistantSettings.model_validate(task['payload']['settings'])
            if profile==self.profile and source_signature(settings)!=source_signature(self.assistant.settings):
                raise StaleMarketTask('configuration')
            if task.get('claim_version',0)>0:
                current=self.repo.task(task['id'])
                if not current or current['state']!='running' or current['claim_version']!=task['claim_version']:
                    raise StaleMarketTask('claim')
            yield

    def handle_task(self,task):
        profile=task['profile']
        payload=task['payload']
        settings=AssistantSettings.model_validate(payload['settings'])
        generation=configuration_stamp(settings)
        kind=task['kind']
        if profile==self.profile and source_signature(settings)!=source_signature(self.assistant.settings):
            self._health(profile,kind,'discarded_configuration')
            return
        if profile=='demo':
            self.ensure_demo()
            return
        provider=self.provider_for(settings)
        partial=False
        try:
            if kind=='stock_live':
                from src.services.a_share_live_price import handle
                handle(self,task,provider)
            elif kind=='catalog':
                rows=provider.catalog()
                with self._publication(task): self._merge_catalog(profile,rows,self.clock().isoformat())
            elif kind=='listing':
                rows=provider.listing_slice(payload['exchange'],payload['board'])
                with self._publication(task): self._merge_catalog(profile,rows,self.clock().isoformat())
            elif kind=='snapshot':
                paid={}
                batch=self.clock().isoformat()
                if settings.snapshot_provider=='tushare' and settings.realtime_entitled and profile==self.profile and hasattr(self.assistant,'_quotes'):
                    with self._publication(task):
                        self.assistant._quotes()
                        paid=self.assistant.repo.latest(profile,'quotes',default={}).get('quotes',{})
                        if paid: self.repo.put_quotes(profile,batch,list(paid.values()))
                        self.assistant.check()
                try:
                    quotes=provider.quotes()
                except (ValueError,RuntimeError,KeyError):
                    if not paid: raise
                    quotes=[]
                    partial=True
                with self._publication(task):
                    if quotes:
                        self.repo.put_quotes(profile,batch,quotes)
                        if not self.repo.get_state(profile,'catalog'):
                            stocks=[MarketStock(code=q.code,name=q.name or q.code,st=('ST' in (q.name or '').upper()) if q.name else None,source=q.source+'/provisional-directory',fetched_at=q.fetched_at) for q in quotes]
                            self._merge_catalog(profile,stocks,batch)
                    if paid: self.repo.put_quotes(profile,batch,list(paid.values()))
                    if hasattr(self.assistant,'market_quotes_updated'):
                        self.assistant.market_quotes_updated(profile,self.repo.quotes(profile))
            elif kind=='calendar':
                rows=provider.provider.call('tool_trade_date_hist_sina')
                days=sorted({str(r['trade_date'])[:10] for r in rows})
                if not days: raise ValueError('交易日历为空')
                with self._publication(task): self.repo.set_state(profile,'calendar',dict(dates=days,source='akshare/sina',fetched_at=self.clock().isoformat()))
            elif kind=='sector_catalog':
                sectors=provider.sectors(payload['kind'])
                with self._publication(task):
                    self.repo.put_sectors(profile,sectors)
                    if not payload.get('refresh_only'):
                        end=self.completed_day(profile)
                        start=(date.fromisoformat(end)-timedelta(days=500)).isoformat()
                        for s in sectors:
                            value=s.model_dump(mode='json')
                            self.jobs.submit(profile,'members:'+s.sector_id+':'+end+':'+generation,'members',dict(settings=payload['settings'],sector=value),60)
                            self.jobs.submit(profile,'sector_history:'+s.sector_id+':'+end+':'+generation,'sector_history',dict(settings=payload['settings'],sector=value,entity=s.sector_id,code=s.sector_id,start=start,end=end,adjust='raw'),65)
            elif kind=='members':
                sector=payload['sector']
                codes=provider.members(sector)
                with self._publication(task): self.repo.replace_members(profile,sector['sector_id'],self.clock().isoformat(),codes,source=getattr(provider,'members_source',None))
            elif kind=='benchmark':
                end=payload.get('end') or self.completed_day(profile)
                start=payload.get('start') or (date.fromisoformat(end)-timedelta(days=500)).isoformat()
                source=payload.get('source','akshare/eastmoney')
                try:
                    result=provider.benchmark_history(start,end,source)
                except (ValueError,RuntimeError):
                    if source=='akshare/eastmoney' and settings.free_fallback:
                        with self._publication(task):
                            identity=self.jobs.submit(profile,task.get('key','benchmark')+':fallback:'+generation,'benchmark',payload|dict(source='akshare/tencent',start=start,end=end),task.get('priority',30))
                            if payload.get('pointer_key'): self.repo.set_state(profile,payload['pointer_key'],{'id':identity})
                        return
                    raise
                with self._publication(task): self.repo.replace_history(profile,'benchmark:000300','raw',result.source,result.adjustment_basis,result.items,result.fetched_at,requested_start=start,requested_end=end)
            elif kind in ('stock_history','sector_history'):
                pointer_key=payload.get('pointer_key') or 'history:'+payload['entity']+':'+payload['adjust']+':'+payload['start']+':'+payload['end']
                payload=payload|dict(pointer_key=pointer_key)
                prior=self.repo.get_history(profile,payload['entity'],payload['adjust'],'1900-01-01',payload['end'])
                if prior and prior['requested_start']<payload['start']:
                    floor=date.fromisoformat(payload['end'])
                    try: floor=floor.replace(year=floor.year-5)
                    except ValueError: floor=floor.replace(year=floor.year-5,day=28)
                    payload=payload|dict(start=max(prior['requested_start'],floor.isoformat()))
                if kind=='sector_history': result=provider.sector_history(payload['sector'],payload['start'],payload['end'])
                else:
                    sources=(['tushare'] if profile.startswith('tushare') else [])+['akshare/eastmoney']
                    if settings.free_fallback: sources+=['akshare/sina','akshare/tencent']
                    elif profile.startswith('tushare'): sources=['tushare']
                    if payload.get('forced_source'): sources=[payload['forced_source']]
                    index=payload.get('source_index',0)
                    try:
                        result=provider.history(payload['code'],payload['start'],payload['end'],payload['adjust'],source=sources[index])
                    except (ValueError,RuntimeError):
                        if index+1>=len(sources): raise
                        with self._publication(task):
                            follow=payload|dict(source_index=index+1)
                            identity=self.jobs.submit(profile,task['key']+':fallback:'+str(index+1)+':'+generation,kind,follow,task['priority'])
                            self.repo.set_state(profile,pointer_key,{'id':identity})
                            self._health(profile,kind,'fallback',source=sources[index])
                        return
                with self._publication(task):
                    latest=self.repo.get_history(profile,payload['entity'],payload['adjust'],'1900-01-01','9999-12-31')
                    if kind=='stock_history' and latest and latest['actual_end']>result.items[-1].date:
                        self._health(profile,kind,'superseded_by_newer_history')
                        return
                    self.repo.replace_history(profile,payload['entity'],payload['adjust'],result.source,result.adjustment_basis,result.items,result.fetched_at,requested_start=payload['start'],requested_end=payload['end'])
            elif kind=='warmup':
                with self._publication(task):
                    codes=self.repo.catalog_codes(profile)
                    if not codes or not self.calendar(profile): raise Deferred(30)
                    end=self.completed_day(profile)
                    start=(date.fromisoformat(end)-timedelta(days=500)).isoformat()
                    catalog=self.repo.get_state(profile,'catalog',{})
                    warmup=dict(codes=codes,as_of=end,start=start,catalog_version=catalog['version'],settings=payload['settings'])
                    self.repo.set_state(profile,'warmup',warmup)
                    priorities=set(settings.watchlist)
                    if profile==self.profile: priorities|={p['code'] for p in self.assistant.portfolio().get('positions',[])}
                    for code in codes:
                        for adjust in ('raw','qfq'):
                            self.jobs.submit(profile,'warm-history:'+code+':'+adjust+':'+end+':'+generation,'stock_history',dict(settings=payload['settings'],entity='stock:'+code,code=code,start=start,end=end,adjust=adjust),80 if code in priorities else 100)
                    self.jobs.submit(profile,'report:'+task['id'],'report',dict(settings=payload['settings'],warmup=warmup),110)
            elif kind=='report':
                if not hasattr(self.assistant,'build_market_report'): raise ValueError('报告服务尚不可用')
                with self._publication(task): self.assistant.build_market_report(profile,payload['warmup'])
            else: raise ValueError('未知市场任务')
            with self._publication(task): self._health(profile,kind,'partial' if partial else 'ok')
        except StaleMarketTask:
            self._health(profile,kind,'discarded_configuration')
        except Deferred: raise
        except Exception as exc:
            self._health(profile,kind,'failed',error=type(exc).__name__)
            raise

    def ensure_demo(self):
        existing=self.repo.get_state('demo','catalog')
        if not hasattr(self.assistant,'repo'):
            return
        data=self.assistant.repo.latest('demo','dataset',default={})
        if not data.get('stocks'):
            self.assistant._demo()
            data=self.assistant.repo.latest('demo','dataset',default={})
        fetched=self.clock().isoformat()
        stocks=[MarketStock(code=s['code'],name=s['name'],board='main',exchange='unknown',st=False,identity_verified=False,
                            source='synthetic',fetched_at=fetched) for s in data['stocks']]
        if not existing: self.repo.replace_catalog('demo','synthetic',stocks)
        self.repo.set_state('demo','calendar',dict(dates=data['calendar'],source='synthetic'))
        def bars_of(s):
            return [dict(date=r['date'],open=r['close'],high=r['high'],low=r['low'],close=r['close'],volume=r.get('volume'),amount=r.get('amount')) for r in s['bars']]
        benchmark=self.repo.get_history('demo','benchmark:000300','raw','1900-01-01',data['as_of'])
        if data.get('benchmark') and (not benchmark or benchmark['source']!='synthetic'):
            self.repo.replace_history('demo','benchmark:000300','raw','synthetic','synthetic',bars_of({'bars':data['benchmark']}),fetched)
        if existing: return
        for s in data['stocks']:
            for adjust in ('raw','qfq'):
                self.repo.replace_history('demo','stock:'+s['code'],adjust,'synthetic','synthetic',bars_of(s),fetched,
                    requested_start=(date.fromisoformat(data['as_of'])-timedelta(days=365*5)).isoformat(),requested_end=data['as_of'])
        sectors=[]
        for i,s in enumerate(data['sectors']):
            for kind in ('industry','concept'):
                identity='demo:'+kind+':'+s['code']
                sectors.append(dict(sector_id=identity,code=s['code'],name=s['name'] if kind=='industry' else '演示概念'+str(i+1),kind=kind,
                    classification='demo-'+kind,source='synthetic',change=s['bars'][-1]['close']/s['bars'][-2]['close']-1,fetched_at=fetched))
                members=[stock['code'] for stock in data['stocks'] if stock['sector']==s['code']]
                self.repo.replace_members('demo',identity,'synthetic',members)
                self.repo.replace_history('demo',identity,'raw','synthetic','synthetic',bars_of(s),fetched,
                    requested_start=(date.fromisoformat(data['as_of'])-timedelta(days=365*5)).isoformat(),requested_end=data['as_of'])
        self.repo.put_sectors('demo',sectors)
        quotes=[dict(code=s['code'],name=s['name'],price=s['bars'][-1]['close'],change=s['bars'][-1]['close']/s['bars'][-2]['close']-1,
                    source='synthetic',fetched_at=fetched,source_time=None,trade_date=None,amount=s['bars'][-1]['amount']) for s in data['stocks']]
        self.repo.put_quotes('demo','synthetic',quotes)
        self.repo.set_state('demo','warmup',dict(codes=[s['code'] for s in data['stocks']],as_of=data['as_of'],catalog_version='synthetic'))
        for s in data['stocks']:
            self.repo.set_state('demo','research:'+data['as_of']+':'+s['code'],dict(state='valid'))
