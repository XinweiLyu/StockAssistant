"""Cached offshore workspace, using the existing market queue and typed history."""
from datetime import datetime,date,timedelta,timezone
from contextlib import contextmanager
import re
from zoneinfo import ZoneInfo
from types import SimpleNamespace
import threading
from sqlalchemy import update
from src.schemas.a_share_market import MarketStock,CatalogQuery,HistoryPage,SectorQuery,history_dates
from src.repositories.a_share_market_repository import MarketRepository,CATALOG,encode
from src.repositories.market_workspace_repository import WorkspaceMarketRepository
from src.services.a_share_market_jobs import MarketJobs
from src.services.a_share_market_service import MarketService,StaleMarketTask,source_signature
from src.services.market_workspace_symbols import resolve_instrument
from src.schemas.market_workspace import MARKET_TIMEZONES
from data_provider.market_workspace import WorkspaceProvider,finite


class WorkspaceAssistant(SimpleNamespace):
    @property
    def settings(self):return self.parent.settings


class MarketWorkspaceService:
    def __init__(self,parent,market,provider=None,clock=None):
        if market not in ('hk','us'):raise ValueError('A股使用原有服务')
        self.parent=parent;self.market_name=market;self.provider=provider or WorkspaceProvider()
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.assistant=WorkspaceAssistant(parent=parent,repo=parent.repo,_settings_lock=parent._settings_lock,market=self)
        self.repo=WorkspaceMarketRepository(MarketRepository(parent.repo.engine),market)
        self.jobs=MarketJobs(self.repo,self.handle_task,profile=self.profile,kinds=['workspace_identity','workspace_history','workspace_quote'])
        self._calendar_cache=None
        self._history_guard=threading.Lock();self._history_locks={}
        self.benchmark_entity='benchmark:'+market
        self.industry_classification='yahoo-industry'

    def initialize_research(self,sources=None):
        from data_provider.offshore_research import OffshoreResearchSources
        from src.services.market_workspace_research import WorkspaceResearchService,WorkspaceOutlookService
        from src.services.market_workspace_value import WorkspaceValueService
        from src.services.a_share_service import AssistantService
        assistant=self.assistant
        assistant.major_risks=lambda:{}
        assistant.portfolio=lambda:dict(positions=[],cash=None,account=None,limitations=['港美股研究未绑定交易账户，不生成下单股数'])
        assistant.value_metadata=self.value_metadata
        assistant.integrated=WorkspaceResearchService(assistant,sources or OffshoreResearchSources())
        assistant.value=WorkspaceValueService(assistant)
        outlook=WorkspaceOutlookService(assistant)
        assistant.quant_outlook=outlook.get
        assistant.price_context=lambda code:AssistantService.price_context(assistant,code)

    def value_metadata(self,code):
        stock=self.stock(code);data=self.assistant.repo.latest(self.profile,'research_data',key=self.profile+':'+code,default={})
        currencies={f['currency'] for f in data.get('value_facts',[]) if f.get('unit') not in ('shares','ratio','multiple')}
        currency=next(iter(currencies)) if len(currencies)==1 else stock.get('financial_currency') or 'XXX'
        return dict(market=self.market_name,currency=currency)

    @property
    def profile(self):return self.assistant.settings.mode
    def identity(self,code):return resolve_instrument(self.market_name,code)
    def _payload(self,**kwargs):return dict(settings=self.assistant.settings.model_dump(),**kwargs)
    @contextmanager
    def _publication(self,task):
        with self.assistant._settings_lock:
            if task['profile']!=self.profile:raise StaleMarketTask('profile')
            with MarketService._publication(self,task):yield

    def _captured_task(self,task):
        return task|dict(profile=task.get('profile',self.profile),payload=dict(settings=self.assistant.settings.model_dump())|task['payload'])

    def calendar(self,profile=None):
        from src.core.trading_calendar import get_trading_dates
        now=self.clock().astimezone(ZoneInfo(MARKET_TIMEZONES[self.market_name])).date()
        key=now.isoformat()
        if self._calendar_cache and self._calendar_cache[0]==key:return self._calendar_cache[1]
        days=get_trading_dates(self.market_name,now-timedelta(days=1900),now+timedelta(days=330))
        if days is None:raise ValueError('交易所日历不可用，不能认证完整日线和未来交易日')
        result=[d.date().isoformat() for d in days]
        self._calendar_cache=(key,result)
        return result

    def completed_day(self,profile=None):
        import exchange_calendars as xcals
        from src.core.trading_calendar import MARKET_EXCHANGE,completed_daily_bar_close
        sessions=set(self.calendar())  # certification must fail closed
        now=self.clock();local=now.astimezone(ZoneInfo(MARKET_TIMEZONES[self.market_name]))
        try:
            cal=xcals.get_calendar(MARKET_EXCHANGE[self.market_name])
            session=cal.date_to_session(local.date(),direction='previous')
            if completed_daily_bar_close(self.market_name,cal,session).to_pydatetime()>now:session=cal.previous_session(session)
            while session.date().isoformat() not in sessions:session=cal.previous_session(session)
            return session.date().isoformat()
        except Exception as exc:raise ValueError('交易所日历不可用，不能认证完整日线') from exc

    def bootstrap(self):
        if self.repo.get_state(self.profile,'catalog'):return
        stamp=self.clock().isoformat();rows=[]
        for item in self.provider.catalog(self.market_name):
            try:identity=self.identity(item['symbol'])
            except ValueError:continue
            rows.append(MarketStock(code=identity.instrument_id,name=item['name'],market=self.market_name,
                aliases=item.get('aliases',[]),
                symbol=identity.symbol,instrument_id=identity.instrument_id,timezone=identity.timezone,
                asset_type='unknown',source='stock-index/candidate',fetched_at=stamp))
        if rows:self.repo.replace_catalog(self.profile,'seed:'+stamp,list({r.code:r for r in rows}.values()))

    def coverage(self):
        total=self.repo.get_state(self.profile,'catalog',{}).get('count',0)
        classified=len(self.repo.associations(self.profile))
        return dict(catalog_total=total,attempted=classified,valid=classified,excluded=0,unverified=max(0,total-classified),failed=0,pending=0,
            state='partial',as_of=self.completed_day(),classified=classified,
            limitations=['股票索引为候选目录；上市资格与证券类型须另行核实','行业筛选仅覆盖已取得分类的证券，未宣称完整行业成员'])

    def catalog(self,query,codes=None):
        self.bootstrap()
        q=query.q.strip()
        if q:
            try:
                identity=self.identity(q)
                if self.repo.stock(self.profile,identity.instrument_id):query=query.model_copy(update={'q':identity.instrument_id})
            except ValueError:pass
        result=self.repo.list_stocks(self.profile,query,codes)
        return result|dict(coverage=self.coverage(),demo=False,market=self.market_name)

    def _enqueue(self,kind,key,**payload):
        return self.jobs.submit(self.profile,key,kind,self._payload(**payload),10)

    def stock(self,code):
        identity=self.identity(code);self.bootstrap();key=identity.instrument_id
        stock=self.repo.stock(self.profile,key)
        if not stock:
            # A lawful but unlisted symbol can be looked up, never called verified.
            stock=MarketStock(code=key,name=identity.symbol,market=self.market_name,symbol=identity.symbol,
                instrument_id=key,timezone=identity.timezone,asset_type='unknown',source='user/symbol',fetched_at=self.clock().isoformat()).model_dump()
            self._upsert_stock(stock)
        if not stock['identity_verified'] and not self.repo.get_state(self.profile,'identity-task:'+key):
            task=self._enqueue('workspace_identity','identity:'+key,code=key)
            self.repo.set_state(self.profile,'identity-task:'+key,dict(id=task))
        groups=self.repo.associations(self.profile,[key]).get(key,[])
        quote=self.repo.quotes(self.profile,[key]).get(key)
        currency=stock.get('currency')
        quote_currency=(quote or {}).get('currency')
        # The same listing's quote supplies price units when the profile is unavailable.
        if not currency and isinstance(quote_currency,str) and re.fullmatch(r'[A-Z]{3}',quote_currency):
            currency=quote_currency
        return stock|dict(currency=currency,quote=quote,industries=[s for s in groups if s['kind']=='industry'],concepts=[],demo=False)

    def _upsert_stock(self,stock):
        values=MarketStock.model_validate(stock).model_dump()
        with self.repo.engine.begin() as conn:
            self.repo.base._upsert(conn,CATALOG,dict(profile=self.repo.physical(self.profile),code=values['code'],name=values['name'],board=values['board'],st=values['st'],payload=encode(values)))

    def history(self,code,start,end,adjust='qfq',refresh=False):
        start,end=history_dates(start,end,stock_history=True)
        stock=self.stock(code);code=stock['code'];end=min(end,self.completed_day())
        if start>end:raise ValueError('所选区间尚无完整交易日')
        if adjust not in ('raw','qfq'):raise ValueError('价格口径不支持')
        key = 'pair:' + code + ':' + start + ':' + end
        # Serialize request registration with publication of the paired history.
        with self.assistant._settings_lock:
            profile = self.profile
            pointer = self.repo.get_state(profile, key, {})
            task = self.repo.task(pointer['id']) if pointer.get('id') else None
            cached = self.repo.get_history(profile, 'stock:' + code, adjust, start, end)
            covers = bool(cached and cached['requested_start'] <= start and cached['requested_end'] >= end)
            active = task and task['state'] in ('pending', 'running')
            if not active and (refresh or (not covers and task is None)):
                job_key = key + ':' + self.clock().isoformat() if refresh else key
                task_id = self._enqueue('workspace_history', job_key, code=code, start=start, end=end)
                self.repo.set_state(profile, key, dict(id=task_id))
                task = self.repo.task(task_id)

        items = (cached or {}).get('items', [])
        if task and task['state'] in ('pending', 'running'):
            state = 'pending'
        elif task and task['state'] == 'failed':
            state = 'failed'
        elif covers and items and items[-1]['date'] == end:
            state = 'ready'
        else:
            state = 'partial'
        limits=['历史只包含已完成日线；Yahoo复权为供应商总回报口径，非A股前复权','免费行情可能延迟，报价获取时间不等于源发布时间']
        if task and task.get('error'):
            if task['error'].endswith('：YFRateLimitError'):
                limits.append('Yahoo 暂时限制行情请求，系统将按计划重试。' if state == 'pending'
                              else 'Yahoo 暂时限制行情请求，本次补齐未完成。')
            else:
                limits.append(task['error'])
        warmup=[]
        if items:
            prior_end=(date.fromisoformat(items[0]['date'])-timedelta(days=1)).isoformat()
            prior=self.repo.get_history(profile,'stock:'+code,adjust,'1900-01-01',prior_end)
            if prior and all(prior.get(k)==cached.get(k) for k in ('source','adjustment_basis','fetched_at')):
                warmup=prior['items'][-249:]
            if len(warmup)<249:limits.append('较早的同版本指标预热历史不足249日，长均线可能不足窗口；更新数值研究可补齐更长历史')
        return HistoryPage(market=self.market_name,currency=stock.get('currency'),timezone=stock.get('timezone'),code=code,items=items,warmup_items=warmup,adjust=adjust,source=(cached or {}).get('source'),
            adjustment_basis=(cached or {}).get('adjustment_basis'),requested_start=start,requested_end=end,
            actual_start=items[0]['date'] if items else None,actual_end=items[-1]['date'] if items else None,
            state=state,fetched_at=(cached or {}).get('fetched_at'),task_id=task['id'] if task else None,limitations=limits)

    def refresh_price(self,code):
        stock=self.stock(code);code=stock['code']
        pointer=self.repo.get_state(self.profile,'live-task:'+code,{})
        task=self.repo.task(pointer.get('id')) if pointer.get('id') else None
        if not task or task['state'] not in ('pending','running'):
            task_id=self._enqueue('workspace_quote','quote:'+code+':'+self.clock().isoformat(),code=code)
            self.repo.set_state(self.profile,'live-task:'+code,dict(id=task_id))
        return self.live_price(code)

    def live_price(self,code):
        stock=self.stock(code);code=stock['code']
        pointer=self.repo.get_state(self.profile,'live-task:'+code,{})
        task=self.repo.task(pointer.get('id')) if pointer.get('id') else None
        quote=stock.get('quote');state='pending' if task and task['state'] in ('pending','running') else 'failed' if task and task['state']=='failed' else 'ready' if quote else 'unavailable'
        end=self.completed_day();raw=self.repo.get_history(self.profile,'stock:'+code,'raw','1900-01-01',end)
        adjusted=self.repo.get_history(self.profile,'stock:'+code,'qfq','1900-01-01',end)
        pointer=self.repo.get_state(self.profile,'quote-history-task:'+code,{})
        history_task=self.repo.task(pointer.get('id')) if pointer.get('id') else None
        repairing=history_task and history_task['state'] in ('pending','running')
        if repairing and not history_task.get('error'):state='pending'
        bindings={};bars=dict(raw=None,qfq=None)
        paired=bool(not repairing and raw and adjusted and raw['adjustment_basis']==adjusted['adjustment_basis'] and raw['items'] and adjusted['items']
            and raw['items'][-1]['date']==end and adjusted['items'][-1]['date']==end and (quote or {}).get('source')==raw['source'])
        for basis,history in [('raw',raw),('qfq',adjusted)]:
            if history and history['items']:
                last=history['items'][-1]
                bindings[basis]=dict(source=history['source'],adjustment_basis=history['adjustment_basis'],fetched_at=history['fetched_at'],anchor_date=last['date'],anchor_close=last['close'])
        provisional=bool((quote or {}).get('trade_date') and quote['trade_date']>end)
        if paired and provisional:
            from src.schemas.a_share_market import MarketBar
            try:
                bar=MarketBar(date=quote['trade_date'],open=quote.get('open'),high=quote.get('high'),low=quote.get('low'),close=quote['price'],volume=quote.get('volume')).model_dump()
                factor=adjusted['items'][-1]['close']/raw['items'][-1]['close']
                bars=dict(raw=bar,qfq=bar|{k:bar[k]*factor for k in ('open','high','low','close')})
            except ValueError:pass
        return dict(code=code,state=state,quote=quote,task_id=task['id'] if task else None,
            bars=bars,provisional=provisional,source=(quote or {}).get('source'),adjustment_basis=(raw or {}).get('adjustment_basis'),
            fetched_at=(quote or {}).get('fetched_at'),completed_day=self.completed_day(),history_updated=False,demo=False,
            history_binding=bindings,
            message='免费行情快照，延迟情况以来源为准；不会触发模型研究')|dict(history_updated=paired)

    def sectors(self,query):
        items=self.repo.list_sectors(self.profile,query)
        return dict(items=items,classification='yahoo-industry',period=query.period,demo=False,coverage=self.coverage(),
            message='仅已核实分类的覆盖范围；无完整概念库或行业指数涨跌')

    def members(self,sector_id,query,refresh=False):
        if not self.repo.sector(self.profile,sector_id):raise ValueError('该市场未取得此行业')
        membership=self.repo.members(self.profile,sector_id)
        return self.catalog(query,membership['codes'])|dict(membership=membership)

    def benchmark_history(self,start,end,refresh=False):
        entity='benchmark:'+self.market_name
        cached=self.repo.get_history(self.profile,entity,'raw',start,end)
        return HistoryPage(code=entity,items=(cached or {}).get('items',[]),adjust='raw',source=(cached or {}).get('source'),
            requested_start=start,requested_end=end,state='ready' if cached else 'partial',limitations=['宽基参照不代表行业或风格完全匹配'])

    def repair_pair(self,*args,**kwargs):return False

    def handle_task(self,task):
        task=self._captured_task(task)
        with self._publication(task):pass
        code=task['payload']['code'];identity=self.identity(code)
        if task['kind']=='workspace_identity':
            data=self.provider.identity(identity)
            with self._publication(task):
                stock=self.repo.stock(self.profile,code)
                stock.update(name=data['name'],exchange=data['exchange'],asset_type=data['asset_type'],currency=data.get('currency'),
                    financial_currency=data.get('financial_currency'),identity_verified=data.get('verified',False),source='yfinance/identity',fetched_at=self.clock().isoformat())
                self._upsert_stock(stock);self.repo.set_state(self.profile,'identity:'+code,data)
                if data.get('info'):
                    from data_provider.market_workspace import yahoo_quote
                    try:
                        quote=yahoo_quote(identity,data['info']);quote.update(code=code,fetched_at=self.clock().isoformat())
                        self.repo.put_quotes(self.profile,self.clock().isoformat(),[quote])
                    except ValueError:pass
                if data.get('industry'):
                    from src.schemas.a_share_integrated import digest
                    sid=self.market_name+':industry:'+digest(data['industry'])[:16]
                    self.repo.put_sectors(self.profile,[dict(sector_id=sid,code=sid,name=data['industry'],kind='industry',classification='yahoo-industry',source='yfinance',change=None,fetched_at=self.clock().isoformat())])
                    members=self.repo.members(self.profile,sid)['codes']
                    self.repo.replace_members(self.profile,sid,self.clock().isoformat(),members+[code],source='yfinance/verified_identity')
                    self.assistant.repo.append(self.profile,'industry_archive',self.profile+':'+code,
                        dict(code=code,sector_id=sid,source='yfinance/identity',observed_at=self.clock().isoformat()))
        elif task['kind']=='workspace_history':
            self._store_history(code,identity,task['payload']['start'],task['payload']['end'],task)
        elif task['kind']=='workspace_quote':
            quote=self.provider.quote(identity)
            if finite(quote.get('price')) is None or quote['price']<=0:raise ValueError('报价缺失，不能用0替代')
            if quote.get('source_time') and not quote.get('trade_date'):
                try:quote['trade_date']=datetime.fromisoformat(quote['source_time'].replace('Z','+00:00')).astimezone(ZoneInfo(identity.timezone)).date().isoformat()
                except ValueError:pass
            with self._publication(task):
                quote.update(code=code,fetched_at=self.clock().isoformat())
                self.repo.put_quotes(self.profile,self.clock().isoformat(),[quote])
                end=self.completed_day();cached=self.repo.get_history(self.profile,'stock:'+code,'raw','1900-01-01',end)
                start=(cached or {}).get('requested_start') or (date.fromisoformat(end)-timedelta(days=365)).isoformat()
                history=self.history(code,start,end,'raw',refresh=True)
                self.repo.set_state(self.profile,'quote-history-task:'+code,dict(id=history.task_id))


    def _store_history(self,code,identity,start,end,task=None):
        task=self._captured_task(task or dict(kind="workspace_history",payload=dict(code=code,start=start,end=end)))
        with self._history_guard:
            lock=self._history_locks.setdefault(code,threading.RLock())
        with lock:
            current=self.repo.get_history(self.profile,'stock:'+code,'raw','1900-01-01',self.completed_day())
            if current:start=min(start,current['requested_start']);end=max(end,current['requested_end'])
            pair=self.provider.history(identity,start,end)
            if not pair.get('raw') or [b['date'] for b in pair['raw']]!=[b['date'] for b in pair.get('adjusted',[])]:
                raise ValueError('原始与复权必须同次完整配对，保留原配对缓存')
            if current and pair['raw'][0]['date']>current['actual_start']:
                raise ValueError('本次来源返回的历史较短，已保留原有较早日线')
            with self._publication(task):
                previous=self.repo.get_history(self.profile,'stock:'+code,'raw',start,end)
                if previous and previous['adjustment_basis']==pair['basis'] and previous['requested_start']<=start and previous['requested_end']>=end:return
                with self.repo.engine.begin() as conn:
                    for basis,key in [('raw','raw'),('qfq','adjusted')]:
                        self.repo.replace_history(self.profile,'stock:'+code,basis,pair['source'],pair['basis'],pair[key],pair['fetched_at'],start,end,conn=conn)
                    self.repo.set_state(self.profile,'actions:'+code,pair.get('actions',[]),conn=conn)

    def start(self):
        self.jobs.start()
        if hasattr(self.assistant,'integrated'):self.assistant.integrated.jobs.start();self.assistant.value.jobs.start()
    def stop(self):
        self.jobs.stop()
        if hasattr(self.assistant,'integrated'):self.assistant.integrated.jobs.stop();self.assistant.value.jobs.stop()
